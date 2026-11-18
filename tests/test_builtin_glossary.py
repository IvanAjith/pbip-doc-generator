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
# --- a term written with %/ratio only matches a measure that also says %/ratio
d = g.lookup("Expense Ratio", web=False)
assert d and d.category == "Insurance", d
d = g.lookup("Expense", web=False)
assert d and d.category == "Finance" and "premium" not in d.text.lower(), d     # plain 'Expense' is not the insurance ratio
print("ok: %d terms, %d domains, smallest domain has %d" % (len(entries), len(by_domain), min(len(v) for v in by_domain.values())))
