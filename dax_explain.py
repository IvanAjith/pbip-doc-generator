"""
dax_explain.py -- turns DAX into plain English, using only what the DAX says.

Nothing here knows about any particular business. It tokenizes and parses
DAX into a small syntax tree, then:

  * describe_measure()  -- "Recordable Incidents / Total Hours Worked x 200,000"
  * colour_rules()      -- the colour logic a measure contains, e.g.
                           [("TRIR > 2", "#D32F2F", "Critical"), ...]
  * card_label()        -- the text an HTML-card measure prints as its label

Everything returns None / [] when the DAX does not contain the evidence, so
callers can leave a statement out instead of guessing.
"""
import html as _html
import re

# ---------------------------------------------------------------- comments

def strip_comments(text: str) -> str:
    """Remove // -- and /* */ comments without touching string literals."""
    out, i, n = [], 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == '"':
                if i + 1 < n and text[i + 1] == '"':
                    out.append('"')
                    i += 1
                else:
                    in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        elif text.startswith("//", i) or text.startswith("--", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        else:
            out.append(c)
            i += 1
    return "".join(out)


# ---------------------------------------------------------------- tokenizer

_TOKEN_RE = re.compile(r"""
 (?P<ws>\s+)
|(?P<str>"(?:[^"]|"")*")
|(?P<num>\d+(?:\.\d+)?(?:[eE][+-]?\d+)?[dD]?(?![\w]))
|(?P<qcol>'(?:[^']|'')+'\[(?:[^\]]|\]\])+\])
|(?P<col>[^\W\d][\w.]*\[(?:[^\]]|\]\])+\])
|(?P<meas>\[(?:[^\]]|\]\])+\])
|(?P<qtable>'(?:[^']|'')+')
|(?P<op><=|>=|<>|&&|\|\||==|[-+*/&=<>^(),{}])
|(?P<ident>[^\W\d][\w.]*)
""", re.X)


def tokenize(text):
    toks, pos = [], 0
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if not m:
            raise ValueError(f"cannot tokenize at {pos}: {text[pos:pos+20]!r}")
        pos = m.end()
        kind = m.lastgroup
        if kind == "ws":
            continue
        toks.append((kind, m.group()))
    return toks


# ---------------------------------------------------------------- parser

class ParseError(Exception):
    pass


class _Parser:
    def __init__(self, toks):
        self.t = toks
        self.i = 0

    def peek(self, k=0):
        j = self.i + k
        return self.t[j] if j < len(self.t) else (None, None)

    def take(self):
        tok = self.t[self.i]
        self.i += 1
        return tok

    def is_op(self, *ops):
        k, v = self.peek()
        return k == "op" and v in ops

    def expect_op(self, op):
        if not self.is_op(op):
            raise ParseError(f"expected {op!r} got {self.peek()}")
        self.take()

    def parse_top(self):
        node = self.parse_expr()
        if self.i != len(self.t):
            raise ParseError(f"trailing tokens at {self.i}: {self.peek()}")
        return node

    def parse_expr(self):
        k, v = self.peek()
        if k == "ident" and v.upper() == "VAR":
            vars_ = []
            while self.peek()[0] == "ident" and self.peek()[1].upper() == "VAR":
                self.take()
                name = self.take()[1]
                self.expect_op("=")
                vars_.append((name, self.parse_expr()))
            k, v = self.peek()
            if not (k == "ident" and v.upper() == "RETURN"):
                raise ParseError("expected RETURN")
            self.take()
            return ("block", vars_, self.parse_expr())
        return self.parse_or()

    def _left(self, sub, ops, tag="bin"):
        node = sub()
        while self.is_op(*ops):
            op = self.take()[1]
            node = (tag, op, node, sub())
        return node

    def parse_or(self):
        return self._left(self.parse_and, ("||",))

    def parse_and(self):
        return self._left(self.parse_cmp, ("&&",))

    def parse_cmp(self):
        node = self.parse_concat()
        while True:
            if self.is_op("=", "==", "<>", "<", "<=", ">", ">="):
                op = self.take()[1]
                node = ("bin", op, node, self.parse_concat())
            elif self.peek()[0] == "ident" and self.peek()[1].upper() == "IN":
                self.take()
                node = ("bin", "IN", node, self.parse_concat())
            else:
                return node

    def parse_concat(self):
        return self._left(self.parse_add, ("&",))

    def parse_add(self):
        return self._left(self.parse_mul, ("+", "-"))

    def parse_mul(self):
        return self._left(self.parse_unary, ("*", "/"))

    def parse_unary(self):
        k, v = self.peek()
        if k == "ident" and v.upper() == "NOT" and self.peek(1) != ("op", "("):
            self.take()
            return ("call", "NOT", [self.parse_unary()])
        if self.is_op("-"):
            self.take()
            return ("un", "-", self.parse_unary())
        if self.is_op("+"):
            self.take()
            return self.parse_unary()
        return self.parse_pow()

    def parse_pow(self):
        node = self.parse_primary()
        while self.is_op("^"):
            self.take()
            node = ("bin", "^", node, self.parse_primary())
        return node

    def parse_primary(self):
        k, v = self.peek()
        if k is None:
            raise ParseError("unexpected end")
        if k == "num":
            self.take()
            return ("num", float(v.rstrip("dD")))
        if k == "str":
            self.take()
            return ("str", v[1:-1].replace('""', '"'))
        if k == "qcol":
            self.take()
            m = re.match(r"'((?:[^']|'')+)'\[((?:[^\]]|\]\])+)\]$", v)
            return ("col", m.group(1).replace("''", "'"), m.group(2).replace("]]", "]"))
        if k == "col":
            self.take()
            i = v.index("[")
            return ("col", v[:i], v[i + 1:-1].replace("]]", "]"))
        if k == "meas":
            self.take()
            return ("meas", v[1:-1].replace("]]", "]"))
        if k == "qtable":
            self.take()
            return ("table", v[1:-1].replace("''", "'"))
        if k == "op" and v == "(":
            self.take()
            e = self.parse_expr()
            self.expect_op(")")
            return e
        if k == "op" and v == "{":
            self.take()
            items = []
            while not self.is_op("}"):
                items.append(self.parse_expr())
                if self.is_op(","):
                    self.take()
            self.take()
            return ("list", items)
        if k == "ident":
            self.take()
            if self.is_op("("):
                self.take()
                args = []
                if not self.is_op(")"):
                    while True:
                        if self.is_op(",", ")"):      # empty argument slot
                            args.append(("blank",))
                        else:
                            args.append(self.parse_expr())
                        if self.is_op(","):
                            self.take()
                            continue
                        break
                self.expect_op(")")
                if v.upper() in ("TRUE", "FALSE") and not args:
                    return ("bool", v.upper() == "TRUE")
                return ("call", v.upper(), args)
            if v.upper() in ("TRUE", "FALSE"):
                return ("bool", v.upper() == "TRUE")
            if v.upper() == "BLANK":
                return ("blank",)
            return ("id", v)
        raise ParseError(f"unexpected token {k} {v!r}")


def parse_dax(expr: str):
    """Parse a DAX expression into a tuple tree, or return None if the
    syntax is outside what this parser understands."""
    text = strip_comments(expr or "").replace("```", "").strip()
    if text.startswith("="):
        text = text[1:]
    if not text.strip():
        return None
    try:
        return _Parser(tokenize(text)).parse_top()
    except (ParseError, ValueError, IndexError, RecursionError):
        return None


# ---------------------------------------------------------------- naming

_TABLE_PREFIX_RE = re.compile(r"^(?:vw|v|dim|fact|fct|tbl|stg)_", re.I)
_SMALL_WORDS = {"of", "to", "in", "on", "at", "by", "or", "and", "the", "per", "vs",
                "for", "a", "an", "as", "is", "no", "it", "if", "from", "with"}


def _split_words(name: str):
    name = name.replace("_", " ").replace("-", " ").strip()
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    return [w for w in name.split() if w]


def humanize_column(col: str) -> str:
    """RECORDABLE_INCIDENTS -> 'Recordable Incidents'; DL_CLOCKED_HOURS ->
    'DL Clocked Hours'. Mixed-case names are left as authored."""
    if col != col.upper() and col != col.lower():
        return col.replace("_", " ").strip()
    if "_" not in col and " " not in col and col.isupper() and len(col) <= 5:
        return col
    words = _split_words(col)
    out = []
    for i, w in enumerate(words):
        lw = w.lower()
        if i > 0 and lw in _SMALL_WORDS:
            out.append(lw)
        elif len(w) <= 3 and w.isupper() and lw not in _SMALL_WORDS:
            out.append(w)
        else:
            out.append(w.capitalize())
    return " ".join(out)


def humanize_table(name: str) -> str:
    n = name
    while _TABLE_PREFIX_RE.match(n):
        n = _TABLE_PREFIX_RE.sub("", n, count=1)
    return humanize_column(n) or name


def humanize_var(name: str) -> str:
    n = name.lstrip("_")
    if not n:
        return name
    if re.fullmatch(r"[A-Z][a-z][A-Z]", n):                                       # YoY, MoM, QoQ
        return n
    if " " not in n and "_" not in n and n != n.upper() and n != n.lower():      # camelCase
        n = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", n)
        n = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", n)
        return n
    return humanize_column(n)


_NUM_FMT = lambda v: (f"{int(v):,}" if float(v).is_integer() else f"{v:g}")  # noqa: E731

_SYM = {"<=": "≤", ">=": "≥", "<>": "≠", "=": "=", "==": "=", "<": "<", ">": ">"}

_TARGET_VAR_RE = re.compile(r"(tgt|target|threshold|goal|benchmark|budget|limit)", re.I)

_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_CSS_COLOURS = {"red", "green", "amber", "orange", "yellow", "blue", "grey", "gray", "black",
                "white", "purple", "pink", "teal", "brown", "gold", "crimson", "maroon",
                "navy", "lime", "olive", "silver", "cyan", "magenta"}


def is_colour_literal(s: str) -> bool:
    s = s.strip()
    return bool(_HEX_RE.match(s)) or s.lower() in _CSS_COLOURS


def hex_to_name(c: str) -> str:
    """Name a colour by hue/saturation/lightness -- no lookup of what a
    colour 'means', just what it looks like."""
    c = c.strip()
    if c.lower() in _CSS_COLOURS:
        return "grey" if c.lower() == "gray" else c.lower()
    h = c.lstrip("#")
    if len(h) in (3, 4):
        h = "".join(ch * 2 for ch in h[:3])
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2
    d = mx - mn
    if d < 0.06:
        return "white" if l > 0.9 else "black" if l < 0.15 else "grey"
    s = d / (1 - abs(2 * l - 1)) if 0 < l < 1 else 0
    if mx == r:
        hue = ((g - b) / d) % 6
    elif mx == g:
        hue = (b - r) / d + 2
    else:
        hue = (r - g) / d + 4
    hue *= 60
    if s < 0.18:
        return "grey"
    if hue < 15 or hue >= 345:
        name = "red"
    elif hue < 28:
        name = "orange" if l > 0.35 else "brown"
    elif hue < 65:
        name = "amber" if hue < 52 else "yellow"
    elif hue < 175:
        name = "green"
    elif hue < 200:
        name = "teal"
    elif hue < 255:
        name = "blue"
    elif hue < 290:
        name = "purple"
    else:
        name = "pink"
    if l < 0.22 and name != "brown":
        return "dark " + name
    if l > 0.88:
        return "light " + name
    return name


# ---------------------------------------------------------------- explainer

_TIME_FN = {
    "DATESMTD": "month to date", "DATESQTD": "quarter to date", "DATESYTD": "year to date",
    "TOTALMTD": "month to date", "TOTALQTD": "quarter to date", "TOTALYTD": "year to date",
    "SAMEPERIODLASTYEAR": "same period last year",
}
_MAX_LEN = 260


class Explainer:
    """Describes DAX measures. `measures` maps name -> measure dict with an
    'expression' key; results are cached per measure name."""

    def __init__(self, measures_by_name):
        self.measures = measures_by_name
        self._ast = {}
        self._desc = {}
        self._consumed = set()

    # ------------------------------------------------------------ plumbing
    def ast(self, name):
        if name not in self._ast:
            m = self.measures.get(name)
            self._ast[name] = parse_dax(m["expression"]) if m else None
        return self._ast[name]

    def _lookup_measure(self, name):
        if name in self.measures:
            return name
        low = name.lower()
        for k in self.measures:
            if k.lower() == low:
                return k
        return None

    # ------------------------------------------------------------ constants
    def const(self, node, env, depth=0):
        """Numeric value of a constant sub-expression, else None."""
        if depth > 6 or node is None:
            return None
        k = node[0]
        if k == "num":
            return node[1]
        if k == "id" and node[1] in env:
            return self.const(env[node[1]], env, depth + 1)
        if k == "un":
            v = self.const(node[2], env, depth + 1)
            return -v if v is not None else None
        if k == "bin" and node[1] in "+-*/":
            a, b = self.const(node[2], env, depth + 1), self.const(node[3], env, depth + 1)
            if a is None or b is None:
                return None
            try:
                return {"+": a + b, "-": a - b, "*": a * b, "/": a / b}[node[1]]
            except ZeroDivisionError:
                return None
        if k == "call" and node[1] in ("ROUND", "FIXED") and node[2]:
            return self.const(node[2][0], env, depth + 1)
        return None

    # ------------------------------------------------------------ conditions
    def cond(self, node, env, depth=0):
        if node is None or depth > 6:
            return None
        k = node[0]
        if k == "id" and node[1] in env:
            return self.cond(env[node[1]], env, depth + 1)
        if k == "bin" and node[1] in _SYM:
            l = self._operand(node[2], env, depth + 1)
            r = self._operand(node[3], env, depth + 1)
            if l and r:
                return f"{l} {_SYM[node[1]]} {r}"
            return None
        if k == "bin" and node[1] in ("&&", "||"):
            l, r = self.cond(node[2], env, depth + 1), self.cond(node[3], env, depth + 1)
            if l and r:
                return f"{l} {'and' if node[1] == '&&' else 'or'} {r}"
            return None
        if k == "call" and node[1] == "ISBLANK" and node[2]:
            o = self._operand(node[2][0], env, depth + 1)
            return f"{o} is blank" if o else None
        if k == "call" and node[1] == "NOT" and node[2]:
            inner = node[2][0]
            if inner[0] == "call" and inner[1] == "ISBLANK" and inner[2]:
                o = self._operand(inner[2][0], env, depth + 1)
                return f"{o} is not blank" if o else None
            c = self.cond(inner, env, depth + 1)
            return f"not ({c})" if c else None
        if k == "bool":
            return None
        return None

    def _operand(self, node, env, depth):
        if node[0] == "id" and node[1] in env and env[node[1]][0] == "num" \
                and not _TARGET_VAR_RE.search(node[1]):
            return humanize_var(node[1])      # a fixed input: show its name, not its value
        v = self.const(node, env)
        if v is not None:
            return _NUM_FMT(v)
        if node[0] == "str":
            return f"“{node[1]}”"
        if node[0] == "call" and node[1] in ("ROUND", "FIXED", "COALESCE", "ABS") and node[2]:
            return self._operand(node[2][0], env, depth + 1)
        return self.describe_node(node, env, depth + 1, short=True)

    # ------------------------------------------------------------ describing
    def describe_node(self, node, env, depth=0, short=False):
        """Description including filter notes. short=True keeps variables as
        names (used for operands inside conditions)."""
        text, notes = self._parts(node, env, depth, top=not short, short=short)
        if text is None:
            return None
        if notes and re.search(r" [\u00f7\u00d7+\u2212] ", text):
            return f"{text} \u2014 all {self._suffix(notes)}"
        return self._wrap(text, notes)

    @staticmethod
    def _paren(s):
        return f"({s})" if re.search(r" [+\u2212\u00d7\u00f7] ", s) and not s.startswith("(") else s

    @staticmethod
    def _suffix(notes):
        wh = [n[6:] for n in notes if n.startswith("where ")]
        tm = [n for n in notes if not n.startswith("where ") and not n.startswith("+ ")]
        unk = [n[2:] for n in notes if n.startswith("+ ")]
        parts = []
        if wh or unk:
            parts.append("counting only rows where " + " and ".join(wh + [u for u in unk]) if wh
                         else "plus " + " and ".join(unk))
        if tm:
            parts.append("for the " + ", ".join(tm) if len(tm) == 1 and tm[0].endswith("to date")
                         else ", ".join(tm))
        return "; ".join(parts)

    def _wrap(self, text, notes):
        return f"{text} ({self._suffix(notes)})" if notes else text

    def _combine(self, l, ln, r, rn, sym):
        isnum = lambda t: bool(re.fullmatch(r"[\d,.]+", t))  # noqa: E731
        if sym != "^" and ((not rn and isnum(r)) or (not ln and isnum(l))):
            return f"{self._paren(l)} {sym} {self._paren(r)}", (ln or rn)
        common = [x for x in ln if x in rn]
        lu = [x for x in ln if x not in common]
        ru = [x for x in rn if x not in common]
        if sym == "^":
            return f"{l}^{r}", common
        text = f"{self._paren(self._wrap(l, lu))} {sym} {self._paren(self._wrap(r, ru))}"
        return text, common

    def _parts(self, node, env, depth=0, top=False, short=False):
        """-> (text | None, filter_notes). Notes are CALCULATE conditions that
        belong to `text`; callers hoist notes shared by both sides of a ratio."""
        if node is None or depth > 8:
            return None, []
        k = node[0]
        if k == "num":
            return _NUM_FMT(node[1]), []
        if k == "str":
            return f"\u201c{node[1]}\u201d", []
        if k == "col":
            return humanize_column(node[2]), []
        if k == "table":
            return humanize_table(node[1]), []
        if k == "meas":
            real = self._lookup_measure(node[1])
            return (real or node[1]), []
        if k == "id":
            if node[1] in env:
                sub = env[node[1]]
                if sub[0] in ("num", "meas", "col", "str"):
                    return self._parts(sub, env, depth + 1, top, short)
                if not short:
                    t, n = self._parts(sub, env, depth + 1, top, short)
                    if t and len(t) <= 200:
                        return t, n
                return (humanize_var(node[1]) if (short or not top) else None), []
            return humanize_table(node[1]), []
        if k == "un":
            t, n = self._parts(node[2], env, depth + 1, False, short)
            return (f"\u2212{t}" if t else None), n
        if k == "block":
            env2 = dict(env)
            for name, e in node[1]:
                env2[name] = e
            return self._parts(node[2], env2, depth + 1, top, short)
        if k == "bin" and node[1] in "+-*/^":
            l, ln = self._parts(node[2], env, depth + 1, False, short)
            r, rn = self._parts(node[3], env, depth + 1, False, short)
            if not l or not r:
                return None, []
            sym = {"+": "+", "-": "\u2212", "*": "\u00d7", "/": "\u00f7", "^": "^"}[node[1]]
            return self._combine(l, ln, r, rn, sym)
        if k == "call":
            return self._call_parts(node, env, depth, top, short)
        return None, []

    def _call_parts(self, node, env, depth, top, short):
        fn, args = node[1], node[2]
        P = lambda n, t=False: self._parts(n, env, depth + 1, t, short)  # noqa: E731
        if fn == "DIVIDE" and len(args) >= 2:
            a, an = P(args[0])
            b, bn = P(args[1])
            if a and b and a == b and not an and not bn:
                b = "total " + b           # the same figure over itself only differs when filters were widened
            return self._combine(a, an, b, bn, "\u00f7") if a and b else (None, [])
        if fn in ("COALESCE", "ROUND", "FIXED", "INT", "TRUNC", "CEILING", "FLOOR", "FORMAT",
                  "VALUE", "CONVERT") and args:
            return P(args[0], top)
        if fn in ("RELATED", "RELATEDTABLE") and args:
            return P(args[0], top)
        if fn == "DATEDIFF" and len(args) >= 3:
            a, an = P(args[0])
            b, bn = P(args[1])
            unit = args[2][1] if args[2][0] in ("id", "str") else None
            if a and b and unit:
                return f"number of {str(unit).lower()}s between {a} and {b}", an + bn
            return None, []
        if fn == "MEDIAN" and args:
            t, n = P(args[0])
            return (f"median {t}" if t else None), n
        if fn == "DISTINCTCOUNTNOBLANK" and args:
            t, n = P(args[0])
            return (f"number of distinct {t}" if t else None), n
        if fn == "ABS" and args:
            t, n = P(args[0])
            return (f"absolute value of {t}" if t else None), n
        if fn == "IF" and len(args) >= 3 and self._is_guard(args[0], env):
            for br in (args[2], args[1]):
                if self.const(br, env) is None and br[0] != "blank":
                    return P(br, top)
            return None, []
        if fn in ("SUM", "SUMX") and args:
            t, n = P(args[-1] if fn == "SUMX" else args[0])
            return ((f"total {t}" if top else t) if t else None), n
        if fn in ("AVERAGE", "AVERAGEX") and args:
            t, n = P(args[-1] if fn == "AVERAGEX" else args[0])
            return (f"average {t}" if t else None), n
        if fn in ("COUNT", "COUNTA") and args:
            t, n = P(args[0])
            return (f"count of {t}" if t else None), n
        if fn == "DISTINCTCOUNT" and args:
            t, n = P(args[0])
            return (f"number of distinct {t}" if t else None), n
        if fn == "COUNTROWS" and args:
            t = args[0]
            while t[0] == "call" and t[1] in ("FILTER", "CALCULATETABLE", "VALUES", "ALL",
                                              "ALLSELECTED", "DISTINCT") and t[2]:
                t = t[2][0]
            x, n = P(t)
            return (f"number of {x} records" if x else "number of records"), n
        if fn in ("MAX", "MAXX", "MIN", "MINX") and args:
            t, n = P(args[-1] if fn.endswith("X") else args[0])
            word = "highest" if fn.startswith("MAX") else "lowest"
            return (f"{word} {t}" if t else None), n
        if fn == "SELECTEDVALUE" and args:
            t, n = P(args[0])
            return (f"selected {t}" if t else None), n
        if fn in ("CALCULATE", "CALCULATETABLE") and args:
            t, n = P(args[0], top)
            if t is None:
                return None, []
            notes, unknown = list(n), 0
            for f in args[1:]:
                if f[0] == "call" and f[1] in ("ALL", "ALLSELECTED", "ALLEXCEPT", "REMOVEFILTERS",
                                               "USERELATIONSHIP", "CROSSFILTER", "VALUES"):
                    continue                      # widening / plumbing, not a business condition
                nt = self._filter_note(f, env, depth)
                if nt:
                    if nt not in notes:
                        notes.append(nt)
                else:
                    unknown += 1
            if unknown:
                notes.append(f"+ {unknown} further condition{'s' if unknown > 1 else ''}")
            return t, notes
        return None, []

    def _is_guard(self, c, env):
        """True for conditions made only of blank / zero checks, e.g.
        ISBLANK(x) || x = 0 -- used as divide-by-zero protection."""
        if c[0] == "call" and c[1] == "ISBLANK":
            return True
        if c[0] == "bin" and c[1] in ("=", "==") and self.const(c[3], env) == 0:
            return True
        if c[0] == "bin" and c[1] in ("||", "&&"):
            return self._is_guard(c[2], env) and self._is_guard(c[3], env)
        return False

    def _filter_note(self, f, env, depth):
        def _is_col_call(n, fn):
            return n[0] == "call" and n[1] == fn and n[2] and n[2][0][0] == "col"
        if _is_col_call(f, "ISBLANK"):
            return f"where {humanize_column(f[2][0][2])} is blank"
        if f[0] == "call" and f[1] == "NOT" and f[2] and _is_col_call(f[2][0], "ISBLANK"):
            return f"where {humanize_column(f[2][0][2][0][2])} is not blank"
        if (f[0] == "bin" and f[1] in ("=", "<>") and f[2][0] == "col"
                and f[3][0] == "call" and f[3][1] == "BLANK"):
            return f"where {humanize_column(f[2][2])} is " + ("not blank" if f[1] == "<>" else "blank")
        if f[0] == "bin" and f[1] in ("=", "==") and f[2][0] == "col":
            col = humanize_column(f[2][2])
            v = f[3]
            if v[0] == "str":
                return f"where {col} is “{v[1]}”"
            val = self.const(v, env)
            if val is not None:
                return f"where {col} = {_NUM_FMT(val)}"
        if f[0] == "bin" and f[1] == "<>" and f[2][0] == "col" and f[3][0] == "str":
            return f"where {humanize_column(f[2][2])} is not “{f[3][1]}”"
        if (f[0] == "bin" and f[1] in ("=", "==") and f[2][0] == "call" and f[2][1] in ("LEFT", "RIGHT")
                and len(f[2][2]) == 2 and f[2][2][0][0] == "col" and f[3][0] == "str"):
            word = "starts with" if f[2][1] == "LEFT" else "ends with"
            return f"where {humanize_column(f[2][2][0][2])} {word} \u201c{f[3][1]}\u201d"
        if f[0] == "call" and f[1] in ("CONTAINSSTRING", "SEARCH") and len(f[2]) >= 2:
            txt = f[2][1] if f[2][1][0] == "str" else f[2][0]
            colnode = f[2][0] if f[2][0][0] == "col" else f[2][1]
            if colnode[0] == "col" and txt[0] == "str":
                return f"where {humanize_column(colnode[2])} contains \u201c{txt[1]}\u201d"
        if f[0] == "bin" and f[1] in ("=", "==", "IN") and f[3][0] == "list" and f[2][0] == "col":
            vals = [i[1] for i in f[3][1] if i[0] == "str"]
            if vals and len(vals) <= 4:
                return f"where {humanize_column(f[2][2])} is " + " or ".join(f"“{x}”" for x in vals)
        if f[0] == "bin" and f[1] in _SYM and f[2][0] == "col":
            val = self.const(f[3], env)
            if val is not None:
                return f"where {humanize_column(f[2][2])} {_SYM[f[1]]} {_NUM_FMT(val)}"
        if f[0] == "call" and f[1] in _TIME_FN:
            return _TIME_FN[f[1]]
        if f[0] == "call" and f[1] == "DATESINPERIOD":
            return "over a rolling period"
        if f[0] == "call" and f[1] == "KEEPFILTERS" and f[2]:
            return self._filter_note(f[2][0], env, depth)
        return None

    # ------------------------------------------------------------ measures
    def _env_and_return(self, node):
        env = {}
        while node and node[0] == "block":
            for name, e in node[1]:
                env[name] = e
            node = node[2]
        return env, node

    def is_html(self, name):
        m = self.measures.get(name)
        return bool(m) and bool(re.search(r"<\s*(div|html|span|table|style|svg)\b", m["expression"], re.I))

    def format_calls(self, name):
        """Every FORMAT(arg, "fmt") in the measure that prints a variable:
        [{'var', 'fmt', 'scaled' (arg is x*100), 'bare' (arg is just x or x*100)}]."""
        node = self.ast(name)
        env, ret = self._env_and_return(node)
        out = []

        def is_hundred(n):
            return isinstance(n, tuple) and n and n[0] == "num" and n[1] == 100

        def walk(n):
            if isinstance(n, list):
                for x in n:
                    walk(x)
                return
            if not isinstance(n, tuple) or not n:
                return
            if n[0] == "call" and n[1] == "FORMAT" and n[2]:
                arg = n[2][0]
                fmt = n[2][1][1] if len(n[2]) > 1 and n[2][1][0] == "str" else None
                ids = self._collect_ids(arg)
                scaled = (arg[0] == "bin" and arg[1] == "*" and (is_hundred(arg[2]) or is_hundred(arg[3])))
                bare = arg[0] == "id" or (scaled and ids and len(ids) == 1)
                if ids:
                    out.append({"var": ids[0], "fmt": fmt, "scaled": bool(scaled), "bare": bool(bare)})
            for x in n[1:]:
                walk(x)
        for _, e in (node[1] if node and node[0] == "block" else []):
            walk(e)
        walk(ret)
        return out

    def value_vars(self, name):
        """Distinct variables a card prints as figures (targets and constants
        excluded), headline-looking ones (bare variable) first."""
        node = self.ast(name)
        env, _ = self._env_and_return(node)
        seen, bare, other = set(), [], []
        for c in self.format_calls(name):
            v = c["var"]
            if v in seen or _TARGET_VAR_RE.search(v) or (v in env and env[v][0] == "num"):
                continue
            seen.add(v)
            (bare if c["bare"] else other).append(v)
        return bare + other

    def value_var(self, name):
        """For an HTML-card measure: the variable whose value the card
        actually prints as its main figure -- the first bare (unwrapped)
        non-target variable passed to FORMAT."""
        node = self.ast(name)
        env, _ = self._env_and_return(node)
        vs = self.value_vars(name)
        return (vs[0] if vs else None), env

    def _return_var_refs(self, node, env, seen=None):
        """Variables transitively referenced by the RETURN expression."""
        _, ret = self._env_and_return(node)
        seen = set() if seen is None else seen

        def walk(n):
            if isinstance(n, list):
                for x in n:
                    walk(x)
                return
            if not isinstance(n, tuple) or not n:
                return
            if n[0] == "id" and n[1] in env and n[1] not in seen:
                seen.add(n[1])
                walk(env[n[1]])
            for x in n[1:]:
                walk(x)
        walk(ret)
        return seen

    def card_kind(self, name):
        """'status' (a colour/label badge with no printed number),
        'value' (prints a number), or 'other'."""
        if not self.is_html(name):
            return "value"
        node = self.ast(name)
        if node is None:
            return "other"
        vv, env = self.value_var(name)
        rules = self.colour_rules(name)
        if vv is None:
            return "status" if rules else "other"
        refs = self._return_var_refs(node, env)
        _, ret = self._env_and_return(node)

        def formats_value(n):
            if isinstance(n, list):
                return any(formats_value(x) for x in n)
            if not isinstance(n, tuple) or not n:
                return False
            if n[0] == "call" and n[1] == "FORMAT" and n[2] and vv in self._collect_ids(n[2][0]):
                return True
            return any(formats_value(x) for x in n[1:])
        shown = formats_value(ret) or any(formats_value(env[r]) for r in refs if r in env)
        if not shown and rules:
            return "status"
        return "value"

    @staticmethod
    def _collect_ids(n):
        out = []

        def walk(x):
            if isinstance(x, list):
                for y in x:
                    walk(y)
            elif isinstance(x, tuple) and x:
                if x[0] == "id" and x[1] not in out:
                    out.append(x[1])
                for y in x[1:]:
                    walk(y)
        walk(n)
        return out

    def describe_measure(self, name, depth=0):
        """Plain-English description of the quantity the measure computes
        (for an HTML card: the value it prints). None if not derivable."""
        key = (name, depth)
        if key in self._desc:
            return self._desc[key]
        out = None
        node = self.ast(name)
        if node is not None and depth <= 3:
            env, ret = self._env_and_return(node)
            if self.is_html(name):
                vv, env = self.value_var(name)
                if vv:
                    out = self.describe_node(("id", vv), {**env}, 0, short=False)
                    if out and out.startswith("(") and out.endswith(")") and out.count("(") == 1:
                        out = out[1:-1]
            else:
                if ret[0] == "meas":                       # bare reference -> follow it
                    real = self._lookup_measure(ret[1])
                    if real and real != name:
                        out = self.describe_measure(real, depth + 1) or real
                else:
                    out = self.describe_node(node, {}, 0, short=False)
                    if out and out.startswith("(") and out.endswith(")") and out.count("(") == 1:
                        out = out[1:-1]
        if out and len(out) > _MAX_LEN:
            out = None
        self._desc[key] = out
        return out

    def label_logic(self, name):
        """For a plain measure that returns one of several fixed words
        (IF / SWITCH(TRUE()) chains of text literals): the rule in words."""
        node = self.ast(name)
        if node is None or self.is_html(name):
            return None
        env, ret = self._env_and_return(node)
        ch = self._chain(ret, env)
        if not ch or len(ch) < 2:
            return None
        vals = []
        for _, v in ch:
            v = self._resolve_lit(v, env)
            if not v or v[0] != "str" or is_colour_literal(v[1]):
                return None
            vals.append(v[1])
        bits = []
        for (c, _), val in zip(ch, vals):
            if c is None:
                bits.append(f"otherwise \u201c{val}\u201d")
            else:
                cond = self.cond(c, env)
                if not cond:
                    return None
                bits.append(f"\u201c{val}\u201d when {cond}")
        return "; ".join(bits)

    # ------------------------------------------------------------ labels
    def card_label(self, name):
        """First human-readable text printed by an HTML-card measure's RETURN."""
        node = self.ast(name)
        if node is None or not self.is_html(name):
            return None
        _, ret = self._env_and_return(node)
        pieces = []

        def walk(n):
            if isinstance(n, list):
                for x in n:
                    walk(x)
            elif isinstance(n, tuple) and n:
                if n[0] == "str":
                    pieces.append(n[1])
                elif n[0] == "bin" and n[1] == "&":
                    walk(n[2]); walk(n[3])
                elif n[0] == "id":
                    pieces.append("\x01")
                elif n[0] == "call":
                    pieces.append("\x01")
                else:
                    pieces.append("\x01")
        walk(ret)
        html = "".join(pieces)
        html = re.sub(r"<style.*?</style>", "", html, flags=re.S | re.I)
        html = re.sub(r"<script.*?</script>", "", html, flags=re.S | re.I)
        html = re.sub(r"\{[^{}]*\}", "", html)
        for part in re.split(r"<[^>]*>", html):
            t = part.replace("\x01", " ").strip()
            t = re.sub(r"&\w+;", " ", t)
            t = re.sub(r"\s+", " ", t).strip(" :–—-")
            if (len(t) >= 2 and len(t) <= 48 and re.search(r"[A-Za-z]{2}", t)
                    and not re.fullmatch(r"[\d\s.,%$€£+\-/]+", t)):
                return t
        return None

    # ------------------------------------------------------------ colour logic
    def _chain(self, node, env, depth=0):
        """Flatten SWITCH(TRUE(), c1, v1, ..., default) / nested IF(c, v, IF(...))
        into [(cond_node|None, value_node), ...]; None if node isn't a chain."""
        if node is None or depth > 8:
            return None
        if node[0] == "id" and node[1] in env:
            return self._chain(env[node[1]], env, depth + 1)
        if node[0] == "call" and node[1] == "SWITCH" and node[2] and node[2][0] == ("bool", True):
            a = node[2][1:]
            pairs = [(a[i], a[i + 1]) for i in range(0, len(a) - 1, 2)]
            if len(a) % 2 == 1:
                pairs.append((None, a[-1]))
            return pairs
        if node[0] == "call" and node[1] == "IF" and len(node[2]) >= 2:
            c, v = node[2][0], node[2][1]
            rest = node[2][2] if len(node[2]) > 2 else None
            pairs = [(c, v)]
            if rest is not None:
                sub = self._chain(rest, env, depth + 1)
                if sub:
                    self._consumed.add(id(rest))
                pairs += sub if sub else [(None, rest)]
            return pairs
        return None

    def _all_chains(self, node, env):
        out = []

        def walk(n):
            if isinstance(n, list):
                for x in n:
                    walk(x)
                return
            if not isinstance(n, tuple) or not n:
                return
            if n[0] == "call" and n[1] in ("SWITCH", "IF") and id(n) not in self._consumed:
                ch = self._chain(n, env)
                if ch:
                    out.append(ch)
            for x in n[1:]:
                walk(x)
        walk(node)
        return out

    def colour_rules(self, name):
        """Colour logic found in the measure's DAX:
        [{'cond': 'TRIR > 2' | None, 'colour': '#D32F2F', 'label': 'Critical' | None}]
        Empty list if the measure contains no colour literals."""
        node = self.ast(name)
        if node is None:
            return []
        env, ret = self._env_and_return(node)
        chains = []
        seen_ids = set()
        for _, e in (node[1] if node[0] == "block" else []):
            for ch in self._all_chains(e, env):
                if id(ch[0]) not in seen_ids:
                    seen_ids.add(id(ch[0]))
                    chains.append(ch)
        for ch in self._all_chains(ret, env):
            chains.append(ch)

        def lit(v):
            v = self._resolve_lit(v, env)
            return v[1] if v and v[0] == "str" else None

        colour_chains, label_chains = [], []
        for ch in chains:
            vals = [lit(v) for _, v in ch]
            if vals and all(x is not None for x in vals):
                if any(is_colour_literal(x) for x in vals) and all(is_colour_literal(x) for x in vals):
                    colour_chains.append((ch, vals))
                else:
                    label_chains.append((ch, vals))
        if not colour_chains:
            return []
        rules, seen, seen_logic = [], set(), set()
        chain_no = 0
        for ch, cols in colour_chains:
            conds = [self.cond(c, env) if c is not None else None for c, _ in ch]
            labels = [None] * len(ch)
            for lch, lvals in label_chains:
                lconds = [self.cond(c, env) if c is not None else None for c, _ in lch]
                if len(lch) == len(ch) and lconds == conds:
                    labels = lvals
                    break
            if any(cn is not None and cnd is None for (cn, _), cnd in zip(ch, conds)):
                continue                        # an unreadable condition: skip the whole chain, don't guess
            logic = (tuple(conds), tuple(labels))
            if logic in seen_logic:
                continue                        # same logic, different colour shade (text vs background)
            seen_logic.add(logic)
            chain_no += 1
            for cnd, col, lab in zip(conds, cols, labels):
                key = (chain_no, cnd, col.lower())
                if key in seen:
                    continue
                seen.add(key)
                lab = _html.unescape(lab).strip() if lab else None
                if lab and not re.search(r"[A-Za-z]{2}", lab):
                    lab = None                     # symbol-only label (arrow, tick): no words to show
                rules.append({"cond": cnd, "colour": col, "label": lab, "chain": chain_no})
        return rules

    def _resolve_lit(self, node, env, depth=0):
        if node and node[0] == "id" and node[1] in env and depth < 5:
            return self._resolve_lit(env[node[1]], env, depth + 1)
        return node

    # ------------------------------------------------------------ extras
    def fixed_inputs(self, name):
        """Variables that are bare number literals AND are compared against
        thresholds inside a colour/label chain -- i.e. the status is computed
        from a constant, not from data."""
        node = self.ast(name)
        if node is None or node[0] != "block":
            return []
        env, ret = self._env_and_return(node)
        found = []
        for ch in [c for _, e in node[1] for c in self._all_chains(e, env)]:
            for c, _ in ch:
                if c and c[0] == "bin" and c[2][0] == "id":
                    v = c[2][1]
                    if v in env and env[v][0] == "num" and not _TARGET_VAR_RE.search(v):
                        if (v, env[v][1]) not in found:
                            found.append((v, env[v][1]))
        return found

    def targets(self, name):
        """Literal target/threshold values: [(humanized var name, number)]."""
        node = self.ast(name)
        if node is None or node[0] != "block":
            return []
        out = []
        for vname, e in node[1]:
            if _TARGET_VAR_RE.search(vname) and e[0] in ("num", "un"):
                v = self.const(e, {})
                if v is not None:
                    out.append((humanize_var(vname), v))
        return out
