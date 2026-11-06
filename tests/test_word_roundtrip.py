"""Run:  python tests/test_word_roundtrip.py
Generates the documents for a made-up project, edits a definition inside the glossary .docx the way a user would,
runs again, and checks the edit is kept in the glossary, the manual and across a third run."""
import subprocess, sys, tempfile, json
from pathlib import Path
from docx import Document
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))


def run(src, out, gloss):
    r = subprocess.run([sys.executable, str(ROOT / "run.py"), "--offline", "--source", str(src), "--output", str(out),
                        "--glossary", str(gloss / "glossary.json")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def text(path):
    d = Document(str(path))
    parts = [p.text for p in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            parts += [c.text for c in row.cells]
    return "\n".join(parts)


def main():
    tmp = Path(tempfile.mkdtemp())
    subprocess.run([sys.executable, str(HERE / "make_synthetic_projects.py"), str(tmp / "synth")], check=True, capture_output=True)
    src, out, g = tmp / "synth" / "inventory", tmp / "out", tmp / "g"
    g.mkdir()
    run(src, out, g)
    gl = next(out.glob("*KPI_Glossary.docx"))
    d = Document(str(gl))
    target = None
    for t in d.tables:
        if [c.text for c in t.rows[0].cells][:2] == ["Indicator", "What it means"]:
            for r in t.rows[1:]:
                target = r
                break
        if target is not None:
            break
    assert target is not None, "no glossary table found"
    term = target.cells[0].text.strip()
    mine = "My own wording for this indicator, written directly in Word."
    cell = target.cells[1]
    for p in cell.paragraphs[1:]:
        p._element.getparent().remove(p._element)
    cell.paragraphs[0].text = mine
    d.save(str(gl))

    console = run(src, out, g)
    assert "picked up 1 definition" in console, console
    assert mine in text(next(out.glob("*KPI_Glossary.docx"))), "edit lost in the glossary"
    assert "Your own definition" in text(next(out.glob("*KPI_Glossary.docx")))
    manual_txt = text(next(out.glob("*User_Manual.docx")))
    assert mine in manual_txt, "the edited definition did not reach the user manual"
    third = run(src, out, g)
    assert mine in text(next(out.glob("*KPI_Glossary.docx"))), "edit lost on the third run"
    assert "picked up" not in third, "an unchanged cell was counted as an edit"
    print("word round-trip tests passed (edited:", term + ")")


main()
