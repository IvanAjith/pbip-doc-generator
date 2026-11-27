"""Run:  python tests/test_clarification.py -- the clarification loop: run -> the file asks what is missing (abbreviations and KPI meanings)
-> type answers -> run again -> answers kept (context.txt and the glossary file), documents rebuilt without yellow, file says nothing is needed."""
import sys, re, json, subprocess, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import clarify
from docx import Document

t = Path(tempfile.mkdtemp())
subprocess.run([sys.executable, str(ROOT / "tests" / "make_synthetic_projects.py"), str(t / "syn")], check=True, capture_output=True)
tm = next((t / "syn" / "hr").glob("*.SemanticModel/definition/tables/_Measures.tmdl"))
s = tm.read_text(encoding="utf-8")
s2 = re.sub(r"DIVIDE\(\[Leavers\][^\n]*", '"PENDING" & ""', s)          # a measure nobody can define from its formula
s2 = s2.replace("Attrition %", "Zorp CB %").replace("Headcount", "WO Headcount")
assert s2 != s
tm.write_text(s2, encoding="utf-8")
for f in (t / "syn" / "hr").rglob("*.json"):
    x = f.read_text(encoding="utf-8")
    if "Attrition %" in x or "Headcount" in x:
        f.write_text(x.replace("Attrition %", "Zorp CB %").replace("Headcount", "WO Headcount"), encoding="utf-8")

def run(*extra, skip=True):
    r = subprocess.run([sys.executable, str(ROOT / "run.py"), "--no-prompt", "--offline", "--source", str(t / "syn" / "hr"),
                        "--output", str(t / "out"), "--glossary", str(t / "gl" / "glossary.json"), *(["--skip-drafts"] if skip else []), *extra],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr[-800:]
    return r.stdout

def glossary_text():
    d = Document(str(next((t / "out").glob("*KPI_Glossary.docx"))))
    return "\n".join(c.text for tb in d.tables for r in tb.rows for c in r.cells)

def yellow(path):
    x = Document(str(path)).element.xml
    return len(re.findall(r'w:fill="(?:FFE699|FFF2CC)"', x))

out1 = run()
assert "CLARIFICATION NEEDED" in out1 and "abbreviation(s)" in out1 and "Zorp CB %" in out1, out1[-1500:]
f = t / "out" / clarify.NAME
body = f.read_text(encoding="utf-8")
assert "PART 1" in body and "[A1] CB" in body and "[A2] WO" in body and "[K1] Zorp CB %" in body, body
assert yellow(next((t / "out").glob("*KPI_Glossary.docx"))) >= 1                 # the unanswered KPI is flagged
assert len(list((t / "out").glob("*.docx"))) == 2 and list((t / "out").glob("*.html"))

# the person answers; the same command is run again
body = body.replace("[A1] CB\n     seen in: Zorp CB %\n>>> ", "[A1] CB\n     seen in: Zorp CB %\n>>> comeback, a job sent back by the customer")
body = re.sub(r"(\[A2\] WO\n.*\n>>> )", r"\1work order", body)
body = body.replace("No definition was found for this one.\n>>> ", "No definition was found for this one.\n>>> The share of jobs that came back as claims.\n")
f.write_text(body, encoding="utf-8")
out2 = run()
assert "picked up from" in out2 and "No clarification needed" in out2 and "CLARIFICATION NEEDED" not in out2, out2[-1500:]
assert "NO CLARIFICATION NEEDED" in f.read_text(encoding="utf-8") and "[K1]" not in f.read_text(encoding="utf-8")
ctx = (t / "gl" / "context.txt").read_text(encoding="utf-8")
assert "CB = comeback, a job sent back by the customer" in ctx and "WO = work order" in ctx, ctx
saved = json.loads((t / "gl" / "glossary.json").read_text(encoding="utf-8"))["terms"]
assert any(v.get("definition") == "The share of jobs that came back as claims." and v["source"] == "manual" for v in saved.values())
txt = glossary_text()
assert "The share of jobs that came back as claims." in txt
assert "Here, WO means work order." in txt                                        # drafts that use an explained abbreviation say so
assert yellow(next((t / "out").glob("*KPI_Glossary.docx"))) == 0 and yellow(next((t / "out").glob("*User_Manual.docx"))) == 0, "yellow left over"
assert "No clarification needed" in run()                                         # stays quiet on the next run

# the default (no --skip-drafts) asks about the drafts too, and OK keeps one
run(skip=False)
body = f.read_text(encoding="utf-8")
assert "draft:" in body and "[K1]" in body, body
m = re.search(r"\[K1\] (.+)\n.*\n.*\n     draft: (.+)\n", body)
term, draft = m.group(1), m.group(2)
f.write_text(body.replace("Type OK to keep this draft, or write your own wording.\n>>> ", "Type OK to keep this draft, or write your own wording.\n>>> OK\n", 1), encoding="utf-8")
run(skip=False)
saved = json.loads((t / "gl" / "glossary.json").read_text(encoding="utf-8"))["terms"]
assert any(v.get("definition") == draft and v["source"] == "manual" for v in saved.values()), (term, draft)
# every answer is also kept in my own dictionary, by domain (no Domain line in context.txt -> General)
import csv as _csv
dom = t / "gl" / "domains" / "General.csv"
assert dom.exists(), list((t / "gl").rglob("*"))
rows = list(_csv.DictReader(open(dom, newline="", encoding="utf-8-sig")))
assert list(rows[0].keys()) == ["Term", "Also known as", "Better", "Definition"], rows[0].keys()
assert any(r["Definition"] == "The share of jobs that came back as claims." for r in rows), rows
assert any(r["Definition"] == draft for r in rows), (draft, rows)
print("clarification loop tests passed")
# an older 1.9 csv with typed answers is still read
import csv
d = Path(tempfile.mkdtemp())
with open(d / clarify.LEGACY_CSV, "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.writer(fh); w.writerow(["Term", "Your definition (type here)"]); w.writerow(["Old KPI", "Typed in version 1.9."])
assert clarify.read(d / clarify.NAME) == ({}, [("Old KPI", "Typed in version 1.9.")])
print("legacy csv ok")
