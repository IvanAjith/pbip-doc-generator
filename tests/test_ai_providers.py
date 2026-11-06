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
            "openai": {"choices": [{"message": {"content": "Expected win: turnover multiplied by the hold percentage."}}]}}[prov]
for prov in PROVIDERS:
    d = AIDrafter(prov, api_key="K", post=fake, verbose=False, report_context="Casino report; pages: Slots")
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
print("AI provider tests passed")
