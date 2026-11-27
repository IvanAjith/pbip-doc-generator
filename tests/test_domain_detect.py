"""Run:  python tests/test_domain_detect.py -- the domain is found from the report's own names; a typed Domain: line wins; unclear -> General."""
import sys, csv
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import domain_detect as dd

cat = dd._load()
assert len(cat) >= 120, len(cat)
assert all(len(w) >= 6 for w in cat.values()), [d for d, w in cat.items() if len(w) < 6]
# the 14 built-in domains are in the catalogue under the same names the built-in glossary uses
from seed_glossary import SEED
built = {e["category"] for e in SEED} - {"General"}
assert built <= set(cat), built - set(cat)

cases = {
    "Healthcare": ["Readmission Rate", "Average Length of Stay", "Bed Occupancy Rate", "Patient Admissions", "No Show Rate"],
    "Supply Chain & Inventory": ["Stock On Hand", "Inventory Value", "Days of Supply", "Stockout Rate"],
    "Airlines & Aviation": ["Load Factor", "On Time Performance", "Flights Operated", "Passenger Count"],
    "Gaming & Media": ["Content", "Audience", "Viewing", "Monthly Active Users", "Churned Subscribers", "ARPU", "Watch Hours"],
    "Education": ["Student Enrollment", "Attendance Rate", "Dropout Rate", "Graduation Rate"],
    "Real Estate & Property": ["Lease Expiry", "Occupancy Rate", "Rent per Square Feet", "Tenant Count", "Vacancy"],
}
for want, names in cases.items():
    got, ev = dd.detect(names)
    assert got == want, (want, got, ev)

assert dd.detect(["Total", "Count", "Amount"])[0] == "General"          # nothing to go on
# a hospital report also has finance KPIs: the industry still wins over the function
assert dd.detect(["Patient Admissions", "Bed Occupancy", "Readmission Rate", "Revenue", "Expense", "Gross Margin", "EBITDA"])[0] == "Healthcare"
assert dd.detect([])[0] == "General"
# the built-in glossary votes too
got, _ = dd.detect(["Foo", "Bar", "Baz"], seed_category=lambda n: "Insurance")
assert got == "Insurance"
print("domain detection tests passed")
