"""The built-in glossary on paper (Excel) and the reviewed, shared list that grows."""
import csv, json, os, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import glossary_export as GE
from glossary import Glossary
from seed_glossary import SEED

tmp = Path(tempfile.mkdtemp())

# --- Excel of the built-in list
x, n = GE.export_xlsx(tmp / "list.xlsx")
assert n == len(SEED) and x.suffix == ".xlsx"
import openpyxl
wb = openpyxl.load_workbook(x)
assert wb.sheetnames[:2] == ["Overview", "All terms"] and "Safety" in wb.sheetnames and "Finance" in wb.sheetnames
ws = wb["All terms"]
assert ws.max_row == len(SEED) + 1 and [c.value for c in ws[1]][:2] == ["Domain", "Term"] and ws.auto_filter.ref
assert sum(wb[d].max_row - 1 for d in wb.sheetnames[2:]) == len(SEED)          # every term is on exactly one domain sheet
print("ok: Excel export")

# --- shared list: used like a built-in term (offline too), never overrides a built-in one
shared = tmp / "shared_glossary.csv"
shared.write_text("Term,Also known as,Domain,Better,Definition,Source,Added\n"
                  "Supplier OTIF,On Time In Full Supplier; SOTIF,Procurement,higher,Share of purchase orders delivered on time and complete.,Reviewed addition,18/11/2026\n"
                  "TRIR,,Safety,,A competing definition that must not win.,x,18/11/2026\n", encoding="utf-8")
rows = GE.read_shared(shared)
assert [r["terms"][0] for r in rows] == ["Supplier OTIF", "TRIR"] and rows[0]["terms"][1:] == ["On Time In Full Supplier", "SOTIF"]
assert rows[0]["better"] == "higher" and rows[0]["category"] == "Procurement"
import glossary as G
# glossary.py calls read_shared() with its default path: point that default at the temporary file
GE.read_shared.__defaults__ = (shared,)
g = Glossary(tmp / "g.json")
d = g.lookup("SOTIF")
assert d and d.source == "seed" and d.origin == "shared glossary" and "delivered on time" in d.text, d
d2 = g.lookup("6 months Supplier OTIF")
assert d2 and d2.text.endswith("(Period shown: 6 months.)")
assert "competing" not in g.lookup("TRIR").text                                   # built-in wins
x2, n2 = GE.export_xlsx(tmp / "list2.xlsx", shared)
assert n2 == len(SEED) + 2 and "Procurement" in openpyxl.load_workbook(x2).sheetnames        # new domain appears
print("ok: shared list is used offline and never overrides built-in terms")

# --- candidates: what this computer learned
gj = tmp / "glossary" / "glossary.json"
gj.parent.mkdir()
gj.write_text(json.dumps({"terms": {
    "dock door turnaround": {"term": "Dock Door Turnaround", "definition": "Days between placing an order and receiving it.", "source": "ai", "origin": "AI draft (gemini)"},
    "cabinet fill index": {"term": "Cabinet Fill Index", "definition": "Share of spend covered by managed contracts.", "source": "web", "origin": "Wikipedia", "url": "https://x", "wv": G.WEB_VERSION},
    "30 day raw cb": {"term": "30-Day Raw CB %", "definition": "Their own wording.", "source": "manual"},
    "otd": {"term": "OTD", "definition": "already built in", "source": "ai"},
    "sotif": {"term": "SOTIF", "definition": "already shared", "source": "ai"},
    "empty": {"term": "Empty", "definition": "", "source": "unresolved"},
    "checked": {"term": "Checked", "definition": "Words that need a look.", "source": "ai", "note": "words not in the report: a, b"}}}), encoding="utf-8")
g = Glossary(gj)
cand = GE.candidates(g, shared)
assert [c["Term"] for c in cand] == ["30-Day Raw CB %", "Cabinet Fill Index", "Checked", "Dock Door Turnaround"], [c["Term"] for c in cand]
assert "Check" in [c for c in cand if c["Term"] == "Checked"][0]["Notes for the reviewer"]
out = tmp / "cand.csv"
assert GE.export_candidates(g, out, shared) == 4
assert next(csv.DictReader(open(out, encoding="utf-8-sig")))["Approve (Y/N)"] == ""
print("ok: candidates")

# --- merge: only rows marked Y, nothing twice, nothing unfinished
rowsx = list(csv.DictReader(open(out, encoding="utf-8-sig")))
for r in rowsx:
    if r["Term"] in ("Dock Door Turnaround", "Cabinet Fill Index", "Checked"):
        r["Approve (Y/N)"] = "y" if r["Term"] != "Checked" else "Yes"
    if r["Term"] == "Dock Door Turnaround":
        r["Domain"] = "Procurement"
rowsx.append({"Approve (Y/N)": "Y", "Term": "Supplier OTIF", "Domain": "x", "Definition": "dup", "Where it came from": "", "Notes for the reviewer": ""})
rowsx.append({"Approve (Y/N)": "Y", "Term": "No Text", "Domain": "", "Definition": "", "Where it came from": "", "Notes for the reviewer": ""})
with open(out, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=GE.CAND_COLS); w.writeheader(); w.writerows(rowsx)
added, known, unfinished = GE.merge_candidates(out, shared, today="18/11/2026")
assert (added, known, unfinished) == (3, 1, 1), (added, known, unfinished)
after = {r["Term"]: r for r in csv.DictReader(open(shared, encoding="utf-8-sig"))}
assert after["Dock Door Turnaround"]["Domain"] == "Procurement" and after["Cabinet Fill Index"]["Domain"] == "General"
assert after["Dock Door Turnaround"]["Added"] == "18/11/2026" and "30-Day Raw CB %" not in after
assert GE.merge_candidates(out, shared)[0] == 0                                    # running it twice adds nothing
assert Glossary(tmp / "g2.json").lookup("Dock Door Turnaround").source == "seed"       # now available to everyone, offline
print("ok: merge")

# --- the command line
env = dict(os.environ, PBIP_DOC_GENERATOR_HOME=str(tmp / "home"))
r = subprocess.run([sys.executable, str(ROOT / "run.py"), "--export-glossary", str(tmp / "cli.xlsx")], capture_output=True, text=True, env=env)
assert r.returncode == 0 and (tmp / "cli.xlsx").exists() and "definitions, by domain" in r.stdout, r.stdout + r.stderr
r = subprocess.run([sys.executable, str(ROOT / "run.py"), "--export-shared", str(tmp / "c2.csv"), "--glossary", str(gj)], capture_output=True, text=True, env=env)
assert r.returncode == 0 and "Write Y" in r.stdout.replace("write Y", "Write Y"), r.stdout + r.stderr
print("ok: command line")
print("shared glossary tests passed")
