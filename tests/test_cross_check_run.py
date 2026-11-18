"""Run:  python tests/test_cross_check_run.py -- a whole --ai run with a stand-in AI service (no network): the invented
wording is replaced, the doubtful one is asked about in the clarification file, and the review notes say what happened."""
import sys, os, subprocess, tempfile, json, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
t = Path(tempfile.mkdtemp())
subprocess.run([sys.executable, str(ROOT / "tests" / "make_synthetic_projects.py"), str(t / "syn")], check=True, capture_output=True)
for f in list((t / "syn" / "hr").rglob("*.tmdl")) + list((t / "syn" / "hr").rglob("*.json")):
    x = f.read_text(encoding="utf-8"); y = x.replace("Attrition %", "Zorp Rate %").replace("Headcount", "Admin Heads")
    if y != x: f.write_text(y, encoding="utf-8")

class H(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        prompt = json.dumps(body)
        text = "Staff counted by a barcode reader at the gate." if "Admin Heads" in prompt else "UNKNOWN" if "Zorp" in prompt else "A measure shown on the page."
        out = json.dumps({"choices": [{"message": {"content": text}}]}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)
    def log_message(self, *a): pass
srv = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
env = dict(os.environ, PBIP_DOC_GENERATOR_HOME=str(t / "home"), PBIP_DOC_GENERATOR_NO_KEYRING="1", AI_API_KEY="k" * 30,
           AI_BASE_URL=f"http://127.0.0.1:{srv.server_port}/v1", AI_MODEL="m")
r = subprocess.run([sys.executable, str(ROOT / "run.py"), "--no-prompt", "--ai", "--offline", "--source", str(t / "syn" / "hr"), "--output", str(t / "out"),
                    "--glossary", str(t / "gl" / "glossary.json")], capture_output=True, text=True, encoding="utf-8", env=env)
out = r.stdout + r.stderr
assert r.returncode == 0, out[-1500:]
assert "Cross-check of the AI drafts" in out, out[-2500:]
import csv
rows = list(csv.DictReader(open(t / "gl" / "my_definitions.csv", encoding="utf-8-sig")))
by = {x["Term"]: x for x in rows}
assert "barcode" not in by["Admin Heads"]["Suggested definition"] and "barcode" in by["Admin Heads"]["Where the suggestion came from"], by["Admin Heads"]
print("cross-check run tests passed")
