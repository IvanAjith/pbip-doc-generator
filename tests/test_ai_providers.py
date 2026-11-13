"""Run:  python tests/test_ai_providers.py   (no network). Checks the request each provider receives and that each
provider's reply format is read correctly. The real services could not be reached while building this."""
import sys, json, urllib.error, io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ai_draft import AIDrafter, build_request, read_reply, PROVIDERS, SYSTEM

# --- request shapes
u, h, p = build_request("anthropic", "m1", SYSTEM, "hello")
assert u.endswith("/v1/messages") and h["anthropic-version"] and p["system"] == SYSTEM and p["messages"][0]["content"] == "hello"
u, h, p = build_request("gemini", "gemini-x", SYSTEM, "hello")
assert u.endswith("/models/gemini-x:generateContent") and p["contents"][0]["parts"][0]["text"] == "hello" \
    and p["system_instruction"]["parts"][0]["text"] == SYSTEM
u, h, p = build_request("openai", "gpt-x", SYSTEM, "hello")
assert u.endswith("/chat/completions") and p["messages"][0]["role"] == "system" and p["messages"][1]["content"] == "hello"

# --- reply shapes
assert read_reply("anthropic", {"content": [{"type": "text", "text": "A."}]}) == "A."
assert read_reply("gemini", {"candidates": [{"content": {"parts": [{"text": "B"}, {"text": "."}]}}]}) == "B."
assert read_reply("openai", {"choices": [{"message": {"content": "C."}}]}) == "C."
for prov in PROVIDERS:
    assert read_reply(prov, {}) == "" and read_reply(prov, {"error": "x"}) == ""        # unexpected shapes never crash
assert read_reply("gemini", {"candidates": [{"finishReason": "SAFETY"}]}) == ""

# --- end to end per provider with a fake transport; the key travels, the DAX only when allowed
seen = []
def fake(url, headers, payload, key):
    seen.append((url, headers, payload, key))
    return {"anthropic": {"content": [{"type": "text", "text": "Expected win: turnover multiplied by the hold percentage."}]},
            "gemini": {"candidates": [{"content": {"parts": [{"text": "Expected win: turnover multiplied by the hold percentage."}]}}]},
            "openai": {"choices": [{"message": {"content": "Expected win: turnover multiplied by the hold percentage."}}]},
            "custom": {"choices": [{"message": {"content": "Expected win: turnover multiplied by the hold percentage."}}]}}[prov]
for prov in PROVIDERS:
    extra = dict(base_url="https://gateway.example.com/v1", model="m1") if prov == "custom" else {}
    d = AIDrafter(prov, api_key="K", post=fake, verbose=False, report_context="Casino report; pages: Slots", **extra)
    r = d.draft("Theoretical Win", calc="Turnover multiplied by Hold %", page="Slots", dax="Turnover * [Hold %]", kind="value")
    assert r and r["text"].startswith("Expected win") and prov in r["origin"], r
    blob = json.dumps(seen[-1][2])
    assert "Theoretical Win" in blob and "Casino report" in blob and "Turnover * [Hold %]" not in blob   # DAX not sent by default
    assert seen[-1][3] == "K"
d = AIDrafter("gemini", api_key="K", post=fake, verbose=False, send_dax=True)
prov = "gemini"; d.draft("X Y", calc="a", dax="Turnover * [Hold %]")
assert "Turnover * [Hold %]" in json.dumps(seen[-1][2])

# --- failure handling
def http(code):
    def f(*a): raise urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(b""))
    return f
for code, dead in ((401, True), (404, True), (429, True), (500, False)):
    d = AIDrafter("openai", api_key="K", post=http(code), verbose=False)
    d.draft("Term One")
    assert d.dead == dead, code
try:
    AIDrafter("nope"); raise SystemExit("unknown provider accepted")
except ValueError:
    pass
# --- Gemini: a retired/closed default model name falls through to the next one (HTTP 404), a chosen one does not
import os, tempfile
os.environ["PBIP_DOC_GENERATOR_HOME"] = tempfile.mkdtemp()
used = []
def only(good):
    def f(url, h, p, k):
        used.append(url)
        if good not in url:
            raise urllib.error.HTTPError(url, 404, "x", {}, io.BytesIO(b""))
        return {"candidates": [{"content": {"parts": [{"text": "A measure of how much was earned in the period."}]}}]}
    return f
d = AIDrafter("gemini", api_key="K", post=only("gemini-3.8-flash"), verbose=False)
r = d.draft("Theoretical Win")
assert r and d.model == "gemini-3.8-flash" and not d.dead, (r, d.model)
assert d.calls == 1                                   # the retries are not counted as extra calls
d = AIDrafter("gemini", api_key="K", post=only("gemini-3.8-flash"), verbose=False, model="gemini-old")
assert d.draft("Theoretical Win") is None and d.dead   # the user's own model name is never swapped
d = AIDrafter("gemini", api_key="K", post=only("nothing-matches"), verbose=False)
assert d.draft("Theoretical Win") is None and d.dead   # every name tried -> switched off with the 404 message
import ai_setup
st = {}
sample, why = ai_setup._test("gemini", "K" * 30, st, only("gemini-3.6-flash"))
assert sample and st.get("model") == "gemini-3.6-flash", (sample, st)   # the working name is remembered
print("ok: Gemini model fallback")
print("AI provider tests passed")
