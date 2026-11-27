"""Run:  python tests/test_design_language.py -- the Design Language section: theme, palette, fonts, canvas, card style, HTML measures
are read from the report files and written into the User Manual; a report with no formatting still gets a short, honest section."""
import sys, json, re, subprocess, tempfile, shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import design_language as DL
from docx import Document

# ---- the small readers
lit = lambda v: {"expr": {"Literal": {"Value": v}}}
assert DL._lit(lit("'Segoe UI'")) == "Segoe UI" and DL._lit(lit("12D")) == 12 and DL._lit(lit("true")) is True and DL._lit({}) is None
assert DL._colour({"solid": {"color": lit("'#fff'")}}) is None or DL._colour({"solid": {"color": lit("'#ffffff'")}}) == ("hex", "#FFFFFF")
assert DL._colour({"solid": {"color": {"expr": {"ThemeDataColor": {"ColorId": 3, "Percent": -0.25}}}}}) == ("theme", 3, -0.25)
assert DL._colour({"solid": {"color": {"expr": {"FillRule": {"Input": {}}}}}}) == ("rule",)
assert DL._norm_hex("#abc") == "#AABBCC"

# ---- a synthetic project with formatting added
t = Path(tempfile.mkdtemp())
subprocess.run([sys.executable, str(ROOT / "tests" / "make_synthetic_projects.py"), str(t / "syn")], check=True, capture_output=True)
rep = next((t / "syn" / "hr").glob("*.Report"))
(rep / "definition" / "report.json").write_text(json.dumps({
    "themeCollection": {"baseTheme": {"name": "CY24SU10"}, "customTheme": {"name": "BrandTheme.json"}},
    "resourcePackages": [{"name": "RegisteredResources", "type": "RegisteredResources", "items": [
        {"name": "BrandTheme.json", "path": "BrandTheme.json", "type": "CustomTheme"}, {"name": "logo.png", "path": "logo.png", "type": "Image"}]}]}), encoding="utf-8")
(rep / "StaticResources" / "RegisteredResources").mkdir(parents=True)
(rep / "StaticResources" / "RegisteredResources" / "BrandTheme.json").write_text(json.dumps({
    "name": "BrandTheme", "dataColors": ["#0B3C5D", "#328CC1", "#D9B310", "#1D2731"], "background": "#FFFFFF", "foreground": "#252423",
    "tableAccent": "#0B3C5D", "good": "#2E8B57", "neutral": "#D9B310", "bad": "#C0392B",
    "textClasses": {"title": {"fontSize": 16, "fontFace": "Segoe UI Semibold", "color": "#252423"}, "callout": {"fontSize": 28, "fontFace": "DIN", "color": "#0B3C5D"}},
    "visualStyles": {"*": {"*": {"border": [{"show": True, "color": {"solid": {"color": "#E1E1E1"}}, "radius": 8}],
                               "background": [{"color": {"solid": {"color": "#FFFFFF"}}, "transparency": 0}]}}}}), encoding="utf-8")
pages = sorted((rep / "definition" / "pages").glob("*/page.json"))
pf = next(f for f in pages if json.loads(f.read_text(encoding="utf-8")).get("displayName") == "Hiring")   # a page that is in the manual
pj = json.loads(pf.read_text(encoding="utf-8"))
pj["objects"] = {"background": [{"properties": {"color": {"solid": {"color": lit("'#F3F2F1'")}}, "transparency": lit("0D")}}]}
pf.write_text(json.dumps(pj), encoding="utf-8")
styled = 0
for vf in sorted((rep / "definition" / "pages").glob("*/visuals/*/visual.json")):
    vj = json.loads(vf.read_text(encoding="utf-8"))
    if vj["visual"]["visualType"] in ("card", "tableEx", "table", "columnChart", "clusteredColumnChart", "lineChart", "barChart"):
        vj["visual"]["visualContainerObjects"] = {
            "background": [{"properties": {"show": lit("true"), "color": {"solid": {"color": lit("'#FAFAFA'")}}}}],
            "border": [{"properties": {"show": lit("true"), "radius": lit("12D"), "color": {"solid": {"color": lit("'#D0D0D0'")}}}}],
            "title": [{"properties": {"show": lit("true"), "fontFamily": lit("'Segoe UI Semibold'"), "fontSize": lit("14D"),
                                      "fontColor": {"solid": {"color": lit("'#0B3C5D'")}}}}]}
        vj["visual"]["objects"] = {"dataPoint": [{"properties": {"fill": {"solid": {"color": lit("'#328CC1'")}}}}]}
        vf.write_text(json.dumps(vj), encoding="utf-8"); styled += 1
assert styled >= 2, styled
mm = next((t / "syn" / "hr").glob("*.SemanticModel/definition/tables/_Measures.tmdl"))
x = mm.read_text(encoding="utf-8")
x += "\n\tmeasure 'Look Test' = \"<div style='font-family:Segoe UI;font-size:13px;border-radius:10px;box-shadow:0 1px 2px #999;color:#0B3C5D'>x</div>\"\n"
mm.write_text(x, encoding="utf-8")

out = t / "out"
r = subprocess.run([sys.executable, str(ROOT / "run.py"), "--no-prompt", "--offline", "--skip-drafts", "--source", str(t / "syn" / "hr"), "--output", str(out),
                    "--glossary", str(t / "gl" / "glossary.json")], capture_output=True, text=True, encoding="utf-8")
assert r.returncode == 0, r.stderr[-1000:]
doc = Document(str(next(out.glob("*User_Manual.docx"))))
text = "\n".join(p.text for p in doc.paragraphs)
cells = "\n".join(c.text for tb in doc.tables for row in tb.rows for c in row.cells)
assert "Design Language" in text and "BrandTheme.json" in text.replace("“", "").replace("”", "") or "BrandTheme" in text, text[-3000:]
for must in ("#0B3C5D", "#328CC1", "#D9B310", "#2E8B57", "#C0392B", "#FAFAFA", "#F3F2F1"):
    assert must in cells, (must, cells[cells.index("Where"):][:900])
assert "Segoe UI Semibold" in cells and "1280 × 720" in text + cells and "16:9" in text and "DIN" in cells
assert "corner radius 12" in text and "logo.png" in text and "Inside HTML visuals" in cells and "box-shadow" not in text
assert "shadows in 1 measure" in text and "Apply the theme" in text

# ---- the headings keep their numbers in order, and a report with no formatting still gets an honest section
heads = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading 1")]
nums = [int(m.group(1)) for h in heads if (m := re.match(r"(\d+)\.\s", h))]
assert nums == list(range(1, len(nums) + 1)), heads
shutil.rmtree(rep / "StaticResources")
(rep / "definition" / "report.json").write_text("{}", encoding="utf-8")
for vf in (rep / "definition" / "pages").glob("*/visuals/*/visual.json"):
    vj = json.loads(vf.read_text(encoding="utf-8")); vj["visual"].pop("visualContainerObjects", None); vj["visual"].pop("objects", None)
    vf.write_text(json.dumps(vj), encoding="utf-8")
x = mm.read_text(encoding="utf-8").split("\n\tmeasure 'Look Test'")[0]
mm.write_text(x, encoding="utf-8")
r = subprocess.run([sys.executable, str(ROOT / "run.py"), "--no-prompt", "--offline", "--skip-drafts", "--source", str(t / "syn" / "hr"), "--output", str(t / "out2"),
                    "--glossary", str(t / "gl2" / "glossary.json")], capture_output=True, text=True, encoding="utf-8")
assert r.returncode == 0, r.stderr[-1000:]
doc = Document(str(next((t / "out2").glob("*User_Manual.docx"))))
text = "\n".join(p.text for p in doc.paragraphs)
assert "Design Language" in text and "no theme, so Power BI's default theme applies" in text and "do not override Power BI's default" in text, text[-2500:]
d = DL.collect(t / "does_not_exist", [], [])
assert d.get("found") is False or d.get("pages") == [], d
print("design language tests passed")
