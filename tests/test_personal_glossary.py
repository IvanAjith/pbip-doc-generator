"""Run:  python tests/test_personal_glossary.py -- my own dictionary: every answer is kept in glossary\\domains\\<Domain>.csv
(the Domain: line of context.txt names the file), the next run reads it like the built-in list, and an answer is replaced, not duplicated."""
import sys, csv, json, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from glossary import Glossary

t = Path(tempfile.mkdtemp())
gp = t / "gl" / "glossary.json"

assert Glossary.domain_slug("healthcare") == "Healthcare"
assert Glossary.domain_slug("manufacturing (engraving and mold making)") == "Manufacturing"
assert Glossary.domain_slug("") == "General" and Glossary.domain_slug("Retail & E-commerce") == "Retail_E_Commerce"

g = Glossary(gp)
assert g.lookup("Readmission Rate") is None or g.lookup("Readmission Rate").source != "seed"   # not a built-in term
g.domain = "healthcare"
assert g.absorb_answers([("Readmission Rate", "Patients who return to hospital within 30 days of leaving.")]) == 1
f = t / "gl" / "domains" / "Healthcare.csv"
assert f.exists()
rows = list(csv.DictReader(open(f, newline="", encoding="utf-8-sig")))
assert [r["Term"] for r in rows] == ["Readmission Rate"] and list(rows[0]) == ["Term", "Also known as", "Better", "Definition"]
g.save()

# a later project: even with glossary.json gone, my dictionary answers (and a time window around the name still matches)
gp.unlink()
g2 = Glossary(gp)
d = g2.lookup("Readmission Rate")
assert d and d.source == "seed" and d.verified and d.origin == "My glossary - Healthcare" and "30 days" in d.text, d
d2 = g2.lookup("Readmission Rate (12M)")
assert d2 and "30 days" in d2.text, d2

# an answer for the same term replaces the old row; another domain goes to its own file
g2.domain = "healthcare"
g2.absorb_answers([("readmission rate", "Share of discharged patients admitted again within 30 days.")])
rows = list(csv.DictReader(open(f, newline="", encoding="utf-8-sig")))
assert len(rows) == 1 and rows[0]["Definition"].startswith("Share of discharged"), rows
g2.domain = "retail"
g2.absorb_answers([("Basket Size", "Items in one shopping trip.")])
assert (t / "gl" / "domains" / "Retail.csv").exists()
assert Glossary(gp).lookup("Basket Size").origin == "My glossary - Retail"
# the built-in list is not touched
assert not (ROOT / "builtin_glossary" / "Healthcare.csv").exists()
print("personal glossary tests passed")
