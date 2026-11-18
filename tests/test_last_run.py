"""Run:  python tests/test_last_run.py -- python run.py carries on in the last mode while clarification questions are waiting,
and asks the mode again only when everything is finished."""
import os, sys, re, json, subprocess, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import last_run

# --- the note
t = Path(tempfile.mkdtemp())
p = last_run.path_for(t / "gl" / "glossary.json")
assert p == t / "gl" / "last_run.json" and last_run.read(p) is None and last_run.resume(p) is None
last_run.write(p, "ai", "gemini", 3)
assert last_run.resume(p)["mode"] == "ai" and last_run.resume(p)["provider"] == "gemini" and "key" not in p.read_text(encoding="utf-8").lower()
last_run.write(p, "ai", "gemini", 0)
assert last_run.read(p)["mode"] == "ai" and last_run.resume(p) is None            # finished: ask again next time
p.write_text("not json", encoding="utf-8"); assert last_run.read(p) is None

# --- resuming AI mode uses the saved key (nothing is typed)
home = t / "home"
env0 = dict(PBIP_DOC_GENERATOR_HOME=str(home), PBIP_DOC_GENERATOR_NO_KEYRING="1")
os.environ.update(env0)
for v in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "AI_API_KEY", "AI_BASE_URL", "AI_MODEL"):
    os.environ.pop(v, None)
import ai_setup, secrets_store as S
msgs = []
assert ai_setup.resume_ai("custom", out=msgs.append) is None and any("not saved" in m for m in msgs)
def fake(url, headers, payload, key):
    return {"choices": [{"message": {"content": "The amount a game is expected to win over time."}}]}
KEY = "gsk_FAKEKEY0123456789abcdefghijkl"
it = iter(["4", "https://api.groq.com/openai/v1", "llama-x"])
assert ai_setup.setup(None, ask=lambda prompt="": next(it), ask_secret=lambda p="": KEY, post=fake, out=lambda *_: None)
r = ai_setup.resume_ai("custom", post=fake, out=msgs.append)
assert r and r["mode"] == "ai" and r["provider"] == "custom" and r["key"] == KEY and r["settings"]["model"] == "llama-x"
def broken(url, headers, payload, key):
    raise RuntimeError("401")
msgs.clear(); assert ai_setup.resume_ai("custom", post=broken, out=msgs.append) is None and any("did not work" in m for m in msgs)

# --- a whole python run.py in a real terminal (Linux/macOS only; Windows has no pty)
try:
    import pty
except ImportError:
    print("last run tests passed (pty not available: terminal part skipped)"); sys.exit(0)
subprocess.run([sys.executable, str(ROOT / "tests" / "make_synthetic_projects.py"), str(t / "syn")], check=True, capture_output=True)
for f in list((t / "syn" / "hr").rglob("*.tmdl")) + list((t / "syn" / "hr").rglob("*.json")):
    x = f.read_text(encoding="utf-8"); y = x.replace("Attrition %", "Zorp CB %")
    if y != x: f.write_text(y, encoding="utf-8")

def tty_run(typed):
    m, s = pty.openpty()
    cmd = [sys.executable, str(ROOT / "run.py"), "--source", str(t / "syn" / "hr"), "--output", str(t / "out"), "--glossary", str(t / "gl" / "glossary.json")]
    proc = subprocess.Popen(cmd, stdin=s, stdout=s, stderr=s, close_fds=True, env=dict(os.environ))
    os.close(s)
    for line in typed:
        os.write(m, (line + "\n").encode())
    out, end = b"", time.time() + 150
    import select
    while time.time() < end:
        if not select.select([m], [], [], 1)[0]:
            if proc.poll() is not None:
                break
            continue
        try:
            chunk = os.read(m, 65536)
        except OSError:
            break
        if not chunk:
            break
        out += chunk
    if proc.poll() is None:
        proc.kill()
        raise AssertionError("run.py waited for input it should not have needed:\n" + out.decode("utf-8", "replace")[-1200:])
    proc.wait()
    os.close(m)
    return out.decode("utf-8", "replace"), proc.returncode

out1, rc = tty_run(["2"])                              # first run: the question is asked, answer 2 = offline
assert rc == 0 and "Do you have an AI API key?" in out1 and "CLARIFICATION NEEDED" in out1, out1[-1500:]
assert last_run.resume(t / "gl" / "last_run.json")["mode"] == "offline"
out2, rc = tty_run([])                                  # second run: nothing is asked, it carries on in offline mode
assert rc == 0 and "Do you have an AI API key?" not in out2 and "Carrying on in offline mode" in out2, out2[-1500:]
# answer everything, run again: it finishes and says so
f = t / "out" / "Needs_Your_Clarification.txt"
body = f.read_text(encoding="utf-8")
body = re.sub(r"(\[A\d+\] CB\n.*\n>>> )", r"\1comeback", body)
body = re.sub(r"(\[K\d+\] [^\n]*\n[^\n]*\n[^\n]*\n[^\n]*\n>>> )", r"\1A made up meaning for the test.", body)
f.write_text(body, encoding="utf-8")
out3, rc = tty_run([])
assert rc == 0 and "Carrying on in offline mode" in out3 and "No clarification needed" in out3 and "asked the mode again" in out3, out3[-1500:]
out4, rc = tty_run(["2"])                               # finished: next run asks again
assert "Do you have an AI API key?" in out4 and "Carrying on" not in out4
print("last run tests passed")
