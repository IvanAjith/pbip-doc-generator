"""Offline drafts: turns the plain-English formula the tool already derived from a measure's DAX into a
one-sentence definition. Nothing here knows about any industry -- it only rephrases the formula's own words.
The result is always labelled as a draft: it says *how* the figure is calculated, not what the business
means by it, so a person must confirm it."""
import re

ORIGIN = "Draft built from the report's formula - please verify"

_OPS = {"÷": "divided by", "×": "multiplied by", "−": "minus", "+": "plus"}
_LEADS = [
    (r"^total (?=\S)", "The total of "),
    (r"^number of distinct (?=\S)", "The number of distinct "),
    (r"^count of (?=\S)", "The count of "),
    (r"^average number of (?=\S)", "The average number of "),
    (r"^average (?=\S)", "The average of "),
    (r"^highest (?=\S)", "The highest "),
    (r"^lowest (?=\S)", "The lowest "),
    (r"^absolute value of (?=\S)", "The absolute value of "),
    (r"^number of (?=\S)", "The number of "),
]


def _split_top(text):
    """Split at operators that are outside brackets: [(operand, op_before)]."""
    out, depth, cur, last_op, i = [], 0, "", None, 0
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if depth == 0 and ch in _OPS and i > 0 and text[i - 1] == " " and text[i + 1:i + 2] == " ":
            out.append((cur.strip(), last_op))
            cur, last_op, i = "", ch, i + 2
            continue
        cur += ch
        i += 1
    out.append((cur.strip(), last_op))
    return out


def _lead(text):
    for pat, rep in _LEADS:
        if re.match(pat, text, re.I):
            return re.sub(pat, rep, text, count=1, flags=re.I)
    return None


def _strip_outer(text):
    t = text.strip()
    if t.startswith("(") and t.endswith(")"):
        depth = 0
        for i, ch in enumerate(t):
            depth += ch == "("
            depth -= ch == ")"
            if depth == 0 and i < len(t) - 1:
                return t
        return t[1:-1]
    return t


def formula_draft(calc, unit=None, inputs=None):
    """-> one sentence, or None when there is no formula to rephrase."""
    if not calc or not calc.strip():
        if inputs:
            names = list(dict.fromkeys(inputs))[:6]
            joined = ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else names[0]
            return f"Built from {joined}; the logic is too involved to summarise automatically."
        return None
    core, suffix = calc.strip(), ""
    if " — all " in core:
        core, suffix = core.split(" — all ", 1)
        suffix = ", all " + suffix
    parts = _split_top(_strip_outer(core))
    if unit == "percent" and len(parts) > 1 and parts[-1] == ("100", "\u00d7"):
        parts = _split_top(_strip_outer(" ".join(
            (op_ + " " if op_ else "") + o for o, op_ in parts[:-1]))) if len(parts) > 2 else _split_top(_strip_outer(parts[0][0]))
    if len(parts) == 1:
        one = re.sub(r" \((counting only rows where [^()]+)\)$", r", \1", parts[0][0])
        body = _lead(one) or ("Shows " + one)
    elif len(parts) == 2 and parts[1][1] == "\u00f7" and unit == "percent":
        body = f"{_cap(parts[0][0])} as a percentage of {parts[1][0]}"
    else:
        words = []
        for k, (operand, op) in enumerate(parts):
            if op:
                words.append(_OPS[op])
            words.append((_lead(operand) or operand) if k == 0 else operand)
        body = " ".join(words)
    body = re.sub(r"\s+", " ", body + suffix).strip()
    for sym, word in _OPS.items():                    # operators left inside brackets
        body = body.replace(f" {sym} ", f" {word} ")
    return (body[0].upper() + body[1:] if body else body).rstrip(".") + "."


def _cap(t):
    return t[0].upper() + t[1:] if t else t
