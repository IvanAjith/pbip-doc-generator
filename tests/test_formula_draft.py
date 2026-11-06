"""Run:  python tests/test_formula_draft.py"""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from formula_draft import formula_draft as f
from glossary import Glossary

cases = [
    (("Scanned Hours ÷ Paid Hours", "percent"), "Scanned Hours as a percentage of Paid Hours."),
    (("Turnover × Hold %", None), "Turnover multiplied by Hold %."),
    (("Wagers − Payouts", None), "Wagers minus Payouts."),
    (("Month End Backlog + Shipped Sales", None), "Month End Backlog plus Shipped Sales."),
    (("total Amount (counting only rows where Type is “Sales”)", None), "The total of Amount, counting only rows where Type is “Sales”."),
    (("number of distinct Customer KEY", None), "The number of distinct Customer KEY."),
    (("average Rating Value", None), "The average of Rating Value."),
    (("(Closed ÷ Total) × 100", "percent"), "Closed as a percentage of Total."),
    (("absolute value of Revenue ÷ Hours", None), "The absolute value of Revenue divided by Hours."),
]
for args, want in cases:
    got = f(*args)
    assert got == want, (args, got, want)
assert f(None) is None and f("") is None
assert f("", None, ["Recordable Incidents", "Hours"]).startswith("Built from Recordable Incidents and Hours;")

# in the glossary: formula draft sits below manual / seed / web / AI, above 'unresolved', and is never saved as learned
d = Path(tempfile.mkdtemp())
g = Glossary(d / "glossary.json")
x = g.lookup("Theoretical Win Custom", draft={"calc": "Turnover × Hold %", "unit": None})
assert x.source == "draft" and x.text == "Turnover multiplied by Hold %." and not x.verified
assert g.lookup("Mystery Thing", draft={"calc": "", "inputs": []}) is None
g.save()
import json
terms = json.loads((d / "glossary.json").read_text(encoding="utf-8")).get("terms", {}) if (d / "glossary.json").exists() else {}
assert "theoretical win custom" not in terms
assert g.lookup("Revenue", draft={"calc": "A ÷ B"}).source == "seed"      # a standard definition beats a draft
print("formula draft tests passed")
