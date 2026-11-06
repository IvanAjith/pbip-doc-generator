"""Run:  python tests/test_menu.py   (no network). The question asked when run.py starts with no options."""
import builtins, contextlib, getpass, io, os, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
tmp = Path(tempfile.mkdtemp())
os.environ["PBIP_DOC_GENERATOR_HOME"] = str(tmp / "home")
os.environ["PBIP_DOC_GENERATOR_NO_KEYRING"] = "1"
for v in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"):
    os.environ.pop(v, None)
import ai_setup, secrets_store as S, ai_draft

KEY = "AIzaFAKEKEY0123456789abcdefghijkl"
GOOD = lambda u, h, p, k: {"candidates": [{"content": {"parts": [{"text": "The amount a game is expected to win over time."}]}}]}

def scripted(a):
    it = iter(a); return lambda prompt="": next(it)

# option 2 -> offline
assert ai_setup.choose_mode(ask=scripted(["x", "2"]), out=lambda *_: None) == {"mode": "offline"}
# option 1, new key, test passes, saved
buf = []
r = ai_setup.choose_mode(ask=scripted(["1", "y"]), ask_secret=lambda p="": " " + KEY + " ", post=GOOD, out=buf.append)
assert (r["provider"], r["key"]) == ("gemini", KEY) and S.get_key("gemini")[0] == KEY
assert KEY not in "\n".join(buf), "the key was printed"
# next time: saved key offered, Enter uses it, no paste needed
r = ai_setup.choose_mode(ask=scripted(["1", ""]), ask_secret=lambda p="": 1 / 0, post=GOOD, out=lambda *_: None)
assert r["key"] == KEY
# ... or N to type another, and 'n' to not save it
S.delete_key("gemini")
r = ai_setup.choose_mode(ask=scripted(["1", "n"]), ask_secret=lambda p="": "sk-ant-OTHERKEY0123456789abcdefgh",
                         post=lambda u, h, p, k: {"content": [{"type": "text", "text": "The amount a game is expected to win over time."}]}, out=lambda *_: None)
assert r["provider"] == "anthropic" and S.get_key("anthropic")[0] == "", "key saved although the user said n"
# a rejected key -> asked whether to continue offline; yes = offline, no = stop with a message
import urllib.error
def bad(u, h, p, k): raise urllib.error.HTTPError(u, 401, "no", {}, None)
OAI = "sk-OPENAIFAKE0123456789abcdefgh"
buf = []
r = ai_setup.choose_mode(ask=scripted(["1", "n", "y"]), ask_secret=lambda p="": OAI, post=bad, out=buf.append)
assert r == {"mode": "offline"} and "rejected" in "\n".join(buf) and S.get_key("openai")[0] == "" and OAI not in "\n".join(buf)
buf = []
r = ai_setup.choose_mode(ask=scripted(["1", "n", "n"]), ask_secret=lambda p="": OAI, post=bad, out=buf.append)
assert r == {"mode": "stop"} and "Invalid API key" in "\n".join(buf) and "python run.py" in "\n".join(buf)
r = ai_setup.choose_mode(ask=scripted(["1", "y"]), ask_secret=lambda p="": "sk-ant-BADKEY0123456789abcdefghij", post=bad, out=lambda *_: None)
assert r == {"mode": "offline"}
# a key that is too short is treated the same way
r = ai_setup.choose_mode(ask=scripted(["1", "n"]), ask_secret=lambda p="": "abc", post=GOOD, out=lambda *_: None)
assert r == {"mode": "stop"}
# a saved key that stops working is not silently used
S.save_key("gemini", KEY)
r = ai_setup.choose_mode(ask=scripted(["1", "", "n"]), post=bad, out=lambda *_: None)
assert r == {"mode": "stop"}
S.delete_key("gemini")

# ---- the whole program, as a colleague would start it: python run.py  (keyboard session)
sys.path.insert(0, str(ROOT / "tests"))
import subprocess
subprocess.run([sys.executable, str(ROOT / "tests/make_synthetic_projects.py"), str(tmp / "synth")], check=True, capture_output=True)
import run
def go(answers, secret=KEY, http=None):
    out = tmp / ("out%d" % len(list(tmp.glob("out*"))))
    argv = ["run.py", "--source", str(tmp / "synth/gaming"), "--output", str(out), "--glossary", str(out.parent / ("g%s/glossary.json" % out.name))]
    it = iter(answers)
    saved = (sys.argv, sys.stdin, builtins.input, getpass.getpass, ai_draft._http)
    class TTY(io.StringIO):
        def isatty(self): return True
    sys.argv, sys.stdin = argv, TTY()
    builtins.input, getpass.getpass = (lambda p="": next(it)), (lambda p="": secret)
    if http: ai_draft._http = http
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            run.main()
    finally:
        sys.argv, sys.stdin, builtins.input, getpass.getpass, ai_draft._http = saved
    return buf.getvalue(), out

text, out = go(["2"])
assert "Offline mode" in text and len(list(out.glob("*"))) == 3, text[-500:]
calls = []
def http(url, headers, payload, key, provider=None, timeout=40):
    calls.append(key); return GOOD(url, headers, payload, key)
ai_draft._http_real = ai_draft._http
text, out = go(["1", "n"], http=lambda u, h, p, k, *a, **kw: http(u, h, p, k))
assert len(list(out.glob("*"))) == 3 and calls and set(calls) == {KEY}, text[-600:]
assert KEY not in text and S.get_key("gemini")[0] == "", "key leaked or saved"
assert "AI mode on" in text
# the whole program with a wrong key and "no": exit code 1, no documents
before = len(list(tmp.glob("out*")))
try:
    go(["1", "n", "n"], secret="sk-ant-WRONGKEY0123456789abcdefgh", http=lambda u, h, p, k, *a, **kw: bad(u, h, p, k))
    raise AssertionError("program did not stop")
except SystemExit as e:
    assert e.code == 1
assert len(list(tmp.glob("out*"))) == before, "an output folder was created after a rejected key"
# no keyboard (automation): no question is asked
r = subprocess.run([sys.executable, str(ROOT / "run.py"), "--offline", "--source", str(tmp / "synth/gaming"), "--output", str(tmp / "o9"),
                    "--glossary", str(tmp / "g9/glossary.json")], capture_output=True, text=True, stdin=subprocess.DEVNULL)
assert r.returncode == 0 and "How should the glossary" not in r.stdout
print("ALL MENU TESTS PASSED")
