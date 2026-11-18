"""Run:  python tests/test_compare_end_to_end.py
Two real runs on the same report, each with its own glossary folder and its own answers, then the test-only Word document
that shows what each run says. (The second run stands in for AI mode: it differs only by an abbreviation answer.)"""
import sys, re, subprocess, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import clarify
from docx import Document

t = Path(tempfile.mkdtemp())
subprocess.run([sys.executable, str(ROOT / "tests" / "make_synthetic_projects.py"), str(t / "syn")], check=True, capture_output=True)
rename = {"Attrition %": "% Unscheduled Jobs", "Headcount": "Admin FTE", "Leavers": "Zorp DL Leavers"}
for f in list((t / "syn" / "hr").rglob("*.tmdl")) + list((t / "syn" / "hr").rglob("*.json")):
    x = f.read_text(encoding="utf-8")
    y = x
    for a, b in rename.items():
        y = y.replace(a, b)
    if y != x:
        f.write_text(y, encoding="utf-8")

def run(tag, *extra):
    r = subprocess.run([sys.executable, str(ROOT / "run.py"), "--no-prompt", "--offline", "--source", str(t / "syn" / "hr"),
                        "--output", str(t / ("out_" + tag)), "--glossary", str(t / ("gl_" + tag) / "glossary.json"), *extra],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr[-800:]
    return r.stdout

def meanings(tag):
    d = Document(str(next((t / ("out_" + tag)).glob("*KPI_Glossary.docx"))))
    return {r.cells[0].text.strip(): r.cells[1].text.strip() for tb in d.tables for r in tb.rows
            if len(r.cells) >= 3 and tb.rows[0].cells[0].text.strip() == "KPI"}

run("offline")
a = meanings("offline")
assert a["% Unscheduled Jobs"].startswith("The percentage of jobs that are not scheduled."), a["% Unscheduled Jobs"]
assert a["Admin FTE"].startswith("Admin full-time equivalent (FTE)"), a["Admin FTE"]

# second run: its own folder, its own answer in its own clarification file
(t / "gl_ai").mkdir()
(t / "gl_ai" / "context.txt").write_text("DL = direct labour\n", encoding="utf-8")
run("ai")                                          # context.txt sits next to the glossary file, so run 2 picks it up
paths, n, changed = __import__("compare_modes").write_all(t / "gl_offline", t / "gl_ai", str(t / "Offline_vs_AI"))
print("terms compared:", n, "different:", changed)
assert n >= 3 and changed >= 1 and Path(paths[0]).exists() and paths[0].endswith(".docx")
text = "\n".join(c.text for tb in Document(paths[0]).tables for r in tb.rows for c in r.cells)
assert "% Unscheduled Jobs" in text and "The percentage of jobs that are not scheduled." in text and "Admin FTE" in text
assert "Source: Draft from the name" in text
# the command a person types
(t / "x").mkdir(exist_ok=True)
r = subprocess.run([sys.executable, str(ROOT / "run.py"), "--compare-glossaries", str(t / "gl_offline"), str(t / "gl_ai"),
                    str(t / "x" / "Test")], capture_output=True, text=True, encoding="utf-8")
assert r.returncode == 0 and (t / "x" / "Test.docx").exists() and "Open the .docx first" in r.stdout, r.stdout[-600:] + r.stderr[-400:]
print("compare end-to-end tests passed")
