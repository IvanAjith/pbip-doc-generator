"""Run:  python tests/test_name_lead.py   -- offline meaning built from the KPI name."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from name_lead import name_lead as n
from glossary import Glossary
from checks import Context

M = {"DL": "direct labour", "IDL": "indirect labour", "CB": "comeback"}
cases = [
    ("% Unscheduled Jobs", M, None, "The percentage of jobs that are not scheduled."),
    ("% UNSCHEDULED JOBS", M, None, "The percentage of jobs that are not scheduled."),
    ("Jobs Unscheduled %", M, None, None),                       # word order we do not rewrite: formula wording is used
    ("Unscheduled Jobs", M, None, "Jobs that are not scheduled."),
    ("Unscheduled Jobs By Week", M, "percent", "The percentage of jobs that are not scheduled. (Period shown: by week.)"),
    ("Unplanned Downtime", M, None, "Downtime that is not planned."),
    ("Non Billable Hours", M, None, "Hours that are not billable."),
    ("Not Scheduled Jobs %", M, None, "The percentage of jobs that are not scheduled."),
    ("Admin FTE", M, None, "Admin full-time equivalent (FTE): staff time expressed as a number of full-time employees."),
    ("FTE DL", M, None, "Full-time equivalent (FTE) direct labour (DL): staff time expressed as a number of full-time employees."),
    ("FTE IDL", M, None, "Full-time equivalent (FTE) indirect labour (IDL): staff time expressed as a number of full-time employees."),
    # never guess: an abbreviation nobody explained, or nothing to add
    ("FTE DL", {}, None, None),
    ("WO Headcount", M, None, None),
    ("Zorp CB %", {}, None, None),
    ("Mid Adj CB %", M, None, None),                             # percentage names that only spell out an abbreviation use the formula
    ("Unit Cost", M, None, None), ("United Sales", M, None, None), ("Underused Capacity", M, None, None),
    ("Late Orders %", M, None, None), ("Jobs", M, None, None), ("Unassigned", M, None, None),
]
for name, m, unit, want in cases:
    got = n(name, m, unit)
    assert got == want, (name, got, want)

# inside the glossary: below manual / built-in glossary / web / AI, above the formula wording
d = Path(tempfile.mkdtemp())
g = Glossary(d / "glossary.json")
g.context = Context(d / "context.txt")
x = g.lookup("% Unscheduled Jobs", draft={"calc": "Number of unscheduled jobs ÷ Total jobs", "unit": "percent"})
assert x.source == "draft" and x.text == "The percentage of jobs that are not scheduled." and "name" in x.origin
y = g.lookup("Late Orders %", draft={"calc": "Late ÷ Total", "unit": "percent"})
assert y.text == "Late as a percentage of Total."                 # no lead -> formula wording, as before
g.context.set_meanings({"DL": "direct labour"})
z = g.lookup("FTE DL", draft={"calc": "x", "unit": None})
assert z.text.startswith("Full-time equivalent (FTE) direct labour (DL)") and "Here, DL" not in z.text   # not said twice
w = g.lookup("DL Hours Lost Custom", draft={"calc": "Lost Hours ÷ Total Hours", "unit": "percent"})
assert w.text.endswith("Here, DL means direct labour.")
v = g.lookup("Zorp DL Hours Custom", draft={"calc": "Lost Hours ÷ Total Hours", "unit": None})   # spelled-out lead + the formula wording
assert v.text == "Zorp direct labour (DL) hours custom. Lost Hours divided by Total Hours.", v.text           # formula wording still gets the note
g.context.set_meanings({"FTE": "my own words for FTE"})
assert g.lookup("Admin FTE Extra", draft={"calc": "x"}).text.startswith("Admin my own words for FTE (FTE)")  # your meaning wins
assert g.lookup("Revenue", draft={"calc": "A ÷ B"}).source == "seed"
print("name lead tests passed")
