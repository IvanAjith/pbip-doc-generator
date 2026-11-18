"""Run:  python tests/test_compare_test.py -- compare_test.py: one command does the offline run, the AI run (stand-in service) and the
comparison; an answer typed in one clarification file is used by both runs on the next command."""
import sys, os, re, subprocess, tempfile, json, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
t = Path(tempfile.mkdtemp())
subprocess.run([sys.executable, str(ROOT / "tests" / "make_synthetic_projects.py"), str(t / "syn")], check=True, capture_output=True)
for f in list((t / "syn" / "hr").rglob("*.tmdl")) + list((t / "syn" / "hr").rglob("*.json")):
    x = f.read_text(encoding="utf-8"); y = x.replace("Attrition %", "Zorp CB %")
    if y != x: f.write_text(y, encoding="utf-8")

class H(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        out = json.dumps({"choices": [{"message": {"content": "A measure that is shown on this page."}}]}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)
    def log_message(self, *a): pass
srv = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
env = dict(os.environ, PBIP_DOC_GENERATOR_HOME=str(t / "home"), PBIP_DOC_GENERATOR_NO_KEYRING="1", AI_API_KEY="k" * 30,
           AI_BASE_URL=f"http://127.0.0.1:{srv.server_port}/v1", AI_MODEL="m")

def go():
    r = subprocess.run([sys.executable, str(ROOT / "compare_test.py"), "--source", str(t / "syn" / "hr"), "--folder", str(t / "ct")],
                       capture_output=True, text=True, encoding="utf-8", env=env)
    assert r.returncode == 0, (r.stdout + r.stderr)[-2000:]
    return r.stdout

out1 = go()
ct = t / "ct"
assert (ct / "Offline_vs_AI.docx").exists() and "OFFLINE RUN" in out1 and "AI RUN" in out1 and "Open this first" in out1, out1[-1500:]
for k in ("offline", "ai"):
    assert len(list((ct / k / "output").glob("*User_Manual.docx"))) == 1 and (ct / k / "glossary" / "my_definitions.csv").exists(), k
assert "CLARIFICATION NEEDED" in out1 and "Needs_Your_Clarification.txt" in out1, out1[-800:]

# answer the abbreviation in the OFFLINE file only
f = ct / "offline" / "output" / "Needs_Your_Clarification.txt"
body = f.read_text(encoding="utf-8")
assert re.search(r"\[A\d+\] CB", body), body[:1500]
f.write_text(re.sub(r"(\[A\d+\] CB\n.*\n>>> )", r"\1comeback", body, count=1), encoding="utf-8")
out2 = go()
# the AI run used it too, and both context files carry it
for k in ("offline", "ai"):
    ctx = (ct / k / "glossary" / "context.txt").read_text(encoding="utf-8")
    assert "CB = comeback" in ctx, (k, ctx)
assert "CB" not in "".join(re.findall(r"\[A\d+\] (\w+)", (ct / "ai" / "output" / "Needs_Your_Clarification.txt").read_text(encoding="utf-8")))
print("compare_test tests passed")
