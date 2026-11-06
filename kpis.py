"""
kpis.py -- turns a page's visuals into the items the manuals describe.

Every field of an item is either read from the report/model or left empty.
Nothing is assumed about what a colour, a name or a page "means".
"""
import html as _html
import re

from dax_explain import humanize_column, humanize_var
from glossary import normalize

_CHROME_NAME_RE = re.compile(r"\b(header|title|subtitle|banner|footer|legend|spacer)\b", re.I)
_PLUMBING_WORDS = {"html", "card", "pill", "hdr"}
_SMALL = {"of", "to", "in", "on", "at", "by", "or", "and", "the", "per", "vs", "for", "a", "an", "as"}


def is_chrome_measure(name: str) -> bool:
    return name.startswith("_") or bool(_CHROME_NAME_RE.search(name))


def smart_case(text: str) -> str:
    """'NEAR MISSES' -> 'Near Misses'; leaves 'TRIR', 'EOL', 'DL' and
    mixed-case words as authored."""
    out = []
    words = text.split()
    all_upper_phrase = len(words) >= 2 and all(w.isupper() and w.isalpha() for w in words)
    for i, w in enumerate(words):
        if w.isupper() and w.isalpha() and (len(w) > 4 or (all_upper_phrase and len(w) > 3)):
            w = w.capitalize()
        elif all_upper_phrase and w.lower() in _SMALL and i > 0:
            w = w.lower()
        out.append(w)
    return " ".join(out)


def clean_measure_name(name: str) -> str:
    """'TRIR_HTML_Pill' -> 'TRIR'; 'Net Rev per DL Hr Card HTML' -> 'Net Rev per DL Hr';
    'Safety Status HTML' -> 'Safety Status'."""
    n = re.sub(r"\([^)]*\)", " ", name).replace("_", " ")
    words = [w for w in n.split() if w.lower() not in _PLUMBING_WORDS and not re.fullmatch(r"v\d+", w.lower())]
    return smart_case(" ".join(words)).strip() or name


def clean_label(label: str) -> str:
    t = _html.unescape(label or "")
    t = re.sub(r"^[^\w(]+|[^\w)%]+$", "", t).strip()
    return smart_case(t)


def format_kind(fmt):
    """Reads a format string: 'percent' | 'currency' | 'number' | None."""
    if not fmt:
        return None
    if "%" in fmt:
        return "percent"
    if re.search(r"[$€£¥]", fmt):
        return "currency"
    if re.search(r"[0#]", fmt):
        return "number"
    return None


def html_table_headers(explainer, name):
    """Column headings printed by an HTML-table measure (<th> text)."""
    node = explainer.ast(name)
    if node is None:
        return []
    pieces = []

    def walk(n):
        if isinstance(n, list):
            for x in n:
                walk(x)
        elif isinstance(n, tuple) and n:
            if n[0] == "str":
                pieces.append(n[1])
            else:
                pieces.append("\x01") if n[0] in ("id", "call", "meas", "col") else None
                for x in n[1:]:
                    walk(x)
    walk(node)
    text = "".join(pieces)
    heads = []
    for m in re.finditer(r"<th[^>]*>(.*?)</th>", text, re.S | re.I):
        t = _html.unescape(re.sub(r"<[^>]*>|\x01", " ", m.group(1)))
        t = re.sub(r"\s+", " ", t).strip()
        if 1 <= len(t) <= 40 and re.search(r"[A-Za-z]", t) and t not in heads:
            heads.append(t)
    return heads


def _value_format(explainer, name):
    """Format string a card prints its main value with. A value printed as
    FORMAT(x * 100, ...) is a percentage shown without its % sign, so it is
    reported as a percentage format."""
    vv, _ = explainer.value_var(name)
    if not vv:
        return None
    for c in explainer.format_calls(name):
        if c["var"] == vv:
            if c["scaled"]:
                return "0.0%"
            return c["fmt"]
    return None


def _percent_cond(cond, is_percent):
    """'OT % > 0.05' -> 'OT % > 5%' -- only when the compared value is known to be a percentage."""
    if not cond or not is_percent:
        return cond
    m = re.fullmatch(r"(.+?) ([<>≤≥=]) (-?\d*\.?\d+)", cond)
    if m and abs(float(m.group(3))) <= 10:
        return f"{m.group(1)} {m.group(2)} {float(m.group(3)) * 100:g}%"
    return cond


def _subject_is_percent(subject, display, kind, card_fmt, measures, var_pct=None):
    """Is the number the condition compares known to be a percentage?
    Looks at the model's own format string for the named measure; for a
    card's own value, at the format the card prints it with."""
    if var_pct and subject in var_pct:
        return var_pct[subject]
    for k, m in measures.items():
        if k.lower() == subject.lower():
            return "%" in (m.get("formatString") or "")
    if kind != "status" and subject == display:
        return bool(card_fmt) and "%" in card_fmt
    return False


def _drop_tint_chains(rules):
    """Drop chains whose colours are all white/very light (background tints
    that only accompany another chain) -- they add words but no information."""
    from dax_explain import hex_to_name
    by = {}
    for r in rules:
        by.setdefault(r.get("chain", 0), []).append(r)
    keep = {c for c, rs in by.items()
            if any(not hex_to_name(r["colour"]).startswith(("white", "light")) for r in rs)}
    return [r for r in rules if r.get("chain", 0) in keep]


def _chain_bits(rules):
    from dax_explain import hex_to_name
    bits = []
    for r in rules:
        nm = hex_to_name(r["colour"])
        lab = f" ({r['label']})" if r.get("label") else ""
        bits.append(f"{nm}{lab} when {r['cond']}" if r["cond"] else f"{nm}{lab} otherwise")
    return bits


def colour_sentences(rules):
    """One sentence per colour-logic chain. Chains with the same colours,
    labels and thresholds but different subjects are merged into one
    sentence ('for each of A, B, C: ...')."""
    chains = {}
    for r in rules:
        chains.setdefault(r.get("chain", 0), []).append(r)
    merged, order = {}, []
    for rs in chains.values():
        subjects = []
        sig_parts = []
        for r in rs:
            m = re.fullmatch(r"(.+?) ([<>\u2264\u2265=]) (.+)", r["cond"] or "")
            if m:
                subjects.append(m.group(1))
                sig_parts.append((r["colour"].lower(), r.get("label"), m.group(2), m.group(3)))
            else:
                sig_parts.append((r["colour"].lower(), r.get("label"), r["cond"], None))
        sig = tuple(sig_parts)
        if sig not in merged:
            merged[sig] = {"rules": rs, "subjects": []}
            order.append(sig)
        if subjects:
            merged[sig]["subjects"].append(subjects[0])
    out = []
    for sig in order:
        g = merged[sig]
        bits = _chain_bits(g["rules"])
        prefix = "Colour coding: " if not out else "Also: "
        if len(g["subjects"]) >= 2:
            first_subj = g["subjects"][0]
            bits = [b.replace(first_subj, "the value", 1) if first_subj in b else b for b in bits]
            out.append(f"{prefix}for each of {', '.join(g['subjects'])} \u2014 " + "; ".join(bits) + ".")
        else:
            out.append(prefix + "; ".join(bits) + ".")
    return out


def colour_sentence(rules):
    s = colour_sentences(rules)
    return " ".join(s)


# ---------------------------------------------------------------- items

def _stem(w):
    w = w.lower()
    return w[:-1] if len(w) > 3 and w.endswith("s") else w


def _shares_word(text, others):
    tok = lambda t: {_stem(w) for w in re.findall(r"[A-Za-z0-9]{2,}", t)} - {"of", "to", "in", "by", "or", "and", "the", "per", "for"}  # noqa: E731
    ws = tok(text)
    for o in others:
        if ws & tok(o):
            return True
    return False


def _follow_reference(ex, desc):
    out = _follow_reference_(ex, desc)
    m100 = re.fullmatch(r"(.+?) \u00d7 100", desc or "")
    if out is None and m100:
        return m100.group(1)              # nothing deeper to say: keep the measure's name
    return out


def _follow_reference_(ex, desc):
    """A description that is only the name of another measure ('EOL Rework %')
    says nothing; replace it with that measure's own description."""
    m100 = re.fullmatch(r"(.+?) \u00d7 100", desc or "")
    if m100 and hasattr(ex, "_lookup_measure") and ex._lookup_measure(m100.group(1)):
        desc = m100.group(1)                          # 'x 100' only turns a ratio into a percentage for display
    for _ in range(3):
        if not desc:
            return desc
        real = ex._lookup_measure(desc) if hasattr(ex, "_lookup_measure") else None
        if not real:
            return desc
        nxt = ex.describe_measure(real)
        if not nxt or nxt == desc:
            return None                           # a bare stored figure: nothing more to say
        desc = nxt
    return desc


def build_page_items(page, analysis, glossary):
    """Ordered list of what a reader sees on the page (headline visuals only)."""
    ex = analysis["explainer"]
    ev = analysis["evidence"].get(page["id"], {}).get("visuals", {})
    measures = analysis["measuresByName"]
    items, seen = [], set()
    for v in page["visuals"]:
        cat = v["category"]
        if cat not in ("HTML Content (custom visual)", "KPI Card", "Table", "Chart"):
            continue
        mrefs = [r["property"] for r in v["refs"] if r["kind"] == "measure"]
        vev = ev.get(v["id"], {})
        if cat in ("HTML Content (custom visual)", "KPI Card"):
            for m in mrefs:
                if m in seen or is_chrome_measure(m) or m not in measures:
                    continue
                seen.add(m)
                items.append(_card_item(m, page, ex, measures, glossary, v))
        else:
            fields = vev.get("fields", [])
            cols = [f["display"] or f["name"] for f in fields if f["display"] or f["name"]]
            dims = [humanize_column(f["name"]) if (f["name"] or "").isupper() else (f["display"] or f["name"])
                    for f in fields if not f["isMeasure"] and f["name"]]
            if not cols:
                continue
            kind = "table" if cat == "Table" else "chart"
            key = (kind, tuple(cols))
            if key in seen:
                continue
            seen.add(key)
            items.append({
                "kind": kind, "visualType": v["visualType"], "measure": None, "visual_id": v["id"],
                "display": (v["title"] or (f"{'Table' if kind == 'table' else 'Chart'} — {dims[0]}" if dims
                                           else ("Table" if kind == "table" else "Chart"))),
                "columns": [humanize_column(c) if c.isupper() else c for c in cols],
                "definition": None, "calc": None, "rules": [], "unit": None, "basis": None,
            })
    return items


_TIME_COLS = {"date", "year", "month", "quarter", "day", "week", "fiscal year", "fiscal quarter", "year month",
              "month number", "month name", "day name", "time"}


def measure_inputs(measures, m):
    """Business columns a measure reads (calendar columns left out): the last-resort basis for a draft."""
    cols = (measures.get(m) or {}).get("_columnsReferenced") or []
    out = []
    for c in cols:
        name = humanize_column(c[2]) if len(c) > 2 and c[2] else ""
        if name and name.lower() not in _TIME_COLS and name not in out:
            out.append(name)
    return out


def _card_item(m, page, ex, measures, glossary, visual):
    kind = ex.card_kind(m)
    label = ex.card_label(m)
    if not ex.is_html(m):
        display = m                                   # a plain measure: use its name exactly as authored
    else:
        display = clean_label(label) if label else clean_measure_name(m)
    heads = html_table_headers(ex, m) if ex.is_html(m) else []
    if kind == "other":
        kind = "value"
    item = {"kind": "html_table" if len(heads) >= 2 else kind, "visualType": visual["visualType"],
            "visual_id": visual["id"],
            "measure": m, "display": display, "columns": heads, "definition": None, "calc": None,
            "rules": [], "unit": None, "basis": None}
    if item["kind"] == "html_table":
        item["display"] = clean_measure_name(m) if not label else display
        return item

    desc = ex.describe_measure(m)
    fmt = _value_format(ex, m) if ex.is_html(m) else measures[m].get("formatString")
    item["unit"] = format_kind(fmt)
    if kind == "status":
        # a badge: its value is the measure it is based on (if that is all desc says)
        is_name = bool(desc) and hasattr(ex, "_lookup_measure") and bool(ex._lookup_measure(desc))
        item["basis"] = desc if desc and (is_name or re.fullmatch(r"[^()÷×+−]+", desc)) else None
    else:
        vvars = ex.value_vars(m) if ex.is_html(m) else []
        item["calc"] = _follow_reference(ex, desc)
        if not item["calc"] and not ex.is_html(m):
            item["label_logic"] = ex.label_logic(m)
        if len(vvars) >= 4:                      # a summary tile printing several figures
            item["also_shows"] = [humanize_var(v) for v in vvars[1:]]
            # words that appear only in the denominator ("X ÷ Net Total Revenue") do not say what the tile is
            calc_ = item["calc"] or ""
            first_term = re.split(r" [\u00f7\u00d7+\u2212] ", calc_)[0] + " " + (calc_.split(" \u2014 all ", 1)[1] if " \u2014 all " in calc_ else "")
            if item["calc"] and not _shares_word(first_term, [display, m]):
                item["calc"] = None              # the first figure may not be what the tile's name says

    rules = ex.colour_rules(m)
    vv, _ = ex.value_var(m)
    var_pct = {}
    for c in (ex.format_calls(m) if ex.is_html(m) else []):
        var_pct[humanize_var(c["var"])] = bool(c["scaled"] or "%" in (c["fmt"] or ""))
    out = []
    for r in rules:
        cond = r["cond"]
        if cond and vv:                       # a condition's subject that is the card's own value -> card name
            cond = re.sub(r"^" + re.escape(humanize_var(vv)) + r" (?=[<>\u2264\u2265=]|is )", display + " ", cond)
        pct = False
        mm = re.fullmatch(r"(.+?) [<>\u2264\u2265=] -?\d*\.?\d+", cond or "")
        if mm:
            pct = _subject_is_percent(mm.group(1), display, kind, fmt, measures, var_pct)
        out.append({**r, "cond": _percent_cond(cond, pct)})
    out = _drop_tint_chains(out)
    item["rules"] = out
    item["colour_sentences"] = colour_sentences(out)
    item["fixed"] = ex.fixed_inputs(m)

    names = [label and clean_label(label), clean_measure_name(m), item["basis"], m]
    names = [n for n in names if n]
    ctx = [page["displayName"].strip()] + ([item["calc"]] if item.get("calc") else [])
    # A status badge is a traffic light, not a standard KPI: only the measure it is *based on* is looked up
    # (e.g. "Turnover Status" -> "Turnover % (12M)"). Naming it after a general term would be a guess:
    # the badge may test something else entirely. Everything else may be searched under its own name.
    if kind == "status":
        web_names = [item["basis"]] if item["basis"] else []
    else:
        web_names = None
    ai_context = {"calc": item.get("calc") or "", "basis": item["basis"] or "", "page": page["displayName"].strip(),
                  "rules": item["colour_sentences"][:3], "kind": kind,
                  "dax": measures[m].get("expression") or ""}
    # a summary tile named after a report page ("People", "Quality") summarises that whole area, not one standard term
    if web_names is None and normalize(display) in _PAGE_KEYS:
        web_names = []
    item["definition"] = glossary.lookup(*names, context=ctx, web=bool(web_names is None or web_names),
                                         web_names=web_names, ai_context=ai_context,
                                         draft=None if kind == "status" else {"calc": item.get("calc"), "unit": item.get("unit"),
                                                                                  "inputs": measure_inputs(measures, m)})
    return item


def build_extra_items(analysis, glossary, pages, page_items):
    """Measures that are displayed on the main pages but are not a headline tile: table columns, chart values,
    anything else. They get a glossary row of their own so that nothing the report shows is left out."""
    ex = analysis["explainer"]
    measures = analysis["measuresByName"]
    covered = set(glossary.used)
    extras, seen = [], set()
    for p in pages:
        pname = p["displayName"].strip()
        for v in p["visuals"]:
            for r in v["refs"]:
                m = r["property"]
                if r["kind"] != "measure" or m in seen or m not in measures or is_chrome_measure(m) or ex.is_html(m):
                    continue
                key = normalize(m)
                if not key or key in covered:
                    continue
                seen.add(m)
                calc = _follow_reference(ex, ex.describe_measure(m))
                ctx = [pname] + ([calc] if calc else [])
                d = glossary.lookup(m, context=ctx, web=True,
                                    ai_context={"calc": calc or "", "basis": "", "page": pname, "rules": [], "kind": "value",
                                                "dax": measures[m].get("expression") or ""},
                                    draft={"calc": calc, "unit": format_kind(measures[m].get("formatString")),
                                           "inputs": measure_inputs(measures, m)})
                extras.append({"kind": "value", "measure": m, "display": m, "calc": calc, "definition": d,
                               "page": pname, "rules": [], "basis": None, "also_shows": None})
    return extras


_PAGE_KEYS = set()          # normalised names of the report's pages (set by build_all_items)


def build_all_items(analysis, glossary, pages=None):
    """{page_id: [items]} for the main pages. Built once and shared by every
    document so web lookups (and their cost) happen once per run."""
    pages = pages if pages is not None else [p for p in analysis["pages"] if p.get("mainNav")]
    _PAGE_KEYS.clear()
    _PAGE_KEYS.update(normalize(p["displayName"]) for p in analysis["pages"])
    return {p["id"]: build_page_items(p, analysis, glossary) for p in pages}
