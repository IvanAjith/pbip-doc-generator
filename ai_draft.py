"""Optional AI drafting of definitions. Off by default; switched on with  python run.py --ai <provider>.

Providers: anthropic (Claude), gemini (Google), openai (ChatGPT API). Each reads its own key from an
environment variable. Only the indicator's name, the formula wording, the page name and the report's name and
page names are sent -- never report data. With --ai-send-dax the measure's DAX text is also sent (better
accuracy; check that your client allows it). Every result is labelled as an AI draft to verify.
"""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

LABEL = "AI draft - please verify"

SYSTEM = (
    "You write one-sentence glossary definitions of business indicators (KPIs) for the business users of a "
    "Power BI report. Use ONLY the information supplied (name, formula in words or DAX, what it is based on, "
    "page name, report name) plus the widely accepted meaning of the term in that industry. If the term is "
    "company-specific and the information does not make its meaning clear, restate what the formula does in plain "
    "words and do not invent details. If you cannot say anything useful, reply with exactly: UNKNOWN. "
    "No marketing language, no numbers that were not supplied, at most 35 words, no leading phrase such as "
    "'This KPI'. Reply with the definition only."
)

PROVIDERS = {
    "anthropic": {"env": ["ANTHROPIC_API_KEY"], "model": "claude-sonnet-5-5",
                  "url": "https://api.anthropic.com/v1/messages"},
    "gemini": {"env": ["GEMINI_API_KEY", "GOOGLE_API_KEY"], "model": "gemini-2.5-flash",
               "url": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"},
    "openai": {"env": ["OPENAI_API_KEY"], "model": "gpt-4o-mini",
               "url": "https://api.openai.com/v1/chat/completions"},
}


def key_from_env(provider):
    """The provider's key from the environment, the secure store or the private user file (see secrets_store)."""
    import secrets_store
    return secrets_store.get_key(provider)[0]


def build_request(provider, model, system, user, max_tokens=160):
    """-> (url, headers, payload) for one provider."""
    cfg = PROVIDERS[provider]
    url = cfg["url"].format(model=urllib.parse.quote(model, safe=""))
    if provider == "anthropic":
        return url, {"anthropic-version": "2023-06-01"}, {
            "model": model, "max_tokens": max_tokens, "system": system,
            "messages": [{"role": "user", "content": user}]}
    if provider == "gemini":
        return url, {}, {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"maxOutputTokens": max_tokens * 4, "temperature": 0.2}}
    return url, {}, {
        "model": model, "max_completion_tokens": max_tokens * 4,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}


def read_reply(provider, data):
    """Pull the text out of a provider's JSON reply ('' when the shape is unexpected)."""
    try:
        if provider == "anthropic":
            return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        if provider == "gemini":
            cand = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in cand)
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError, AttributeError):
        return ""


def _http(url, headers, payload, key, provider, timeout=40):
    h = {"content-type": "application/json", **headers}
    if provider == "anthropic":
        h["x-api-key"] = key
    elif provider == "gemini":
        h["x-goog-api-key"] = key
    else:
        h["authorization"] = "Bearer " + key
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


class AIDrafter:
    def __init__(self, provider="anthropic", api_key=None, model=None, max_calls=150, post=None,
                 verbose=True, report_context="", send_dax=False):
        if provider not in PROVIDERS:
            raise ValueError(f"unknown AI provider {provider!r}; choose one of {', '.join(PROVIDERS)}")
        self.provider = provider
        self.api_key = api_key or key_from_env(provider)
        self.model = model or PROVIDERS[provider]["model"]
        self.max_calls = max_calls
        self.post = post                      # injectable for tests: post(url, headers, payload, key) -> dict
        self.verbose = verbose
        self.report_context = report_context
        self.send_dax = send_dax
        self.calls = self.failures = self.drafted = 0
        self.dead = False
        self.dead_reason = ""
        self.label = f"{LABEL} ({provider})"

    @property
    def usable(self):
        return bool(self.api_key) and not self.dead

    def _disable(self, why):
        self.dead, self.dead_reason = True, why
        if self.verbose:
            print(f"  (AI drafting switched off: {why})")

    def _fail(self, why):
        self.failures += 1
        if self.failures >= 3:
            self._disable(f"3 failed calls in a row ({why})")

    def facts(self, term, calc="", basis="", page="", rules=(), dax="", **_):
        f = []
        if self.report_context:
            f.append(f"Report: {self.report_context}")
        f.append(f"Indicator name: {term}")
        if calc:
            f.append(f"How the report calculates it (in words): {calc}")
        if basis:
            f.append(f"It is a status badge based on: {basis}")
        if rules:
            f.append("Colour rules in the report: " + " ".join(rules))
        if page:
            f.append(f"Shown on the report page: {page}")
        if self.send_dax and dax:
            f.append("DAX: " + re.sub(r"\s+", " ", dax)[:1500])
        return "\n".join(f)

    def draft(self, term, **ctx):
        if not self.usable or self.calls >= self.max_calls or not term:
            return None
        url, headers, payload = build_request(self.provider, self.model, SYSTEM, self.facts(term, **ctx))
        self.calls += 1
        try:
            data = (self.post or (lambda u, h, p, k: _http(u, h, p, k, self.provider)))(url, headers, payload, self.api_key)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                self._disable(f"the key was rejected (HTTP {e.code})")
            elif e.code == 404:
                self._disable(f"the model name {self.model!r} was not accepted (HTTP 404) -- try --ai-model <name>")
            elif e.code == 429:
                self._disable("the provider's usage limit was reached (HTTP 429) -- remaining terms get formula drafts")
            else:
                self._fail(f"HTTP {e.code}")
            return None
        except Exception as e:
            self._fail(type(e).__name__)
            return None
        self.failures = 0
        text = re.sub(r"\s+", " ", read_reply(self.provider, data)).strip().strip('"')
        if not text or text.upper().startswith("UNKNOWN") or len(text) < 15:
            return None
        self.drafted += 1
        return {"text": text, "origin": self.label}
