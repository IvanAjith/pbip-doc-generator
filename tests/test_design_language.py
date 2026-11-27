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
tables = ["\n".join(c.text for row in tb.rows for c in row.cells) for tb in doc.tables]
cells = "\n".join(tables)
paras = doc.paragraphs
i0 = next(i for i, p in enumerate(paras) if p.style.name.startswith("Heading 1") and p.text.endswith("Design Language"))
i1 = next(i for i in range(i0 + 1, len(paras)) if paras[i].style.name.startswith("Heading 1"))
sec = "\n".join(p.text for p in paras[i0:i1])
assert "BrandTheme.json" in sec.replace("\u201c", "").replace("\u201d", ""), sec[:800]
# the overall picture: primary, secondary, accent, background, text, good / neutral / bad
roles = {}
for tb in doc.tables:
    if [c.text for c in tb.rows[0].cells][:2] == ["Swatch", "Role"]:
        roles = {r.cells[1].text: r.cells[0].text for r in tb.rows[1:]}
assert roles == {"Primary": "#0B3C5D", "Secondary": "#328CC1", "Accent": "#D9B310", "Background": "#FFFFFF", "Text": "#252423",
                 "Good": "#2E8B57", "Neutral": "#D9B310", "Bad": "#C0392B"}, roles
assert "Segoe UI Semibold" in cells and "DIN" in cells and "16 pt" in cells and "28 pt" in cells
assert "1280 \u00D7 720" in sec and "16:9" in sec and "rounded corners (12 px)" in sec and "Apply the theme" in sec and "#0B3C5D (dark blue) as the primary colour" in sec
# high level only: no page-by-page table, no visual-by-visual counts, no long colour lists
assert "Behind the page" not in cells and "Page background" not in cells and not re.search(r"\d+ of \d+ visuals", sec) and "Set directly on" not in cells
assert sum(len(tb.rows) for tb in doc.tables if [c.text for c in tb.rows[0].cells][:1] == ["Swatch"]) <= 10
assert len([l for l in sec.splitlines() if l.strip()]) <= 22, sec

# ---- the headings keep their numbers in order, and a report with no formatting still gets an honest section
heads = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading 1")]
nums = [int(m.group(1)) for h in heads if (m := re.match(r"(\d+)\.\s", h))]
assert nums == list(range(1, len(nums) + 1)), heads
shutil.rmtree(rep / "StaticResources")
(rep / "definition" / "report.json").write_text("{}", encoding="utf-8")
r = subprocess.run([sys.executable, str(ROOT / "run.py"), "--no-prompt", "--offline", "--skip-drafts", "--source", str(t / "syn" / "hr"), "--output", str(t / "out1"),
                    "--glossary", str(t / "gl1" / "glossary.json")], capture_output=True, text=True, encoding="utf-8")
assert r.returncode == 0, r.stderr[-1000:]
d1 = Document(str(next((t / "out1").glob("*User_Manual.docx"))))
sw = next(tb for tb in d1.tables if [c.text for c in tb.rows[0].cells][:2] == ["Swatch", "Role"])
got = {r.cells[1].text: (r.cells[0].text, r.cells[3].text) for r in sw.rows[1:]}
assert {got["Primary"][0], got["Secondary"][0]} == {"#0B3C5D", "#328CC1"} and "most used colour" in got["Primary"][1], got
assert "no custom theme" not in "\n".join(p.text for p in d1.paragraphs) and "default theme applies" in "\n".join(p.text for p in d1.paragraphs)
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
assert "Design Language" in text and "no theme, so Power BI's default theme applies" in text and "keep Power BI's default card style" in text, text[-2500:]
h2s = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading 2") and re.match(r"5\.\d", p.text)]
assert [h.split()[0] for h in h2s] == [f"5.{i}" for i in range(1, len(h2s) + 1)], h2s
d = DL.collect(t / "does_not_exist", [], [])
assert d.get("found") is False or d.get("pages") == [], d
print("design language tests passed")
