"""checks.py -- the tool checks every AI definition against what it actually sent, before it is allowed into a document.

Why: an AI that sees only a measure's name and formula wording will sometimes fill the gaps with a guess: a number that
is not in the report, an abbreviation it expanded on its own ("CB" -> "customer bracket"), or text copied from a
neighbouring measure. Nothing here knows any industry; every check compares the AI's sentence with the facts sent.

A draft that fails a HARD check is thrown away and the measure keeps its formula-based draft (accurate, if plain).
A draft that fails only a SOFT check is kept and its Source cell says what to look at.

Optional file  glossary/context.txt  (next to glossary.json) tells the AI, and these checks, what the company means:

    Domain: manufacturing (engraving and mold making)
    CB = chargeback
    EOL = end of line

Abbreviations the AI had to guess are collected into that file automatically, so you only have to fill in the meanings.
"""
import re
from difflib import SequenceMatcher
from pathlib import Path

CONTEXT_NAME = "context.txt"

# Abbreviations anyone reading a business report knows; an AI spelling them out is not a guess.
UNIVERSAL = {
    "KPI", "YTD", "MTD", "QTD", "FTE", "NPS", "EBIT", "ROI", "SLA", "OTD", "OTIF", "PL", "YOY", "MOM", "QOQ", "USD",
    "EUR", "GBP", "INR", "CAD", "AVG", "PCT", "QTY", "HR", "HRS", "ID", "IDS", "UOM", "SKU", "PO", "RFQ", "COGS",
    "SG", "YR", "MO", "WK", "VS", "TRIR", "OSHA", "CEO", "CFO", "VOC",
}

_GENERIC = {  # words a definition may add without being 'invented facts' (first four letters)
    "meas", "indi", "perc", "prop", "rati", "tota", "coun", "numb", "aver", "calc", "divi", "repr", "trac", "perf",
    "effi", "prod", "stat", "badg", "show", "disp", "base", "wher", "whic", "thei", "spec", "part", "give", "peri",
    "time", "mont", "week", "year", "dail", "curr", "over", "valu", "reco", "rows", "used", "usin", "comp", "rela",
    "with", "duri", "acro", "each", "ever", "othe", "betw", "agai", "same", "thos", "thes", "ther", "equa", "grea",
    "high", "lowe", "belo", "abov", "amou", "sums", "comb", "diff", "mini", "plus", "thro", "into", "from", "that",
    "this", "when", "than", "only", "also", "more", "most", "less", "such", "both", "unde", "afte", "befo", "cond",
    "crit", "thre", "targ", "indu", "gene", "usua", "typi", "refl", "capt", "summ", "tota", "volu", "leve", "rate",
    "scor", "metr", "figu", "resu", "outc", "anal", "monit", "asse", "eval", "deter", "iden", "cate", "grou", "size",
    "fully", "full", "part", "share", "whol", "sing", "mult", "elig", "qual", "appl", "refe", "need", "requ", "allo",
    "assi", "unal", "avai", "cons", "expe", "actu", "real", "plan", "sche", "comp", "open", "clos", "stil", "alre",
}
_STOP = set("""about above after again against all also and any are because been before being below between both but
 can could did does doing down during each few for from further had has have having here how into its itself just more
 most not off once only other our out over own same should some such than that the their them then there these they
 this those through under until very was were what when where which while who whom will with would your""".split())

_FILLER = [
    # ", shown on the Overview page of the Standex V5 report"  /  " on the Efficiency page"
    re.compile(r"[,;]?\s*(?:and\s+)?(?:(?:is|are|as)\s+)?(?:shown|displayed|found|tracked|reported|used|measured|visible)?"
               r"\s*(?:on|in)\s+the\s+[A-Za-z0-9 &/\-]{1,40}?\s+page(?:\s+(?:of|in)\s+the\s+[A-Za-z0-9 .&\-]{1,50}?\s+report)?"
               r"(?=\s*[.,;]|\s*$|\s+(?:to|for|and)\b)", re.I),
    re.compile(r"[,;]?\s*(?:shown|displayed|found|used|tracked)\s+in\s+the\s+[A-Za-z0-9 .&\-]{1,50}?\s+report(?=\s*[.,;]|\s*$)", re.I),
]


# ------------------------------------------------------------------ facts
def facts_text(term, calc="", basis="", page="", rules=(), **_):
    """The words the AI is given about one measure (the DAX is never part of this)."""
    return " ".join([term or "", calc or "", basis or "", page or "", " ".join(rules or [])])


def initials_definitions(texts):
    """'Direct Labour (DL) FT' -> {'DL': 'Direct Labour'}: abbreviations the report itself spells out."""
    out = {}
    for t in texts:
        for m in re.finditer(r"((?:[A-Za-z][A-Za-z]+\s+){1,4})\(([A-Z]{2,6})\)", t or ""):
            abbr = m.group(2)
            words = [h for w in m.group(1).split() for h in re.findall(r"[A-Z][a-z]*|[a-z]+", w)]   # InDirect -> In Direct
            tail = words[-len(abbr):]
            if len(tail) == len(abbr) and all(w[0].upper() == a for w, a in zip(tail, abbr)):
                out.setdefault(abbr, " ".join(tail))
    return out


# ------------------------------------------------------------------ context file
class Context:
    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.domain = ""
        self.abbr = {}                         # 'CB' -> 'chargeback'
        self.auto = {}                         # spelled out in the report itself
        if self.path and self.path.exists():
            try:
                self._read(self.path.read_text(encoding="utf-8-sig"))
            except OSError:
                pass

    def _read(self, text):
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"(?i)^(?:domain|industry|about)\s*:\s*(.+)$", line)
            if m:
                self.domain = m.group(1).strip()
                continue
            m = re.match(r"^([A-Za-z][A-Za-z0-9&/]{0,7})\s*(?:=|:|-)\s*(\S.*)$", line)
            if m:
                self.abbr[m.group(1).upper()] = m.group(2).strip()

    def learn_from_report(self, texts):
        self.auto.update(initials_definitions(texts))

    def known(self, token):
        t = token.upper()
        return t in UNIVERSAL or t in self.abbr or t in self.auto

    def prompt_lines(self):
        """Extra facts for the AI."""
        lines = []
        if self.domain:
            lines.append(f"Business domain: {self.domain}")
        known = {**self.auto, **self.abbr}
        if known:
            lines.append("Abbreviations used in this report: " + "; ".join(f"{k} = {v}" for k, v in sorted(known.items())))
        return lines

    def write_template(self, tokens):
        """Create context.txt listing the abbreviations the AI had to guess, or add the missing ones to the existing
        file (never touching what is already there). -> True when the file was created or extended."""
        if not self.path or not tokens:
            return False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                have = self.path.read_text(encoding="utf-8-sig")
                new = [t for t in sorted(tokens) if not re.search(r"(?im)^\s*#?\s*" + re.escape(t) + r"\s*(=|:|-)", have)]
                if not new:
                    return False
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(("" if have.endswith("\n") else "\n") + "".join(f"{t} = \n" for t in new))
                return True
            lines = ["# Optional. Tells the AI (and the tool's checks) what your company means, so it stops guessing.",
                     "# One line per abbreviation:   CB = chargeback      Leave blank the ones you do not know.",
                     "# Then run the tool again. Lines starting with # are ignored.",
                     "", "Domain: ", ""]
            lines += [f"{t} = " for t in sorted(tokens)]
            self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return True
        except OSError:
            return False


# ------------------------------------------------------------------ the checks
def _numbers(text):
    """Numbers as written ('V5' and '5S' are names, not numbers)."""
    return {n.replace(",", "") for n in re.findall(r"(?<![A-Za-z0-9])\d[\d,]*(?:\.\d+)?(?![A-Za-z])", text or "")}


_SKIP = {"of", "and", "the", "a", "an", "for", "to", "in", "on"}


def spelled_out(token, text):
    """True when `text` writes the abbreviation out in words: 'CB' -> 'customer bracket', 'DOC' -> 'document'.
    Keeping the token as written (or only adding a plural / -ing) is not an expansion."""
    low, tok = (text or "").lower(), token.lower()
    if re.search(r"\b" + re.escape(tok) + r"(?:s|es|ing|ed|er|ers)?\b", low):
        return False
    words = [w for w in re.split(r"[^a-z0-9]+", low) if w]
    sig = [w for w in words if w not in _SKIP]
    n = len(tok)
    for ws in (words, sig):
        for i in range(len(ws) - n + 1):
            if "".join(w[0] for w in ws[i:i + n]) == tok:
                return True
    return n >= 3 and any(w.startswith(tok) and len(w) > n + 3 for w in words)


def _stems(text):
    return {w[:4] for w in re.findall(r"[a-z]{4,}", (text or "").lower())}


def clean_text(text):
    """Remove 'shown on the X page of the Y report' tails (the document already says where a measure is shown)."""
    t = re.sub(r"\s+", " ", text or "").strip()
    for rx in _FILLER:
        t = rx.sub("", t)
    t = re.sub(r"\s+([.,;])", r"\1", t).strip(" ,;")
    if t and not t.endswith("."):
        t += "."
    return t


_RATIO_WORDS = re.compile(r"percent|proportion|ratio|share|rate|divid|\bper\b|out of|average|fraction|relative|versus|"
                          r"compared|÷|%|against", re.I)
_RATIO_IN_FACTS = re.compile(r"percentage of|÷|divided by|per ", re.I)


class Result:
    def __init__(self, text):
        self.text, self.hard, self.soft, self.guessed = text, [], [], []

    @property
    def ok(self):
        return not self.hard


class Checker:
    def __init__(self, context=None):
        self.context = context or Context()
        self.accepted = []                    # [(normalised text, term)]
        self.rejected = []                    # [(term, reasons)]
        self.guessed = set()                  # abbreviations an AI draft had to guess
        self.flagged = []                     # [(term, soft reasons)]

    def validate(self, term, text, facts, register=True):
        res = Result(clean_text(text))
        t, low = res.text, res.text.lower()
        f = facts or ""
        # 1. numbers that were never supplied
        extra = _numbers(t) - _numbers(f)
        if extra:
            res.hard.append("number(s) not in the report: " + ", ".join(sorted(extra)))
        # 2. an abbreviation spelled out by the AI that nobody defined
        for tok in sorted(set(re.findall(r"\b[A-Z]{2,5}\b", (term or "") + " " + f))):
            if self.context.known(tok):
                continue
            if spelled_out(tok, t):
                res.guessed.append(tok)
        if res.guessed:
            res.hard.append("AI wrote its own meaning for: " + ", ".join(res.guessed))
        # 3. a percentage / division in the formula must read as a ratio
        if _RATIO_IN_FACTS.search(f) and not _RATIO_WORDS.search(t):
            res.hard.append("the formula is a ratio but the sentence does not describe one")
        # 4. text copied from another measure
        norm = re.sub(r"[^a-z0-9 ]", "", low)[:200]
        for other, who in self.accepted:
            if who != term and SequenceMatcher(None, norm, other).ratio() >= 0.95:
                res.hard.append(f"almost the same sentence as '{who}'")
                break
        # 5. (soft) several content words that appear nowhere in what was sent
        known = _stems(f) | {s for s in _GENERIC}
        ctx_words = _stems(" ".join(self.context.prompt_lines()))
        odd = []
        for w in re.findall(r"[a-z]{5,}", low):
            if w in _STOP or w[:4] in known or w[:4] in ctx_words or w in odd:
                continue
            odd.append(w)
        if len(odd) >= 3:
            res.soft.append("check these words, they are not in the report: " + ", ".join(odd[:4]))
        if register:
            if res.ok:
                self.accepted.append((norm, term))
                if res.soft:
                    self.flagged.append((term, res.soft))
            else:
                self.rejected.append((term, res.hard))
                self.guessed.update(res.guessed)
        return res
