"""domain_detect.py -- works out the business domain of a report by itself, so nobody has to type a Domain: line.

It reads the names in the report (pages, tables, KPIs) and scores them two ways:
  1. keywords: domains_catalog.csv lists 120+ industries, each with the words that show up in its reports
  2. the built-in glossary: every KPI that matches a built-in term votes for that term's domain
The domain with the most evidence wins; with too little evidence the answer is "General".
A "Domain:" line typed in context.txt always wins (checks.Context reads it), so this is only used when nobody typed one.
"""
import csv
import re
from collections import Counter
from pathlib import Path

CATALOG = Path(__file__).resolve().parent / "domains_catalog.csv"
MIN_SCORE = 3            # evidence needed before a domain is named
# Business functions show up in every industry's report (a hospital has finance and customer KPIs too), so an industry
# wins unless a function has more than twice its evidence.
FUNCTIONS = {"Finance", "Sales", "Marketing", "Customer", "Operations", "Supply Chain & Inventory", "Procurement", "Quality",
             "Safety", "HR & People", "Accounting & Audit", "Project Management Office", "Customer Experience & Contact Strategy"}


def _load(path=CATALOG):
    out = {}
    p = Path(path)
    if not p.exists():
        return out
    with open(p, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            d = (r.get("Domain") or "").strip()
            words = [w.strip().lower() for w in (r.get("Keywords") or "").split(";") if w.strip()]
            if d and words:
                out[d] = words
    return out


def _squash(text):
    return " " + " ".join(re.findall(r"[a-z0-9]+", (text or "").lower())) + " "


def _has(text, word):
    w = " ".join(re.findall(r"[a-z0-9]+", word))
    return bool(w) and (f" {w} " in text or f" {w}s " in text or f" {w}es " in text)


def score(names, seed_category=None, catalog=None):
    """-> Counter {domain: evidence}. names: report text (pages, tables, KPI names). seed_category: name -> built-in domain or None."""
    catalog = _load() if catalog is None else catalog
    hay = _squash(" | ".join(n for n in names if n))
    sc = Counter()
    for domain, words in catalog.items():
        hits = sum(1 for w in words if _has(hay, w))
        if hits:
            sc[domain] += hits
    if seed_category:
        for n in names:
            c = seed_category(n)
            if c and c != "General":
                sc[c] += 1
    return sc


def detect(names, seed_category=None, catalog=None):
    """-> (domain, evidence). 'General' when no domain has MIN_SCORE evidence."""
    sc = score(names, seed_category, catalog)
    if not sc:
        return "General", 0
    ranked = sorted(sc.items(), key=lambda kv: (-kv[1], kv[0]))          # ties: alphabetical, so the answer is stable
    ind = next(((d, v) for d, v in ranked if d not in FUNCTIONS), (None, 0))
    fun = next(((d, v) for d, v in ranked if d in FUNCTIONS), (None, 0))
    if ind[0] and ind[1] >= MIN_SCORE and ind[1] * 2 >= fun[1]:
        return ind
    if fun[0] and fun[1] >= MIN_SCORE:
        return fun
    return "General", ranked[0][1]
