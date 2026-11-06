"""Run:  python tests/test_secrets.py   (no network). Key storage, masking, guided setup, and that keys never reach output."""
import os, sys, stat, tempfile, json, io, contextlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

tmp = Path(tempfile.mkdtemp())
os.environ["PBIP_DOC_GENERATOR_HOME"] = str(tmp / "home")
os.environ["PBIP_DOC_GENERATOR_NO_KEYRING"] = "1"          # test the private-file route, not the OS store
for v in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"):
    os.environ.pop(v, None)

import secrets_store as S
import ai_setup
from ai_draft import AIDrafter

KEY = "sk-ant-TESTKEY0123456789abcdefWXYZ"

assert S.get_key("anthropic") == ("", None) and S.status() == []
where = S.save_key("anthropic", KEY)
assert "private file" in where
assert S.get_key("anthropic")[0] == KEY and S.default_provider() == "anthropic"
cfg = S.home_dir() / "config.json"
if os.name == "posix":
    assert stat.S_IMODE(cfg.stat().st_mode) == 0o600, oct(cfg.stat().st_mode)       # only the owner can read it
    assert stat.S_IMODE(S.home_dir().stat().st_mode) == 0o700
assert S.mask(KEY) == "...WXYZ" and KEY not in repr(S.status())

# the environment variable wins over the saved file
os.environ["ANTHROPIC_API_KEY"] = "env-key-0123456789abcdefghij"
assert S.get_key("anthropic")[0].startswith("env-key") and "environment" in S.get_key("anthropic")[1]
os.environ.pop("ANTHROPIC_API_KEY")
# AIDrafter finds the saved key by itself
assert AIDrafter("anthropic", verbose=False).api_key == KEY

# delete
assert S.delete_key("anthropic") and S.get_key("anthropic")[0] == "" and S.default_provider() is None
assert not S.delete_key("anthropic")


def fake_ok(url, headers, payload, key):
    return {"content": [{"type": "text", "text": "The amount a game is expected to win over time."}]}

def fake_bad(url, headers, payload, key):
    import urllib.error
    raise urllib.error.HTTPError(url, 401, "no", {}, None)

def scripted(answers):
    it = iter(answers)
    return lambda prompt="": next(it)

# guided setup: success saves, output never shows the key
buf = []
ok = ai_setup.setup(None, ask=scripted([""]), ask_secret=lambda p="": "  AIzaFAKEKEY0123456789abcdefghijkl ", post=lambda u, h, p, k: {
    "candidates": [{"content": {"parts": [{"text": "Expected win over time."}]}}]}, out=buf.append)
assert ok and S.get_key("gemini")[0] == "AIzaFAKEKEY0123456789abcdefghijkl" and S.default_provider() == "gemini"
assert "AIzaFAKEKEY" not in "\n".join(buf), "setup printed the key"

# a rejected key is not saved
S.delete_key("gemini")
buf = []
ok = ai_setup.setup("anthropic", ask=scripted(["2"]), ask_secret=lambda p="": KEY, post=fake_bad, out=buf.append)
assert not ok and S.get_key("anthropic")[0] == "" and KEY not in "\n".join(buf)
# junk input is refused
assert not ai_setup.setup("openai", ask=scripted([]), ask_secret=lambda p="": "abc", post=fake_ok, out=lambda *_: None)
assert not ai_setup.setup(None, ask=scripted(["9", "9", "9"]), ask_secret=lambda p="": "z" * 30, out=lambda *_: None)

# status and forget never show the whole key
S.save_key("openai", "sk-openaiFAKE0123456789ABCD")
buf = []
ai_setup.show_status(out=buf.append)
text = "\n".join(buf)
assert "...ABCD" in text and "openaiFAKE" not in text
buf = []
ai_setup.forget(out=buf.append)
assert S.get_key("openai")[0] == "" and "Removed" in "\n".join(buf)

# run.py --ai-status / --setup-ai plumbing works as a command (no key set -> friendly message)
import subprocess
env = dict(os.environ)
r = subprocess.run([sys.executable, str(Path(__file__).resolve().parent.parent / "run.py"), "--ai-status"],
                   capture_output=True, text=True, env=env)
assert r.returncode == 0 and "No AI key is set up" in r.stdout, r.stdout + r.stderr
print("ALL SECRETS TESTS PASSED")
