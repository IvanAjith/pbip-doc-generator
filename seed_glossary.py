"""seed_glossary.py -- the built-in glossary: standard business terms and what they mean, by domain.

The definitions live in builtin_glossary/<Domain>.csv, one file per domain, so they can be opened and edited in Excel:

    Term, Also known as (separate with ;), Better (higher / lower / blank), Definition

SEED is built from those files. Rules for the files: one row per term; a term (or alternative name) appears once in the
whole list; the definition says what the figure means to the business in plain words (no formulas unless they are universal).
tests/test_builtin_glossary.py checks all of this.
"""
import csv
from pathlib import Path

DIR = Path(__file__).resolve().parent / "builtin_glossary"

# file name -> the domain name shown in documents (everything else: the file name with _ turned into a space)
DOMAIN_NAMES = {
    "Supply_Chain_Inventory": "Supply Chain & Inventory",
    "HR_People": "HR & People",
    "Banking_Investments": "Banking & Investments",
    "Gaming_Media": "Gaming & Media",
    "Technology_SaaS": "Technology & SaaS",
    "Safety_EHS": "Safety & EHS",
}


def load(folder=DIR):
    entries = []
    for p in sorted(Path(folder).glob("*.csv")):
        domain = DOMAIN_NAMES.get(p.stem, p.stem.replace("_", " "))
        with open(p, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                term, text = (r.get("Term") or "").strip(), (r.get("Definition") or "").strip()
                if not term or not text:
                    continue
                aliases = [a.strip() for a in (r.get("Also known as") or "").replace("|", ";").split(";") if a.strip()]
                better = (r.get("Better") or "").strip().lower()
                entries.append({"terms": [term] + aliases, "category": domain,
                                "better": better if better in ("higher", "lower") else None, "definition": text})
    return entries


SEED = load()
