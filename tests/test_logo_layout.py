"""Run:  python tests/test_logo_layout.py -- company logo on all three documents; glossary table = KPI / What it means / How it is calculated."""
import sys, subprocess, tempfile, re
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from docx import Document
t = Path(tempfile.mkdtemp())
subprocess.run([sys.executable, str(ROOT / "tests" / "make_synthetic_projects.py"), str(t / "syn")], check=True, capture_output=True)
def run(out, *extra):
    r = subprocess.run([sys.executable, str(ROOT / "run.py"), "--no-prompt", "--offline", "--source", str(t / "syn" / "gaming"),
                        "--output", str(t / out), "--glossary", str(t / out / "g" / "glossary.json"), *extra],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr[-800:]
    return r.stdout
def images(doc_path):
    d = Document(str(doc_path))
    n = len(d.inline_shapes)
    for s in d.sections:
        n += len(s.header._element.xpath(".//pic:pic")) + len(s.first_page_header._element.xpath(".//pic:pic"))
    return n, len(d.inline_shapes)
run("with")
g = next((t / "with").glob("*KPI_Glossary.docx")); m = next((t / "with").glob("*User_Manual.docx")); h = next((t / "with").glob("*.html"))
for f in (g, m):
    total, cover = images(f)
    assert cover >= 1 and total >= 2, (f.name, total, cover)          # on the cover and in the page header
    assert "[ COMPANY LOGO ]" not in "\n".join(c.text for tb in Document(str(f)).tables for r in tb.rows for c in r.cells)
assert "data:image/png;base64," in h.read_text(encoding="utf-8")
heads = [[c.text for c in tb.rows[0].cells] for tb in Document(str(g)).tables if tb.rows[0].cells[0].text in ("KPI", "Indicator", "Measure")]
assert heads and all(x == ["KPI", "What it means", "How it is calculated"] for x in heads), heads
alltext = "\n".join(c.text for tb in Document(str(g)).tables for r in tb.rows for c in r.cells)
assert "Built-in glossary" not in alltext and "Draft from the formula" not in alltext and "Also shown on" not in alltext
# no logo: the placeholder stays and nothing breaks
run("without", "--logo", "none")
g2 = next((t / "without").glob("*KPI_Glossary.docx"))
assert "[ COMPANY LOGO ]" in "\n".join(c.text for tb in Document(str(g2)).tables for r in tb.rows for c in r.cells)
assert "data:image/png" not in next((t / "without").glob("*.html")).read_text(encoding="utf-8")
print("logo + glossary layout tests passed")
