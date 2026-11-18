"""Run:  python tests/test_compose_lead.py   -- known term + modifier names (Sales report: Actual_value, Previous month_actual_yarn, Rate(Rs/Kg))."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from glossary import Glossary
from compose_lead import compose_lead, unit_in_name

g = Glossary(Path(tempfile.mkdtemp()) / "g.json")
seed = g._seed_match
ACT = "the figure that really happened in the period, as opposed to the budget, target or forecast."
cases = {
    "Actual Value_yarn": "The figure that really happened in the period, as opposed to the budget, target or forecast. (Variant: yarn.)",
    "Actual_value": None,                                    # no variant, but the filler word makes it a different name from 'Actual'
    "Previous year_actual": "The actual figure for the previous year. Actual: " + ACT,
    "Previous month_actual_yarn": "The actual figure for the previous month. Actual: " + ACT + " (Variant: yarn.)",
    "Rate(Rs/Kg)_Yarn": "An amount measured against a unit of time or volume, such as per hour or per thousand. Measured in rupees per kilogram. (Variant: Yarn.)",
}
for name, want in cases.items():
    got = compose_lead(name, seed)
    if name == "Actual_value":
        assert got and got[0].startswith("The figure that really happened"), got
    else:
        assert got and got[0] == want, (name, got)
assert compose_lead("Budget_value", seed)[0].startswith("The planned amount")
# never over-reach: other words in the name, a plain name, a code as the label
assert compose_lead("Actual Hours Lost", seed) is None and compose_lead("Actual Value", seed) is None
assert compose_lead("Rate_INR", seed) is None and compose_lead("Previous month_lost hours", seed) is None
assert compose_lead("Scrap_yarn", seed) is None            # no known term inside
assert unit_in_name("Rate (USD/QTY)") == "Measured in US dollars per quantity." and unit_in_name("Rate") is None
assert unit_in_name("Rate (Rs/Kg)", {"RS": "Rupees"}) == "Measured in rupees per kilogram."

# in the glossary: a built-in term keeps its meaning and gains the unit; the composed name is a draft from the name
d = g.lookup("Rate (USD/QTY)", draft={"calc": "USD Value ÷ Usd quantity"})
assert d.source == "seed" and d.text.endswith("Measured in US dollars per quantity.")
d = g.lookup("Previous year_actual", draft={"calc": "Actual_value (plus 1 further condition)"})
assert d.source == "draft" and d.text.startswith("The actual figure for the previous year.") and "Draft built from the KPI name" in d.origin
d = g.lookup("Rate_INR", draft={"calc": "Amount INR ÷ Qty KG"})
assert d.text == "Amount INR divided by Qty KG."
print("compose lead tests passed")
