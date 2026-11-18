"""Offline meaning for a KPI name that is a known term plus a modifier -- no AI, no guessing.

Reports often write the same measure many times with a small change in the name:

    Actual_value, Actual Value_yarn            -> the built-in meaning of "Actual"
    Previous month_actual, Previous year_actual -> "Actual", for the previous month / year
    Rate(Rs/Kg), Rate (USD/QTY)                 -> "Rate", measured in rupees per kilogram / US dollars per quantity

The name is split at "_" and at brackets. Every piece must be one of: a known built-in term (the core, found once), a
"previous month / prior year ..." phrase, a plain filler word (value, amount, figure), a "A/B" unit in brackets, or one
short label at the end ("yarn"). A name with any other words in it is left alone, so "Actual Hours Lost" never becomes
"Actual".
"""
import re

ORIGIN = "Draft built from the KPI name - please verify"

_FILLER = {"value", "values", "amount", "figure", "figures", "measure", "calc", "calculation"}
_SHIFT = re.compile(r"^(?:previous|prior|prev|last|py|ly)\s+(month|year|quarter|week|day|period|fiscal year)$", re.I)
_SHIFT_ABBR = {"py": "year", "ly": "year", "pm": "month", "lm": "month"}
_UNIT = re.compile(r"^([A-Za-z]{1,6})\s*/\s*([A-Za-z]{1,6})$")
_PIECES = re.compile(r"\(([^)]*)\)|([^_()]+)")

# Currency and measure codes: only the spelling out, never a made-up meaning (singular form for the "per" side).
UNITS = {"USD": ("US dollars", "US dollar"), "INR": ("Indian rupees", "Indian rupee"), "RS": ("rupees", "rupee"),
         "EUR": ("euros", "euro"), "GBP": ("pounds sterling", "pound sterling"), "KG": ("kilograms", "kilogram"),
         "GM": ("grams", "gram"), "LB": ("pounds", "pound"), "MT": ("metric tonnes", "metric tonne"),
         "QTY": ("quantity", "quantity"), "HR": ("hours", "hour"), "HRS": ("hours", "hour"), "PC": ("pieces", "piece"),
         "PCS": ("pieces", "piece"), "LTR": ("litres", "litre"), "L": ("litres", "litre"), "M": ("metres", "metre"),
         "SQM": ("square metres", "square metre"), "UNIT": ("units", "unit")}


def _unit_sentence(a, b, meanings):
    def one(tok, singular):
        up = tok.upper()
        if up in (meanings or {}):
            return meanings[up].rstrip(".").lower()
        if up in UNITS:
            return UNITS[up][1 if singular else 0]
        return tok
    return f"Measured in {one(a, False)} per {one(b, True)}."


def _strip_filler(piece):
    words = piece.split()
    kept = [w for w in words if w.lower() not in _FILLER]
    return " ".join(kept), len(kept) != len(words)


def unit_in_name(name, meanings=None):
    """'Rate (USD/QTY)' -> 'Measured in US dollars per quantity.' (or None)."""
    for m in re.finditer(r"\(([^)]*)\)", name or ""):
        u = _UNIT.match(m.group(1).strip())
        if u:
            return _unit_sentence(u.group(1), u.group(2), meanings)
    return None


def compose_lead(name, seed_for, meanings=None):
    """-> (text, origin) or None.  seed_for(term) -> {'definition': ..} or None (the built-in glossary, exact match)."""
    if not name:
        return None
    core = shift = variant = unit = None
    core_text = ""
    pieces = [(m.group(1), m.group(2)) for m in _PIECES.finditer(name)]
    if len(pieces) < 2 and not re.search(r"[(]", name):
        return None                                   # 'Actual Value' alone: the glossary or the formula handles it
    for bracket, plain in pieces:
        if bracket is not None:
            m = _UNIT.match(bracket.strip())
            if not m or unit:
                return None
            unit = (m.group(1), m.group(2))
            continue
        piece = re.sub(r"\s+", " ", plain.replace("-", " ")).strip()
        if not piece:
            continue
        m = _SHIFT.match(piece)
        if m and shift is None:
            shift = "previous " + m.group(1).lower() if m.group(1).lower() != "period" else "previous period"
            continue
        if piece.lower() in _SHIFT_ABBR and shift is None:
            shift = "previous " + _SHIFT_ABBR[piece.lower()]
            continue
        base, had_filler = _strip_filler(piece)
        if not base:
            continue                                   # 'value' on its own
        s = seed_for(base) if core is None else None
        if s:
            core, core_text = base, s["definition"]
            continue
        if (core is not None and variant is None and not (base.isupper() and len(base) <= 4)   # 'INR' is a code, not a label
                and re.fullmatch(r"[A-Za-z][A-Za-z ]{1,24}", base) and len(base.split()) <= 2):
            variant = base
            continue
        return None
    if core is None:
        return None
    if shift is None and unit is None and variant is None and not any(p[1] and _strip_filler(p[1].strip())[1] for p in pieces):
        return None
    c = core.lower()
    text = (f"The {c} figure for the {shift}. {core[:1].upper() + core[1:]}: {core_text[:1].lower() + core_text[1:]}"
            if shift else core_text)
    if unit:
        text = text.rstrip() + " " + _unit_sentence(unit[0], unit[1], meanings)
    if variant:
        text = text.rstrip() + f" (Variant: {variant}.)"
    return text, ORIGIN
