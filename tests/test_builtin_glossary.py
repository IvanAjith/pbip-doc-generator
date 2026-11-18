"""Run:  python tests/test_builtin_glossary.py   (no network).
The built-in glossary is the offline dictionary: every domain must have at least 50 terms with real definitions,
no two entries may share a name, and a term written with %/ratio must only match a measure that also says so."""
import sys, csv
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import seed_glossary as S
from glossary import Glossary, normalize, has_unit

MIN_TERMS = 50
entries = S.load()
by_domain = {}
for e in entries:
    by_domain.setdefault(e["category"], []).append(e)

# --- every domain has at least 50 terms
for d, items in sorted(by_domain.items()):
    assert len(items) >= MIN_TERMS, f"{d} has only {len(items)} terms (need {MIN_TERMS})"
for want in ("Finance", "Sales", "Marketing", "Customer", "Operations", "Supply Chain & Inventory", "Procurement", "Quality",
             "Safety", "HR & People", "Insurance", "Banking & Investments", "Gaming & Media", "Technology & SaaS", "General"):
    assert want in by_domain, f"domain missing: {want}"

# --- definitions are real sentences, Better is valid, no duplicate names across the whole list
seen = {}
for e in entries:
    d = e["definition"]
    assert len(d) >= 40 and d.rstrip().endswith("."), (e["terms"][0], d)
    assert e["better"] in (None, "higher", "lower"), e["terms"][0]
    for t in e["terms"]:
        k = (normalize(t), has_unit(t))
        assert k[0], f"name normalises to nothing: {t}"
        assert seen.get(k, e["terms"][0]) == e["terms"][0], f"'{t}' ({e['terms'][0]}) clashes with '{seen[k]}'"
        seen[k] = e["terms"][0]

# --- the offline tool really reads these definitions
g = Glossary(Path("/nonexistent/glossary.json"))
for name, expect in (("Net Interest Margin", "Banking & Investments"), ("Purchase Price Variance", "Procurement"),
                     ("First Contact Resolution", "Customer"), ("Win per Seat", "Gaming & Media"),
                     ("Sprint Velocity", "Technology & SaaS"), ("Sick Leave Rate", "HR & People"),
                     ("Claims Settlement Time", "Insurance"), ("Sales Cycle Length", "Sales")):
    d = g.lookup(name, web=False)
    assert d and d.text and d.origin == "built-in glossary", (name, d)
# --- names that exist in more than one field must resolve to the field a business user means
TRAPS = {   # written name -> the domain it must resolve to
    "Turnover": "HR & People", "Turnover %": "HR & People", "Turnover Ratio": "HR & People", "Turnover Rate": "HR & People",
    "Portfolio Turnover": "Banking & Investments", "Fund Turnover": "Banking & Investments",
    "Efficiency": "Operations", "Efficiency %": "Operations", "Efficiency Ratio": "Operations", "Cost to Income Ratio": "Banking & Investments",
    "Expense %": "Finance", "Expenses": "Finance", "Expense Ratio": "Insurance",
    "Gross Margin": "Finance", "Gross Margin %": "Finance", "Retention": "Customer", "Retention %": "Customer",
    "Leverage": "Finance", "Leverage Ratio": "Finance", "Bank Leverage Ratio": "Banking & Investments",
    "Operating Expense Ratio": "Finance", "Opex Ratio": "Finance", "Availability %": "Operations",
    "Working Capital": "Finance", "Utilization": "Operations", "Yield": "Quality", "Attendance": None, "Frequency": None,
    "Duration": None, "Exposure": None, "Allocation": None, "Reserves": None, "Subscriptions": None, "Outflows": None,
}
for name, dom in TRAPS.items():
    d = g.lookup(name, web=False)
    got = d.category if d and d.origin == "built-in glossary" else None
    assert got == dom, f"'{name}' resolved to {got}, expected {dom}"
# every name shared by two different domains must still resolve to the one that owns it when written exactly
from collections import defaultdict
owners = defaultdict(set)
for e in entries:
    for t in e["terms"]:
        owners[normalize(t)].add((e["terms"][0], e["category"]))
for k, o in owners.items():
    cats = {c for _, c in o}
    if len(cats) > 1:
        for term, cat in o:
            assert g.lookup(term, web=False).category == cat or has_unit(term) is False, (term, cat)
print("ok: %d terms, %d domains, smallest domain has %d" % (len(entries), len(by_domain), min(len(v) for v in by_domain.values())))
