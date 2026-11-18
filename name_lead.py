"""Offline meaning from the KPI's own name -- no AI, no industry knowledge.

Used when the built-in glossary has no entry, instead of only repeating the report's formula. It does two things a
person would do by reading the name:

  1. Spell out abbreviations that are explained -- the common ones (FTE = full-time equivalent), the ones the report
     spells out itself, and the ones you answered in Needs_Your_Clarification.txt (CB = comeback).
  2. Turn a negative word into plain English:  "% Unscheduled Jobs"  ->  "The percentage of jobs that are not scheduled."

It only answers when it has something real to add (an abbreviation it can spell out in a plain name, or a negative
word to rewrite).
It never guesses: a name that still holds an abbreviation nobody explained gets no lead, so the formula wording is
used and the abbreviation is asked about in Needs_Your_Clarification.txt.
"""
import re

ORIGIN = "Draft built from the KPI name - please verify"

# Abbreviations anyone reading a business report knows. Only the spelling-out -- never a made-up meaning.
SPELLED = {
    "FTE": "full-time equivalent", "YTD": "year to date", "MTD": "month to date", "QTD": "quarter to date",
    "OTD": "on-time delivery", "OTIF": "on time, in full", "SLA": "service level agreement", "NPS": "Net Promoter Score",
    "COGS": "cost of goods sold", "ROI": "return on investment", "YOY": "year over year", "MOM": "month over month",
    "QOQ": "quarter over quarter", "SKU": "stock keeping unit", "PO": "purchase order", "RFQ": "request for quotation",
    "UOM": "unit of measure", "QTY": "quantity", "AVG": "average", "HRS": "hours", "PCT": "percent", "EBIT":
    "earnings before interest and tax", "TRIR": "total recordable incident rate", "WK": "week", "MO": "month", "YR": "year",
    "VS": "versus", "KPI": "key performance indicator",
}
# One extra plain sentence for an abbreviation whose spelled-out form alone does not say what the figure is.
GLOSS = {"FTE": "staff time expressed as a number of full-time employees"}

_PERCENT = {"%", "percent", "percentage", "pct"}
_NOT_NEGATIVE = {"unit", "units", "union", "unions", "unique", "united", "unified", "uniform", "universal", "university",
                 "unity", "under", "undue", "until", "unicode", "unilateral", "unload", "unloading"}
_NON_ADJ = re.compile(r".{3,}(ed|ing|able|ible)$", re.I)
_TOKEN = re.compile(r"%|[A-Za-z0-9&/]+(?:-[A-Za-z0-9]+)*")


def _lower_phrase(text):
    return " ".join(w if (w.isupper() and len(w) > 1) else w.lower() for w in text.split())


def _is_abbr_like(tok, shouting):
    return tok.isupper() and tok.isalpha() and 2 <= len(tok) <= (3 if shouting else 5)


def _negative(tokens):
    """Find 'Un<word>' / 'Non <word>' / 'Not <word>' and rewrite -> (words_before + words_after, root) or None."""
    low = [t.lower() for t in tokens]
    for i, t in enumerate(low):
        if t in ("non", "not") and i + 1 < len(tokens) and _NON_ADJ.match(low[i + 1]):
            root, nouns = low[i + 1], tokens[i + 2:]
            if nouns:
                return tokens[:i] + nouns, root
        if (t.startswith("un") and len(t) >= 6 and t.isalpha() and t not in _NOT_NEGATIVE
                and not t.startswith("under") and i < len(tokens) - 1):
            return tokens[:i] + tokens[i + 1:], t[2:]
    return None


def _plural(word):
    w = word.lower()
    return w.endswith("s") and not w.endswith(("ss", "us", "is"))


def name_lead(name, meanings=None, unit=None, formula_text=None):
    """-> one plain sentence built from the name, or None when the name adds nothing beyond the formula.
    meanings: {'CB': 'comeback'} -- the user's / the report's own explanations.
    formula_text: the formula wording; added after a lead that only spells out an abbreviation, because "Work order (WO)
    headcount." alone says no more than the name does."""
    from checks import split_period                       # imported here: checks imports nothing from this module
    base, period = split_period(name or "")
    toks = _TOKEN.findall(base.replace("%", " % "))
    if not toks:
        return None
    meanings = {k.upper(): v for k, v in (meanings or {}).items() if v}
    percent = unit == "percent" or "%" in (name or "") or any(t.lower() in _PERCENT for t in toks)
    words = [t for t in toks if t.lower() not in _PERCENT]
    if not words:
        return None
    shouting = all(t.isupper() for t in words if len(t) > 3 and t.isalpha()) and any(len(t) > 3 and t.isalpha() for t in words)

    for t in words:                                       # an abbreviation nobody explained -> do not guess
        if _is_abbr_like(t, shouting) and t not in meanings and t not in SPELLED:
            return None
        if re.search(r"\d", t) and re.search(r"[A-Za-z]", t):
            return None

    neg = _negative(words)
    root = None
    if neg:
        words, root = neg
    spelled, gloss = [], []

    def expand(tok):
        up = tok.upper()
        if _is_abbr_like(tok, shouting) and (up in meanings or up in SPELLED):
            meaning = meanings.get(up) or SPELLED[up]
            if up not in spelled:
                spelled.append(up)
                if up in GLOSS and up not in meanings:
                    gloss.append(GLOSS[up])
            return f"{_lower_phrase(meaning.rstrip('.'))} ({up})"
        return tok if (tok.isupper() and len(tok) > 1 and not shouting) else tok.lower()

    phrase = " ".join(expand(t) for t in words)
    if root is None and (not spelled or percent):          # nothing to rewrite (a percentage name that only needs
        return None                                         # abbreviations spelled out reads better from the formula)
    if root is not None:
        phrase += (" that are not " if _plural(words[-1]) else " that is not ") + root
    if percent:
        text = "The percentage of " + phrase
    else:
        text = phrase[0].upper() + phrase[1:]
    if gloss and not percent and root is None:
        text += ": " + gloss[0]
    text = text.rstrip(".")
    text = text[0].upper() + text[1:] + "."
    if root is None and not gloss and formula_text:
        text += " " + formula_text
    if period:
        text += f" (Period shown: {period}.)"
    return text
