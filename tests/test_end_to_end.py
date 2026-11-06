"""End-to-end checks on made-up projects from other business domains.
Run:  python tests/test_end_to_end.py
"""
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def run(src, out, gloss):
    r = subprocess.run([sys.executable, str(ROOT / "run.py"), "--offline", "--source", str(src),
                        "--output", str(out), "--glossary", str(gloss)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def docx_text(path):
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    return re.sub(r"<[^>]+>", " ", xml)


def check(cond, msg):
    print(("ok: " if cond else "FAIL: ") + msg)
    assert cond, msg


def main():
    tmp = Path(tempfile.mkdtemp())
    subprocess.run([sys.executable, str(HERE / "make_synthetic_projects.py"), str(tmp / "synth")], check=True,
                   capture_output=True)
    res = {}
    for name in ("inventory", "streaming", "hr", "gaming"):
        out = tmp / name / "out"
        console = run(tmp / "synth" / name, out, tmp / name / "glossary.json")
        files = {p.name: p for p in out.iterdir()}
        manual = next(p for n, p in files.items() if n.endswith("User_Manual.docx"))
        gloss = next(p for n, p in files.items() if n.endswith("KPI_Glossary.docx"))
        html = next(p for n, p in files.items() if n.endswith("KPI_Documentation.html"))
        res[name] = {"console": console, "manual": docx_text(manual), "glossary": docx_text(gloss),
                     "html": html.read_text(encoding="utf-8")}
        check(True, f"{name}: three files written")
        # nothing from another business domain may leak in
        for word in ("TRIR", "Gemba", "Engraving", "Snowflake"):
            check(word not in res[name]["manual"] and word not in res[name]["glossary"],
                  f"{name}: no '{word}' in the documents")
        # coverage: every measure shown on a main page has a row in my_definitions.csv
        import csv as _csv
        sys.path.insert(0, str(ROOT))
        import app as _app
        from run import find_or_unzip_project
        from glossary import normalize as _norm
        from kpis import is_chrome_measure
        rd, sm = find_or_unzip_project(tmp / "synth" / name)
        an = _app.analyze_project(rd, sm)
        rows_ = {_norm(r["Term"]) for r in _csv.DictReader(open(tmp / name / "my_definitions.csv", encoding="utf-8-sig"))}
        shown = {r["property"] for p in an["pages"] if p.get("mainNav") for v in p["visuals"] for r in v["refs"]
                 if r["kind"] == "measure" and r["property"] in an["measuresByName"]
                 and not is_chrome_measure(r["property"]) and not an["explainer"].is_html(r["property"])}
        lost = sorted(m for m in shown if _norm(m) not in rows_)
        check(not lost, f"{name}: every displayed measure has a row in my_definitions.csv (missing: {lost})")
        h = res[name]["html"]
        check(h.count("<script") == h.count("</script>"), f"{name}: HTML script tags balanced")

    inv, st, hr = res["inventory"], res["streaming"], res["hr"]
    check("SKU Detail" in inv["console"] and "drill-through" in inv["console"], "drill-through page left out and reported")
    check("SKU Detail" not in inv["manual"].split("INDEX")[-1].split("5. Overview")[0].replace("Document Control", ""),
          "drill-through page absent from the manual's index")
    check("5%" in inv["manual"] and "0.05" not in inv["manual"], "visual colour rule shown as 5%, not 0.05")
    check("Shows a text label" in inv["manual"], "text-label measure explained from its DAX")
    check("SQL Server" in inv["manual"] and "InventoryDB" in inv["manual"], "data source read from the M query")
    check("turns" not in st["manual"] and "colour" not in st["manual"].split("Value & Display")[-1].split("Page")[0].lower()
          or "No targets, thresholds or colour rules" in st["manual"], "streaming: no colour text without evidence")
    check("No targets, thresholds or colour rules are defined" in st["manual"], "streaming: says so when there are none")
    check("Tip" in hr["console"] and "tooltip" in hr["console"], "HR: tooltip page left out")
    check("navigation buttons" not in hr["manual"].split("5.2")[1].split("5.3")[0], "HR: no navigation claim without buttons")
    gm = res["gaming"]
    check("2 pages (2 in the main navigation)" in gm["console"], "gaming: a two-page report keeps both pages")
    # a domain term gets its standard definition; a custom measure gets a draft rephrased from its own formula
    check("expected to earn over time" in gm["glossary"] or "wagered multiplied by the game" in gm["glossary"],
          "gaming: 'Theoretical Win' defined from the built-in gaming terms")
    check("Actual Win minus Theoretical Win" in gm["glossary"], "gaming: a custom measure is drafted from its formula")
    check("Draft from the formula" in gm["glossary"], "gaming: drafts are labelled")
    check("3%" in gm["manual"] and "0.03" not in gm["manual"], "gaming: colour threshold shown as 3%")
    for word in ("Gemba", "TRIR", "Mold", "Dayforce"):
        check(word not in gm["manual"] + gm["glossary"], f"gaming: no '{word}' leaked")
    print("ALL END-TO-END TESTS PASSED")


if __name__ == "__main__":
    main()
