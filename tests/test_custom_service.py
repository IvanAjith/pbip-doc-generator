"""Run:  python tests/test_custom_service.py   (no network). Keys from any OpenAI-compatible service, and key recognition."""
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
tmp = Path(tempfile.mkdtemp())
os.environ["PBIP_DOC_GENERATOR_HOME"] = str(tmp / "home")
os.environ["PBIP_DOC_GENERATOR_NO_KEYRING"] = "1"
for v in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "AI_API_KEY", "AI_BASE_URL", "AI_MODEL"):
    os.environ.pop(v, None)
import ai_setup, secrets_store as S
from ai_draft import AIDrafter, build_request, clean_base_url, detect_provider, SYSTEM

# key recognition is only a suggestion
assert detect_provider("sk-ant-api03-xxxxxxxxxxxxxxxxxxxx") == "anthropic"
assert detect_provider("AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX") == "gemini"
assert detect_provider("sk-proj-xxxxxxxxxxxxxxxxxxxxxxxx") == "openai" and detect_provider("sk-xxxxxxxxxxxxxxxxxxxxxxxx") == "openai"
assert detect_provider("sk-or-v1-xxxxxxxxxxxxxxxxxxxx") is None and detect_provider("gsk_xxxxxxxxxxxxxxxxxxxx") is None and detect_provider("") is None

# web addresses: https only (plain http only on this computer); the chat path is added when missing
assert clean_base_url("https://api.groq.com/openai/v1") == "https://api.groq.com/openai/v1/chat/completions"
assert clean_base_url("https://api.groq.com/openai/v1/") == "https://api.groq.com/openai/v1/chat/completions"
assert clean_base_url("https://x.com/v1/chat/completions") == "https://x.com/v1/chat/completions"
az = "https://res.openai.azure.com/openai/deployments/d1/chat/completions?api-version=2024-02-01"
assert clean_base_url(az) == az
assert clean_base_url("https://res.openai.azure.com/openai/deployments/d1?api-version=2024-02-01").endswith("/d1/chat/completions?api-version=2024-02-01")
assert clean_base_url("http://localhost:11434/v1") == "http://localhost:11434/v1/chat/completions"
assert clean_base_url("http://evil.example.com/v1") == "" and clean_base_url("ftp://x.com") == "" and clean_base_url("nonsense") == ""

u, h, p = build_request("custom", "m", SYSTEM, "hi", base_url="https://api.groq.com/openai/v1")
assert u.endswith("/chat/completions") and p["model"] == "m" and p["messages"][1]["content"] == "hi"

# an 'Other' drafter needs both web address and model; with them it works through a fake service
assert not AIDrafter("custom", api_key="k" * 30, verbose=False).usable
seen = []
def fake(url, headers, payload, key):
    seen.append((url, key)); return {"choices": [{"message": {"content": "The amount a game is expected to win over time."}}]}
d = AIDrafter("custom", api_key="k" * 30, base_url="https://api.groq.com/openai/v1", model="llama-x", post=fake, verbose=False)
assert d.usable and d.draft("Theoretical Win", calc="Turnover multiplied by Hold %") and seen[0][0].startswith("https://api.groq.com/")

def scripted(a):
    it = iter(a); return lambda prompt="": next(it)

# guided setup for an unrecognised key: asks the service, then web address and model, tests, saves
KEY = "gsk_FAKEKEY0123456789abcdefghijkl"
buf = []
ok = ai_setup.setup(None, ask=scripted(["4", "https://api.groq.com/openai/v1", "llama-x"]), ask_secret=lambda p="": KEY, post=fake, out=buf.append)
assert ok and S.get_key("custom")[0] == KEY and KEY not in "\n".join(buf)
assert S.get_settings("custom") == {"base_url": "https://api.groq.com/openai/v1", "model": "llama-x"}
# the saved settings are found by a fresh drafter, and the status shows host and model but never the key
assert AIDrafter("custom", verbose=False, post=fake).usable
buf = []; ai_setup.show_status(out=buf.append); t = "\n".join(buf)
assert "api.groq.com" in t and "llama-x" in t and "FAKEKEY" not in t
# the start-up question accepts it too (saved key offered, Enter uses it)
r = ai_setup.choose_mode(ask=scripted(["1", ""]), post=fake, out=lambda *_: None)
assert r["provider"] == "custom" and r["settings"]["model"] == "llama-x"
# a bad web address is refused before any key is sent
S.delete_key("custom")
seen.clear()
ok = ai_setup.setup(None, ask=scripted(["4", "http://evil.example.com", "y", "4", "http://evil.example.com", "y", "4", "http://evil.example.com", "n"]),
                    ask_secret=lambda p="": KEY, post=fake, out=lambda *_: None)
assert not ok and not seen and S.get_key("custom")[0] == ""
# an "sk-" key that is not OpenAI's: the test fails as OpenAI, the tool offers 'different service' and succeeds as Other
import urllib.error
def only_groq(url, headers, payload, key):
    if "api.openai.com" in url:
        raise urllib.error.HTTPError(url, 401, "no", {}, None)
    return fake(url, headers, payload, key)
K2 = "sk-DEEPSEEKFAKE0123456789abcdefgh"
buf = []
ok = ai_setup.setup(None, ask=scripted(["y", "https://api.deepseek.com/v1", "deepseek-chat"]), ask_secret=lambda p="": K2, post=only_groq, out=buf.append)
assert ok and S.get_key("custom")[0] == K2 and S.get_settings("custom")["model"] == "deepseek-chat" and K2 not in "\n".join(buf)
S.delete_key("custom")
# forgetting removes key and settings
S.save_key("custom", KEY); S.save_settings("custom", base_url="https://a.example.com/v1", model="m")
assert S.delete_key("custom") and S.get_settings("custom") == {"base_url": "", "model": ""}
print("ALL CUSTOM-SERVICE TESTS PASSED")
