"""Run:  python tests/test_clarification.py -- the clarification loop: run -> file lists what is missing -> type answers ->
run again -> answers kept in the glossary, documents rebuilt, file says nothing is needed."""
import sys, csv, re, json, subprocess, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import clarify

t = Path(tempfile.mkdtemp())
subprocess.run([sys.executable, str(ROOT / "tests" / "make_synthetic_projects.py"), str(t / "syn")], check=True, capture_output=True)
tm = next((t / "syn" / "hr").glob("*.SemanticModel/definition/tables/_Measures.tmdl"))
s = tm.read_text(encoding="utf-8")
s2 = re.sub(r"DIVIDE\(\[Leavers\][^\n]*", '"PENDING" & ""', s).replace("Attrition %", "Zorp %")
assert s2 != s
tm.write_text(s2, encoding="utf-8")
for f in (t / "syn" / "hr").rglob("*.json"):
    x = f.read_text(encoding="utf-8")
    if "Attrition %" in x:
        f.write_text(x.replace("Attrition %", "Zorp %"), encoding="utf-8")

def run(*extra):
    r = subprocess.run([sys.executable, str(ROOT / "run.py"), "--no-prompt", "--offline", "--source", str(t / "syn" / "hr"),
                        "--output", str(t / "out"), "--glossary", str(t / "gl" / "glossary.json"), *extra],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr[-800:]
    return r.stdout

out1 = run()
assert "CLARIFICATION NEEDED for 1 indicator(s): Zorp %" in out1, out1[-1500:]
f = t / "out" / clarify.NAME
rows = list(csv.reader(open(f, encoding="utf-8-sig", newline="")))
assert rows[0] == clarify.COLS and rows[1][0] == "Zorp %" and rows[1][5] == "", rows
assert len(list((t / "out").glob("*.docx"))) == 2 and list((t / "out").glob("*.html"))

# the person types the meaning; the same command is run again
rows[1][5] = "The share of staff the business is waiting to place."
csv.writer(open(f, "w", encoding="utf-8-sig", newline="")).writerows(rows)
out2 = run()
assert "picked up 1 definition(s)" in out2 and "No clarification needed" in out2, out2[-1500:]
assert "CLARIFICATION NEEDED" not in out2
rows2 = list(csv.reader(open(f, encoding="utf-8-sig", newline="")))
assert rows2[1][0] == clarify.NONE_TEXT and len(rows2) == 2
saved = json.loads((t / "gl" / "glossary.json").read_text(encoding="utf-8"))["terms"]
assert any(v.get("definition") == "The share of staff the business is waiting to place." and v["source"] == "manual" for v in saved.values())
from docx import Document
txt = "\n".join(c.text for tb in Document(str(next((t / "out").glob("*KPI_Glossary.docx")))).tables for r in tb.rows for c in r.cells)
assert "waiting to place" in txt
man = "\n".join(p.text for p in Document(str(next((t / "out").glob("*User_Manual.docx")))).paragraphs)
# a third run keeps it without asking again
out3 = run()
assert "No clarification needed" in out3

# --clarify-drafts lists the drafts too, and 'ok' accepts one
out4 = run("--clarify-drafts")
rows4 = list(csv.reader(open(f, encoding="utf-8-sig", newline="")))
assert len(rows4) > 1 and rows4[1][2].startswith("Draft") and rows4[1][4], rows4[:2]
rows4[1][5] = "ok"
accepted = rows4[1][4]; term = rows4[1][0]
csv.writer(open(f, "w", encoding="utf-8-sig", newline="")).writerows(rows4)
run("--clarify-drafts")
saved = json.loads((t / "gl" / "glossary.json").read_text(encoding="utf-8"))["terms"]
assert any(v.get("definition") == accepted and v["source"] == "manual" for v in saved.values()), term
print("clarification loop tests passed")
