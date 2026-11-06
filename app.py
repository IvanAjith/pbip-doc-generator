"""
app.py -- PBIP Documentation Generator (analysis engine)
=========================================================
Parses an unzipped Power BI project (a "<Name>.Report" folder and a
"<Name>.SemanticModel" folder, PBIP/TMDL format) and generates two outputs:

  1. <Name>_User_Manual.docx       -- a Word user manual
  2. <Name>_KPI_Documentation.html -- an interactive HTML reference

Nothing about a specific project's page names, domains, table names, or
business logic is hardcoded. Everything is discovered from the files
themselves. Called by run.py; not normally run directly.

Design notes (read this before editing):
  - TIER 1 ONLY. Every "description" / "formula summary" field is produced
    by mechanical pattern-matching over the DAX text, never invented. Where
    something cannot be determined mechanically (business purpose, SQL
    translation, RAG thresholds tied to real targets), the output says so
    plainly instead of guessing.
  - "No hardcoding" means: no project-specific names, domains, page lists,
    or KPI selections anywhere in this file. If you're tempted to special-
    case a particular project or measure name, stop -- that belongs in the
    source PBIP, not here.
"""

import re
import io
import json
import zipfile
import datetime
from pathlib import Path
from collections import defaultdict, Counter

# ============================================================================
# SECTION 1 -- TMDL PARSING (semantic model: tables, columns, measures)
# ============================================================================

MEASURE_RE = re.compile(
    r"^\tmeasure\s+('([^']+)'|(\S+))\s*=(.*?)(?=\n\t(?:measure|column|partition|annotation|hierarchy)\s|\Z)",
    re.S | re.M,
)
COLUMN_RE = re.compile(
    r"^\tcolumn\s+('([^']+)'|(\S+))(?:\s*=\s*)?(.*?)(?=\n\t(?:measure|column|partition|annotation|hierarchy)\s|\Z)",
    re.S | re.M,
)
PROP_RE = re.compile(r"^\t\t(\w+):[ \t]*(.*)$", re.M)


def _decl_name(m):
    return m.group(2) or m.group(3)


def _split_expr_and_props(raw):
    """raw = text after '=' up to the next top-level declaration. A DAX
    expression body is indented 3+ tabs; a property (formatString: etc.) is
    indented exactly 2 tabs -- that's the reliable split signal, independent
    of which properties are present or their order."""
    cut = None
    for pm in PROP_RE.finditer(raw):
        cut = pm.start()
        break
    expr = raw[:cut] if cut is not None else raw
    props_text = raw[cut:] if cut is not None else ""
    props = {k: v.strip() for k, v in PROP_RE.findall(props_text)}
    return expr.strip("` \n\t"), props


def _table_name(text):
    mm = re.match(r"table\s+('([^']+)'|(\S+))", text)
    if not mm:
        return None
    return mm.group(2) or mm.group(3)


def parse_table_file(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    name = _table_name(text)
    is_hidden = bool(re.search(r"^\tisHidden\b", text, re.M))

    columns = []
    for m in COLUMN_RE.finditer(text):
        cname = _decl_name(m)
        raw = m.group(4) or ""
        _, props = _split_expr_and_props(raw)
        columns.append({
            "name": cname,
            "dataType": props.get("dataType"),
            "formatString": props.get("formatString"),
            "summarizeBy": props.get("summarizeBy"),
            "sourceColumn": props.get("sourceColumn"),
            "isHidden": bool(re.search(r"^\t\tisHidden\b", raw, re.M)),
            "dataCategory": props.get("dataCategory"),
            "description": props.get("description"),
        })

    measures = []
    for m in MEASURE_RE.finditer(text):
        mname = _decl_name(m)
        raw = m.group(4)
        expr, props = _split_expr_and_props(raw)
        measures.append({
            "name": mname,
            "table": name,
            "expression": expr,
            "formatString": props.get("formatString"),
            "displayFolder": props.get("displayFolder") or "(ungrouped)",
            "description": props.get("description"),
        })

    source_info = {"connector": None, "database": None, "schema": None, "object": None, "objectKind": None}
    part = re.search(r"partition .+?=\s*m\s*\n(.*?)(?=\n\tannotation|\n\tpartition|\Z)", text, re.S)
    if part:
        ptext = part.group(1)
        conn = re.search(r"(\w+(?:\.\w+)+)\s*\(", ptext)
        if conn:
            source_info["connector"] = conn.group(1)
            call = re.search(re.escape(conn.group(1)) + r"\s*\((.*?)\)\s*,", ptext, re.S)
            args = re.findall(r'"([^"]*)"', call.group(1)) if call else []
            source_info["args"] = args
            fc = re.search(r'File\.Contents\(\s*"([^"]+)"', ptext)
            if fc:
                source_info["file"] = re.split(r"[\\/]", fc.group(1))[-1]
            if len(args) >= 2 and conn.group(1).split(".")[0] in ("Sql", "PostgreSQL", "MySQL", "Oracle", "Teradata"):
                source_info["database"] = args[1]
        for nm, kind in re.findall(r'\{\[Name="([^"]+)",\s*Kind="([^"]+)"\]\}', ptext):
            k = kind.lower()
            if k == "database":
                source_info["database"] = nm
            elif k == "schema":
                source_info["schema"] = nm
            elif k in ("view", "table"):
                source_info["object"] = nm
                source_info["objectKind"] = kind

    is_date_table = (
        bool(re.match(r"^(LocalDateTable_|DateTableTemplate_)", name or ""))
        or any(c.get("dataCategory") == "PaddedDateTableDates" for c in columns)
    )

    return {
        "name": name, "isHidden": is_hidden, "isDateTable": is_date_table,
        "columns": columns, "measures": measures, "source": source_info,
    }


def parse_semantic_model(sm_dir: Path):
    tables_dir = sm_dir / "definition" / "tables"
    all_tables = [parse_table_file(f) for f in sorted(tables_dir.glob("*.tmdl"))]
    relationships = parse_relationships(sm_dir / "definition" / "relationships.tmdl")
    roles = parse_roles(sm_dir / "definition" / "roles")
    return all_tables, relationships, roles


# ============================================================================
# SECTION 2 -- TMDL PARSING (relationships, roles)
# ============================================================================

REL_BLOCK_RE = re.compile(r"^relationship\s+(\S+)\n(.*?)(?=\nrelationship\s|\Z)", re.S | re.M)


def _col_ref(s):
    s = s.strip()
    m = re.match(r"^'([^']+)'\.(.+)$", s) or re.match(r"^([^.']+)\.(.+)$", s)
    if not m:
        return s, ""
    table, col = m.group(1), m.group(2).strip().strip("'")
    return table, col


def parse_relationships(path: Path):
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    out = []
    for m in REL_BLOCK_RE.finditer(text):
        rid, body = m.group(1), m.group(2)
        props = {}
        for line in body.split("\n"):
            line = line.strip()
            if not line or ":" not in line:
                continue
            k, v = line.split(":", 1)
            props[k.strip()] = v.strip()
        from_t, from_c = _col_ref(props.get("fromColumn", ""))
        to_t, to_c = _col_ref(props.get("toColumn", ""))
        out.append({
            "id": rid, "fromTable": from_t, "fromColumn": from_c,
            "toTable": to_t, "toColumn": to_c,
            "isActive": props.get("isActive", "true") != "false",
            "crossFilteringBehavior": props.get("crossFilteringBehavior", "single"),
            "fromCardinality": props.get("fromCardinality", "many"),
            "toCardinality": props.get("toCardinality", "one"),
        })
    return out


ROLE_BLOCK_RE = re.compile(r"^role\s+(\S+)\n(.*?)(?=\nrole\s|\Z)", re.S | re.M)
TABLE_PERM_RE = re.compile(
    r"^\ttablePermission\s+('([^']+)'|(\S+))\s*=(.*?)(?=\n\ttablePermission\s|\n\tannotation\s|\Z)",
    re.S | re.M,
)


def parse_roles(roles_dir: Path):
    out = []
    if not roles_dir.exists():
        return out
    for f in sorted(roles_dir.glob("*.tmdl")):
        text = f.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
        m = ROLE_BLOCK_RE.search(text)
        if not m:
            continue
        name, body = m.group(1), m.group(2)
        perms = []
        for pm in TABLE_PERM_RE.finditer(body):
            tname = pm.group(2) or pm.group(3)
            expr = pm.group(4).strip("` \n\t")
            perms.append({"table": tname, "filter": expr})
        out.append({"name": name, "tablePermissions": perms})
    return out


# ============================================================================
# SECTION 3 -- REPORT PARSING (pages, visuals)
# ============================================================================

CHROME_TYPES = {
    "actionButton", "shape", "textbox", "image", "basicShape",
    "bookmarkNavigator", "pageNavigator",
}


def classify_visual(visual_type: str) -> str:
    if visual_type in CHROME_TYPES:
        return "Navigation/Decorative"
    if visual_type == "slicer":
        return "Slicer"
    if visual_type.startswith("htmlContent"):
        return "HTML Content (custom visual)"
    if visual_type in ("card", "multiRowCard", "kpi", "gauge"):
        return "KPI Card"
    if visual_type in ("tableEx", "table", "pivotTable", "matrix"):
        return "Table"
    chart_hint = ("chart", "Chart", "line", "bar", "column", "pie", "donut",
                  "area", "scatter", "treemap", "funnel", "map", "ribbon", "waterfall")
    if any(h in visual_type for h in chart_hint):
        return "Chart"
    if visual_type in ("group", "unknown"):
        return "Layout group"
    return f"Other ({visual_type})"


CONTENT_CATEGORIES = {"HTML Content (custom visual)", "KPI Card", "Table", "Chart"}


def _extract_refs(visual_obj):
    refs = []
    qs = visual_obj.get("query", {}).get("queryState", {})
    for bucket_name, bucket in qs.items():
        for proj in bucket.get("projections", []):
            field = proj.get("field", {})
            if "Measure" in field:
                entity = field["Measure"].get("Expression", {}).get("SourceRef", {}).get("Entity", "?")
                refs.append({"kind": "measure", "entity": entity,
                             "property": field["Measure"].get("Property"), "bucket": bucket_name})
            elif "Column" in field:
                entity = field["Column"].get("Expression", {}).get("SourceRef", {}).get("Entity", "?")
                refs.append({"kind": "column", "entity": entity,
                             "property": field["Column"].get("Property"), "bucket": bucket_name})
            elif "Aggregation" in field:
                inner = field["Aggregation"].get("Expression", {}).get("Column", {})
                entity = inner.get("Expression", {}).get("SourceRef", {}).get("Entity", "?")
                refs.append({"kind": "column", "entity": entity,
                             "property": inner.get("Property"), "bucket": bucket_name,
                             "aggregated": True})
    return refs


def _extract_title(visual_obj):
    try:
        for bucket in ("visualContainerObjects", "objects"):
            for t in (visual_obj.get(bucket) or {}).get("title", []):
                lit = t.get("properties", {}).get("text", {}).get("expr", {}).get("Literal", {}).get("Value")
                if lit:
                    t = lit.strip("'").replace("''", "'").strip()
                    if re.search(r"[A-Za-z0-9]{2}", t):
                        return t
    except Exception:
        pass
    return None


def parse_page(page_dir: Path):
    page_json = json.loads((page_dir / "page.json").read_text(encoding="utf-8"))
    visuals = []
    vdir = page_dir / "visuals"
    if vdir.exists():
        for vfolder in sorted(vdir.iterdir()):
            vfile = vfolder / "visual.json"
            if not vfile.exists():
                continue
            try:
                vjson = json.loads(vfile.read_text(encoding="utf-8"))
            except Exception:
                continue
            vobj = vjson.get("visual", {})
            vtype = vobj.get("visualType") or ("group" if "visualGroup" in vjson else "unknown")
            pos = vjson.get("position", {})
            visuals.append({
                "id": vjson.get("name"),
                "visualType": vtype,
                "category": classify_visual(vtype),
                "title": _extract_title(vobj),
                "refs": _extract_refs(vobj),
                "x": pos.get("x", 0), "y": pos.get("y", 0), "z": pos.get("z", 0),
            })
    visuals.sort(key=lambda v: (round(v["y"] / 20), v["x"]))
    return {
        "id": page_dir.name,
        "displayName": page_json.get("displayName", page_dir.name),
        "visibility": page_json.get("visibility", "visible"),
        "width": page_json.get("width"), "height": page_json.get("height"),
        "visuals": visuals,
    }


NONPROD_PATTERNS = re.compile(
    r"\b(test|duplicate|drill[\s-]?down|tooltip|copy of|backup|wip|old|sample|temp|scratch|detail(?:s)?)\b",
    re.I,
)


def flag_nonprod(display_name: str):
    m = NONPROD_PATTERNS.search(display_name)
    return m.group(1).lower() if m else None


def parse_report(report_dir: Path):
    pages_meta = json.loads((report_dir / "definition" / "pages" / "pages.json").read_text(encoding="utf-8"))
    order = pages_meta.get("pageOrder", [])
    pages_dir = report_dir / "definition" / "pages"
    pages = []
    for pid in order:
        pdir = pages_dir / pid
        if not pdir.exists():
            continue
        p = parse_page(pdir)
        p["nonprodFlag"] = None          # set by evidence.classify_pages once the nav graph is known
        pages.append(p)
    return pages, pages_meta.get("activePageName")


# ============================================================================
# SECTION 4 -- ANALYSIS / CROSS-REFERENCING (still zero hardcoded business facts)
# ============================================================================

def is_date_table(t):
    return t["isDateTable"]


DIM_PREFIXES = ("dim_", "vw_dim_")
FACT_PREFIXES = ("fact_", "vw_fact_")


def classify_dim_fact(table_name: str, relationships=None) -> str:
    """Name-prefix match first (certain when present); otherwise fall back
    to relationship shape, which is how a human analyst actually tells the
    two apart when naming doesn't say so: a table that supplies the 'many'
    side of a relationship (has outgoing foreign keys into other tables) is
    behaving as a fact table regardless of what it's called; a table that
    is only ever the 'one' side (other tables point into it, it points
    into nothing) is behaving as a dimension."""
    n = (table_name or "").lower()
    if any(n.startswith(p) for p in DIM_PREFIXES):
        return "Dimension"
    if any(n.startswith(p) for p in FACT_PREFIXES):
        return "Fact"
    if relationships:
        is_many_source = any(
            r["fromTable"] == table_name and r["fromCardinality"] == "many" for r in relationships
        )
        if is_many_source:
            return "Fact"
        is_referenced = any(r["toTable"] == table_name for r in relationships)
        if is_referenced:
            return "Dimension"
    return "Unclassified"


# ---- formula summarizer (Tier 1 heuristic, never invents business meaning) ----

_FUNC_CALL_RE = re.compile(r"^([A-Z][A-Z0-9_.]*)\s*\((.*)\)\s*$", re.S)


def _split_top_level_args(s):
    """Split a function-call argument string on top-level commas (respecting
    nested parens/brackets/quotes)."""
    args, depth, cur, in_str = [], 0, "", False
    i = 0
    while i < len(s):
        c = s[i]
        if c == '"' and (i == 0 or s[i - 1] != "\\"):
            in_str = not in_str
        if not in_str:
            if c in "([{":
                depth += 1
            elif c in ")]}":
                depth -= 1
            elif c == "," and depth == 0:
                args.append(cur.strip())
                cur = ""
                i += 1
                continue
        cur += c
        i += 1
    if cur.strip():
        args.append(cur.strip())
    return args


_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
_LINE_COMMENT_RE = re.compile(r"--[^\n]*")


def _strip_dax_comments(text: str) -> str:
    """Best-effort comment stripper: block comments first (so a commented-out
    '--' inside one doesn't confuse anything), then line comments. Doesn't
    special-case '--' appearing inside a string literal -- rare in practice,
    and this is a Tier-1 heuristic, not a full DAX tokenizer. Without this,
    hand-authored measures with large commented-out legacy blocks (common in
    real-world models) corrupt the RETURN-statement search below, since a
    greedy search has no way to know a later 'RETURN' is inside a comment."""
    return _LINE_COMMENT_RE.sub("", _BLOCK_COMMENT_RE.sub("", text))


def _core_expression(expr: str) -> str:
    """If the measure is a VAR.../RETURN block, pull out just the RETURN
    expression -- that's what actually determines the output value."""
    clean = _strip_dax_comments(expr)
    m = re.search(r"\bRETURN\b(.*)$", clean, re.S | re.I)
    if m:
        return m.group(1).strip()
    return clean.strip()


_VAR_DEF_RE = re.compile(r"\bVAR\s+(\w+)\s*=(.*?)(?=\n\s*VAR\s+\w+\s*=|\n\s*RETURN\b|\Z)", re.S)


def _find_var_definition(clean_expr: str, var_name: str):
    """clean_expr must already have comments stripped (see
    _strip_dax_comments) -- otherwise a commented-out duplicate VAR block can
    shadow the real one depending on ordering."""
    for vm in _VAR_DEF_RE.finditer(clean_expr):
        if vm.group(1) == var_name:
            return vm.group(2).strip()
    return None


def summarize_formula(expr: str, _depth: int = 0, _clean=None) -> str:
    """A short, mechanical, best-effort English paraphrase of a DAX
    expression's outermost operation. Never invents business meaning that
    isn't in the formula itself."""
    clean_full = _clean if _clean is not None else _strip_dax_comments(expr)
    core = _core_expression(expr) if _depth == 0 else expr.strip()
    core = core.strip().rstrip(")").lstrip("(") if core.startswith("(") and core.endswith(")") else core

    # RETURN <bare identifier> -- trace back to that VAR's own definition
    # rather than giving up, since this is the most common measure shape.
    if _depth < 4 and re.match(r"^\w+$", core):
        var_def = _find_var_definition(clean_full, core)
        if var_def is not None:
            return summarize_formula(var_def, _depth + 1, clean_full)

    m = _FUNC_CALL_RE.match(core)
    if not m:
        if re.match(r"^\[[^\]]+\]$", core):
            return f"Reuses the {core} measure directly."
        return "Composite expression -- see full formula."

    fn, argstr = m.group(1).upper(), m.group(2)
    args = _split_top_level_args(argstr)

    def short(a, n=60):
        a = re.sub(r"\s+", " ", a).strip()
        return a if len(a) <= n else a[: n - 1] + "\u2026"

    if fn == "DIVIDE" and len(args) >= 2:
        return f"{short(args[0])} \u00f7 {short(args[1])}" + (f" (default {short(args[2])} if blank)" if len(args) > 2 else "")
    if fn in ("SUM", "AVERAGE", "MIN", "MAX") and args:
        verb = {"SUM": "Sum", "AVERAGE": "Average", "MIN": "Minimum", "MAX": "Maximum"}[fn]
        return f"{verb} of {short(args[0])}"
    if fn == "COUNTROWS" and args:
        return f"Count of rows in {short(args[0])}"
    if fn in ("COUNT", "COUNTA") and args:
        return f"Count of {short(args[0])}"
    if fn == "DISTINCTCOUNT" and args:
        return f"Distinct count of {short(args[0])}"
    if fn == "CALCULATE" and args:
        base = f"the {short(args[0])} measure" if args[0].strip().startswith("[") else summarize_formula(args[0], _depth + 1, clean_full)
        filters = args[1:]
        if filters:
            return f"{base}, filtered by: {'; '.join(short(f, 40) for f in filters[:3])}" + (" \u2026" if len(filters) > 3 else "")
        return base
    if fn == "SWITCH":
        return "Conditional (SWITCH) \u2014 returns one of several values depending on which condition matches."
    if fn == "IF" and len(args) >= 2:
        return f"If {short(args[0], 50)}, then {short(args[1], 40)}" + (f", else {short(args[2], 40)}" if len(args) > 2 else "")
    if fn in ("SUMX", "AVERAGEX", "COUNTX", "MAXX", "MINX") and len(args) >= 2:
        verb = fn[:-1].capitalize()
        return f"{verb} of \u201c{short(args[1], 40)}\u201d evaluated row-by-row over {short(args[0], 30)}"
    if fn == "FORMAT" and args:
        return f"Formats {short(args[0])} for display"
    if fn == "COALESCE" and args:
        base = summarize_formula(args[0], _depth + 1, clean_full) if _FUNC_CALL_RE.match(args[0].strip()) else short(args[0])
        return f"{base} (or {short(args[1])} if blank)" if len(args) > 1 else base
    return f"{fn}(\u2026) \u2014 see full formula."


CALC_TYPE_ORDER = [
    ("DIVIDE", "Ratio"), ("SUM", "Sum"), ("AVERAGE", "Average"),
    ("COUNTROWS", "Count"), ("COUNT", "Count"), ("DISTINCTCOUNT", "Count"),
    ("SWITCH", "Conditional"), ("IF", "Conditional"),
]


_WRAPPER_FNS = {"COALESCE", "CALCULATE"}


def detect_calc_type(expr: str, _depth: int = 0, _clean=None) -> str:
    clean_full = _clean if _clean is not None else _strip_dax_comments(expr)
    core = _core_expression(expr) if _depth == 0 else expr.strip()
    if re.search(r"<\s*(div|html|body|span)\b", core, re.I) or "style=" in core:
        return "HTML/Display string"
    if _depth < 4 and re.match(r"^\w+$", core):
        var_def = _find_var_definition(clean_full, core)
        if var_def is not None:
            return detect_calc_type(var_def, _depth + 1, clean_full)
    m = _FUNC_CALL_RE.match(core.strip())
    fn = m.group(1).upper() if m else ""
    if fn in _WRAPPER_FNS and _depth < 4:
        inner_args = _split_top_level_args(m.group(2))
        if inner_args and not inner_args[0].strip().startswith("["):
            return detect_calc_type(inner_args[0], _depth + 1, clean_full)
    for key, label in CALC_TYPE_ORDER:
        if fn == key:
            return label
    if "VAR " in expr and "RETURN" in expr:
        return "Multi-step / composite"
    return "Other"


STRING_LITERAL_RE = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"')
PLACEHOLDER_WORD_RE = re.compile(
    r"\b(TBC|Pending|On[\s-]?Hold|N/?A|Not Available|Coming Soon|Placeholder)\b", re.I
)


def detect_status(expr: str) -> str:
    """'Placeholder / TBC' if any string literal the measure can return
    contains a placeholder-ish word (checked as a whole word inside quoted
    text, not just an exact-match literal, since these words are often
    embedded in a larger HTML fragment like '>Pending</div>'), or if the
    formula's own RETURN path is a bare BLANK()."""
    clean = _strip_dax_comments(expr)
    for lit in STRING_LITERAL_RE.findall(clean):
        if PLACEHOLDER_WORD_RE.search(lit):
            return "Placeholder / TBC"
    if re.search(r"RETURN\s+BLANK\s*\(\s*\)\s*$", _core_expression(expr).strip(), re.I):
        return "Placeholder / TBC"
    return "Live"


HEX_COLOR_RE = re.compile(r"#[0-9A-Fa-f]{6}\b")
STATUS_WORD_RE = re.compile(
    r'"((?:On|Above|Below|At)\s+Target|Watch|Critical|Pass(?:ed)?|Fail(?:ed)?|'
    r'Good|High|Low|Pending|TBC|On Hold|Over[- ]?Scan(?:ned)?|Invalid Data|'
    r'Excellent|Caution|At[- ]?Risk)"',
    re.I,
)


def detect_status_vocabulary(all_measures):
    colors, words = Counter(), Counter()
    for m in all_measures:
        colors.update(HEX_COLOR_RE.findall(m["expression"]))
        words.update(w.strip() for w in STATUS_WORD_RE.findall(m["expression"]))
    return colors, words


def find_common_filters(pages):
    """Return [(entity.property, n_pages_with_it, n_real_pages)], sorted by
    frequency. 'Real' pages = not flagged non-prod (so a one-off test page's
    slicer doesn't skew what counts as a 'common' filter)."""
    real_pages = [p for p in pages if not p["nonprodFlag"]]
    counts = Counter()
    for p in real_pages:
        seen_this_page = set()
        for v in p["visuals"]:
            if v["category"] != "Slicer":
                continue
            for r in v["refs"]:
                key = f"{r['entity']}.{r['property']}"
                seen_this_page.add(key)
        counts.update(seen_this_page)
    total = len(real_pages) or 1
    return sorted(
        [(field, n, total) for field, n in counts.items()],
        key=lambda t: -t[1],
    )


def page_content_visuals(page):
    return [v for v in page["visuals"] if v["category"] in CONTENT_CATEGORIES]


def page_measure_refs(page):
    """Distinct measure names referenced anywhere on this page, in visual
    (reading) order, de-duplicated but order-preserving."""
    seen, out = set(), []
    for v in page_content_visuals(page):
        for r in v["refs"]:
            if r["kind"] == "measure" and r["property"] not in seen:
                seen.add(r["property"])
                out.append(r["property"])
    return out


HEADLINE_CATEGORIES = {"HTML Content (custom visual)", "KPI Card"}


def page_headline_measure_refs(page):
    """Distinct measure names referenced by card/pill-style visuals only
    (HTML Content, native KPI Card) -- excluding Table and Chart visuals,
    which hold supporting detail/breakdown data rather than the headline
    figures a business reader would look at first. This distinction is
    generic (based on visual type, not any project-specific naming), so
    it applies the same way to any report."""
    seen, out = set(), []
    for v in page_content_visuals(page):
        if v["category"] not in HEADLINE_CATEGORIES:
            continue
        for r in v["refs"]:
            if r["kind"] == "measure" and r["property"] not in seen:
                seen.add(r["property"])
                out.append(r["property"])
    return out


def build_domain_groups(all_measures):
    groups = defaultdict(list)
    for m in all_measures:
        groups[m["displayFolder"]].append(m)
    return dict(groups)


# ============================================================================
# SECTION 6 -- RICHER MECHANICAL SIGNAL EXTRACTION (for the curated manual)
# ============================================================================

TARGET_VAR_RE = re.compile(
    r"\bVAR\s+(\w*(?:Target|Tgt|Threshold|Benchmark)\w*)\s*=\s*([0-9]+(?:\.[0-9]+)?)\b",
    re.I,
)


def extract_targets(expr: str):
    """Find VAR assignments whose name suggests a target/threshold/benchmark
    and whose value is a bare numeric literal -- e.g. 'VAR _OTDTgt = 0.98'.
    Returns [(var_name, numeric_value_as_text)]. Purely mechanical: the
    variable name and value are exactly what the model author wrote."""
    clean = _strip_dax_comments(expr)
    return [(n, v) for n, v in TARGET_VAR_RE.findall(clean)]


def table_usage_summary(table_name, all_measures, common_filter_fields, roles):
    """What mechanically-verifiable things can be said about a table:
    which domains' measures reference it, a couple of example measure
    names, whether one of its columns drives a common (report-wide) filter,
    and whether an RLS role filters on it. All derived from what's already
    parsed -- nothing invented."""
    referencing = [m for m in all_measures if table_name in m["_tablesReferenced"]]
    domains = sorted({m["displayFolder"] for m in referencing if m["displayFolder"] != "(ungrouped)"})
    examples = [m["name"] for m in referencing[:3]]
    is_filter = any(f.split(".")[0] == table_name for f in common_filter_fields)
    rls_roles = [r["name"] for r in roles if any(p["table"] == table_name for p in r["tablePermissions"])]
    return {
        "measureCount": len(referencing), "domains": domains, "examples": examples,
        "isCommonFilter": is_filter, "rlsRoles": rls_roles,
    }


# ============================================================================
# SECTION 5 -- ANALYSIS ORCHESTRATION (ties parsing + analysis together)
# ============================================================================

DOMAIN_PALETTE = [
    ("4C1D95", "EDE9FE"), ("92400E", "FEF3CD"), ("9B1C1C", "FDECEA"),
    ("1E3A5F", "E0F2FE"), ("14532D", "E6F4EA"), ("065F46", "F0FDF4"),
    ("6B21A8", "FDF4FF"), ("713F12", "FEF9C3"), ("155E75", "CFFAFE"),
    ("7C2D12", "FFEDD5"),
]


def analyze_project(report_dir: Path, sm_dir: Path):
    tables, relationships, roles = parse_semantic_model(sm_dir)
    pages, active_page = parse_report(report_dir)

    import evidence
    from dax_explain import Explainer
    measures_by_name = {m["name"]: m for t in tables for m in t["measures"]}
    explainer = Explainer(measures_by_name)
    report_evidence = evidence.scan_report(report_dir, explainer)
    evidence.classify_pages(pages, report_evidence, active_page)

    real_tables = [t for t in tables if not t["isDateTable"]]
    date_table_count = len(tables) - len(real_tables)
    all_measures = [m for t in tables for m in t["measures"]]

    domain_groups = build_domain_groups(all_measures)
    domains_sorted = sorted(d for d in domain_groups if d != "(ungrouped)")
    if "(ungrouped)" in domain_groups:
        domains_sorted.append("(ungrouped)")
    domain_style = {}
    for i, d in enumerate(domains_sorted):
        fg, bg = DOMAIN_PALETTE[i % len(DOMAIN_PALETTE)]
        domain_style[d] = {"fg": fg, "bg": bg}

    common_filters = find_common_filters(pages)
    status_colors, status_words = detect_status_vocabulary(all_measures)

    # which measures reference a given table, by simple name-token search --
    # best-effort (a measure that references [Column] without qualifying the
    # table, via an implicit CALCULATE context, won't be caught; this is a
    # deliberately conservative heuristic, not a full dependency resolver)
    real_table_names = [t["name"] for t in real_tables]

    def tables_referenced(expr):
        found = []
        for tn in real_table_names:
            if re.search(rf"\b{re.escape(tn)}\b", expr):
                found.append(tn)
        return found

    for m in all_measures:
        m["_tablesReferenced"] = tables_referenced(m["expression"])
        m["_columnsReferenced"] = re.findall(
            r"(?:'([^']+)'|\b([A-Za-z_][A-Za-z0-9_]*)\b)\[([^\]\[]+)\]", m["expression"]
        )

    return {
        "tables": tables, "realTables": real_tables, "dateTableCount": date_table_count,
        "relationships": relationships, "roles": roles,
        "pages": pages, "activePage": active_page,
        "allMeasures": all_measures, "domainGroups": domain_groups,
        "domainsSorted": domains_sorted, "domainStyle": domain_style,
        "commonFilters": common_filters, "statusColors": status_colors,
        "statusWords": status_words,
        "evidence": report_evidence, "explainer": explainer,
        "measuresByName": measures_by_name,
    }


def project_name_from_dirs(report_dir: Path, sm_dir: Path) -> str:
    n1 = re.sub(r"\.Report$", "", report_dir.name, flags=re.I)
    n2 = re.sub(r"\.SemanticModel$", "", sm_dir.name, flags=re.I)
    return n1 if n1 == n2 else (n1 or n2 or "Project")
