"""Optional AI drafting of definitions. Off by default; switched on with  python run.py --ai <provider>.

Providers: anthropic (Claude), gemini (Google), openai (ChatGPT API). Each reads its own key from an
environment variable. Only the indicator's name, the formula wording, the page name and the report's name and
page names are sent -- never report data. With --ai-send-dax the measure's DAX text is also sent (better
accuracy; check that your client allows it). Every result is labelled as an AI draft to verify.
"""
import json
import os
import re
import time
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
    "gemini": {"env": ["GEMINI_API_KEY", "GOOGLE_API_KEY"], "model": "gemini-3.5-flash-lite",
               # Google retires/limits model names now and then (2.5 Flash is closed to new users): when a name
               # gives HTTP 404, the next one is tried automatically unless you chose the model yourself.
               "fallbacks": ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.1-flash-lite",
                             "gemini-2.5-flash-lite", "gemini-2.5-flash"],
               "url": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"},
    "openai": {"env": ["OPENAI_API_KEY"], "model": "gpt-4o-mini",
               "url": "https://api.openai.com/v1/chat/completions"},
    # any other service that speaks the OpenAI "chat completions" format (Azure OpenAI, Mistral, Groq, DeepSeek,
    # OpenRouter, Together, a company gateway, a local Ollama ...). Its web address and model name come from the user.
    "custom": {"env": ["AI_API_KEY"], "model": "", "url": ""},
}


def clean_base_url(url):
    """Accept https://host/v1, https://host/v1/chat/completions or an Azure deployment URL -> full request URL.
    Returns '' when it is not a safe web address (https only; plain http only for this computer)."""
    url = (url or "").strip().strip('"').strip("'")
    p = urllib.parse.urlparse(url)
    local = p.hostname in ("localhost", "127.0.0.1", "::1")
    if not p.hostname or not (p.scheme == "https" or (p.scheme == "http" and local)):
        return ""
    if "/chat/completions" in p.path:
        return url
    base = url.split("?")[0].rstrip("/")
    return base + "/chat/completions" + (("?" + p.query) if p.query else "")


def detect_provider(key):
    """Best guess from how the key starts: 'anthropic' | 'gemini' | 'openai' | None. Only a suggestion."""
    k = (key or "").strip()
    if k.startswith("sk-ant-"):
        return "anthropic"
    if k.startswith("AIza"):
        return "gemini"
    if k.startswith("sk-") and not k.startswith("sk-or-"):
        return "openai"
    return None


def key_from_env(provider):
    """The provider's key from the environment, the secure store or the private user file (see secrets_store)."""
    import secrets_store
    return secrets_store.get_key(provider)[0]


def build_request(provider, model, system, user, max_tokens=160, base_url=""):
    """-> (url, headers, payload) for one provider."""
    cfg = PROVIDERS[provider]
    url = clean_base_url(base_url) if provider == "custom" else cfg["url"].format(model=urllib.parse.quote(model, safe=""))
    if provider == "custom":
        return url, {}, {"model": model, "max_tokens": max_tokens * 4, "temperature": 0.2,
                         "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
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
        if provider == "custom":
            h["api-key"] = key                 # Azure OpenAI reads the key from this header instead
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _retry_wait(err):
    """How long a 429 asks us to wait. -> (seconds or None, daily_limit_reached). Free tiers allow only a few
    requests per minute: waiting a little is normal; a DAILY quota will not recover during this run."""
    body = ""
    try:
        body = err.read().decode("utf-8", "replace")
    except Exception:
        pass
    daily = bool(re.search(r"PerDay|per day|daily", body, re.I))
    wait = None
    ra = (getattr(err, "headers", None) or {}).get("Retry-After") if getattr(err, "headers", None) else None
    try:
        if ra:
            wait = float(ra)
    except (TypeError, ValueError):
        pass
    if wait is None:
        m = re.search(r'retryDelay"?\s*[:=]\s*"?(\d+(?:\.\d+)?)s', body)
        if m:
            wait = float(m.group(1))
    if wait is None and not daily:
        wait = 30.0                           # no hint given: a typical per-minute window
    return (wait + 1 if wait is not None else None), daily


class AIDrafter:
    def __init__(self, provider="anthropic", api_key=None, model=None, max_calls=150, post=None,
                 verbose=True, report_context="", send_dax=False, base_url=None):
        if provider not in PROVIDERS:
            raise ValueError(f"unknown AI provider {provider!r}; choose one of {', '.join(PROVIDERS)}")
        self.provider = provider
        self.api_key = api_key or key_from_env(provider)
        self.base_url = ""
        if provider == "custom":
            import secrets_store
            st = secrets_store.get_settings("custom")
            self.base_url = base_url or st.get("base_url", "")
            model = model or st.get("model", "")
        self.model_chosen = bool(model)       # a model named by the user is never swapped automatically
        if provider != "custom" and not model:
            import secrets_store
            model = secrets_store.get_settings(provider).get("model") or None
        self.model = model or PROVIDERS[provider]["model"]
        self._tried = {self.model}
        self.max_calls = max_calls
        self.post = post                      # injectable for tests: post(url, headers, payload, key) -> dict
        self.verbose = verbose
        self.report_context = report_context
        self.send_dax = send_dax
        self.calls = self.failures = self.drafted = 0
        self.sleep = time.sleep               # injectable for tests
        self.waited = 0                       # seconds spent waiting for the provider's rate limit
        self.rate_hits = 0                    # consecutive 429s on the current term
        self.dead = False
        self.dead_reason = ""
        self.last_error = ""
        self.label = f"{LABEL} ({provider})"

    @property
    def usable(self):
        if self.provider == "custom" and not (clean_base_url(self.base_url) and self.model):
            return False
        return bool(self.api_key) and not self.dead

    def _next_model(self):
        """After HTTP 404 on a default model name: switch to the next fallback name. -> True if one was found."""
        if self.model_chosen or self.provider == "custom":
            return False
        for m in PROVIDERS[self.provider].get("fallbacks", []):
            if m not in self._tried:
                self._tried.add(m)
                self.model = m
                return True
        return False

    def _disable(self, why):
        self.dead, self.dead_reason, self.last_error = True, why, why
        if self.verbose:
            print(f"  (AI drafting switched off: {why})")

    def _fail(self, why):
        self.last_error = why
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
        url, headers, payload = build_request(self.provider, self.model, SYSTEM, self.facts(term, **ctx), base_url=self.base_url)
        self.calls += 1
        try:
            data = (self.post or (lambda u, h, p, k: _http(u, h, p, k, self.provider)))(url, headers, payload, self.api_key)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                self._disable(f"the key was rejected (HTTP {e.code})")
            elif e.code == 404 and self._next_model():
                self.calls -= 1
                return self.draft(term, **ctx)
            elif e.code == 404:
                self._disable(f"the model name {self.model!r} was not accepted (HTTP 404) -- try --ai-model <name>")
            elif e.code == 429:
                wait, daily = _retry_wait(e)
                self.rate_hits += 1
                if daily or wait is None or wait > 70 or self.rate_hits > 4 or self.waited > 900:
                    self._disable("the provider's " + ("daily " if daily else "") + "usage limit was reached (HTTP 429)"
                                  " -- remaining terms get formula drafts")
                    return None
                if self.verbose:
                    print(f"  (the provider's per-minute limit was reached; waiting {wait:.0f}s, then continuing)")
                self.sleep(wait)
                self.waited += wait
                self.calls -= 1
                return self.draft(term, **ctx)
            else:
                self._fail(f"HTTP {e.code}")
            return None
        except Exception as e:
            self._fail(type(e).__name__)
            return None
        self.failures = 0
        self.rate_hits = 0
        text = re.sub(r"\s+", " ", read_reply(self.provider, data)).strip().strip('"')
        if not text or text.upper().startswith("UNKNOWN") or len(text) < 15:
            self.last_error = self.last_error or "the service answered, but not with a usable definition"
            return None
        self.drafted += 1
        return {"text": text, "origin": self.label}
