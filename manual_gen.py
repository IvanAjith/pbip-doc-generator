"""
manual_gen.py -- the business-user Word manual.

Structure follows the reference manual (Cover, INDEX, Document Control,
Introduction, Data Sources, Report Structure, Common Filters, Value & Display
Conventions, Design Language, one section per page, How to Use the Report).

Every sentence is built from something found in the project files. Where the
project has no evidence for a statement (no conditional formatting, no
bookmarks, no thresholds...), the statement is simply not written.
"""
import re
from collections import Counter, OrderedDict

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

import docx_helpers as H
import evidence as EV
from dax_explain import hex_to_name, humanize_column, humanize_table
from kpis import format_kind, smart_case

_NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
                 8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}
KIND_LABEL = {"card": "KPI card", "value": "KPI card", "status": "status badge", "html_table": "table",
              "table": "table", "chart": "chart"}


def _n(n):
    return _NUMBER_WORDS.get(n, str(n))


def _join(items, last="and"):
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + f" {last} " + items[-1]


def _pname(page):
    return page["displayName"].strip()


def _field_label(field):
    """'VW_DIM_DATE.YEAR_MONTH' -> 'Year Month'"""
    return humanize_column(field.split(".", 1)[-1])


# ---------------------------------------------------------------- evidence summaries

def _headline_items(items):
    return [i for i in items if i["kind"] in ("card", "value", "status", "html_table")]


def page_summary(items, page):
    """One evidence-based sentence about what a page contains."""
    heads = _headline_items(items)
    tables = [i for i in items if i["kind"] == "table"]
    charts = [i for i in items if i["kind"] == "chart"]
    names = list(OrderedDict.fromkeys(i["display"] for i in heads))
    parts = []
    if names:
        shown = names[:8]
        more = len(names) - len(shown)
        parts.append(f"{len(names)} indicator{'s' if len(names) != 1 else ''}"
                     f" ({_join(shown)}{f' and {more} more' if more > 0 else ''})")
    if tables:
        parts.append(f"{len(tables)} table{'s' if len(tables) != 1 else ''}")
    if charts:
        parts.append(f"{len(charts)} chart{'s' if len(charts) != 1 else ''}")
    if not parts:
        return f"The {_pname(page)} page contains no indicators, tables or charts."
    return f"The {_pname(page)} page shows " + _join(parts) + "."


def short_summary(items):
    heads = list(OrderedDict.fromkeys(i["display"] for i in _headline_items(items)))
    if heads:
        shown = heads[:5]
        more = len(heads) - len(shown)
        return "shows " + _join(shown) + (f" and {more} more" if more > 0 else "")
    tabs = [i["display"] for i in items if i["kind"] in ("table", "chart")]
    return ("shows " + _join(list(OrderedDict.fromkeys(tabs))[:4])) if tabs else "has no content visuals"


def _walk(node, fn):
    if isinstance(node, list):
        for x in node:
            _walk(x, fn)
    elif isinstance(node, tuple) and node:
        fn(node)
        for x in node[1:]:
            _walk(x, fn)


def tables_used(analysis, pages):
    """Tables read by anything shown on the given pages: measures (followed
    through the measures they call), slicer fields, and row-level security."""
    ex = analysis["explainer"]
    real = {t["name"] for t in analysis["realTables"]}
    memo = {}

    def of_measure(name, stack=()):
        if name in memo:
            return memo[name]
        if name in stack:
            return set()
        out = set()
        node = ex.ast(name)

        def visit(n):
            if n[0] == "col" and n[1] in real:
                out.add(n[1])
            elif n[0] in ("id", "table") and n[1] in real:
                out.add(n[1])
            elif n[0] == "meas":
                real_name = ex._lookup_measure(n[1])
                if real_name:
                    out.update(of_measure(real_name, stack + (name,)))
        if node:
            _walk(node, visit)
        memo[name] = out
        return out

    used, counts = set(), Counter()
    counted = set()
    for p in pages:
        for v in p["visuals"]:
            for r in v["refs"]:
                if r["entity"] in real:
                    used.add(r["entity"])
                if r["kind"] == "measure" and r["property"] in analysis["measuresByName"]:
                    for t in of_measure(r["property"]):
                        used.add(t)
                        if (t, r["property"]) not in counted:
                            counted.add((t, r["property"]))
                            counts[t] += 1
    for p in pages:
        for s in analysis["evidence"].get(p["id"], {}).get("slicers", []):
            if s["field"]:
                used.add(s["field"].split(".")[0])
    for role in analysis["roles"]:
        for tp in role["tablePermissions"]:
            used.add(tp["table"])
    return used & real, counts


def describe_table(t, counts, kind_label):
    src = t.get("source") or {}
    bits = []
    if src.get("object"):
        loc = ".".join(x for x in (src.get("database"), src.get("schema"), src.get("object")) if x)
        bits.append(f"{(src.get('objectKind') or 'Table').title()} {loc}.")
    cols = [c for c in t["columns"] if not c["isHidden"]
            and not re.search(r"(^|_)(key|id)$", c["name"], re.I)][:4]
    if cols:
        bits.append(f"{len(t['columns'])} columns, including " + _join([humanize_column(c["name"]) for c in cols]) + ".")
    elif t["columns"]:
        bits.append(f"{len(t['columns'])} columns.")
    if counts.get(t["name"]):
        bits.append(f"Used by {counts[t['name']]} measure{'s' if counts[t['name']] != 1 else ''} shown in this manual.")
    return " ".join(bits) or "—"


# ---------------------------------------------------------------- section builders

def build_introduction(document, project_name, analysis, primary, page_items):
    H.h1(document, "Introduction")
    H.h2(document, "Document Purpose")
    H.para(document, f"This manual explains the {project_name} report for business users. For each page it "
                     f"describes what is shown, how to use the filters and buttons, and what the figures mean.",
           size=10.5)
    H.para(document, f"The report contains {_n(len(primary))} page{'s' if len(primary) != 1 else ''}:", size=10.5)
    H.bullets(document, [f"{_pname(p)} – {short_summary(page_items[p['id']])}." for p in primary])

    src = _source_summary(analysis)
    if src:
        H.para(document, src, size=10.5)


_FRIENDLY_SOURCES = {
    "Snowflake": "Snowflake", "Sql": "SQL Server", "Excel": "Excel workbook", "Csv": "CSV file",
    "Lakehouse": "Microsoft Fabric Lakehouse", "Fabric": "Microsoft Fabric", "PostgreSQL": "PostgreSQL",
    "MySQL": "MySQL", "Oracle": "Oracle", "GoogleBigQuery": "Google BigQuery", "Databricks": "Databricks",
    "SharePoint": "SharePoint", "Web": "a web source", "OData": "an OData feed", "Json": "JSON file",
    "AnalysisServices": "Analysis Services", "Salesforce": "Salesforce", "AzureStorage": "Azure storage",
    "Teradata": "Teradata", "Folder": "a folder of files", "Access": "Access database",
}


_M_TRANSFORMS = {"Table", "List", "Text", "Number", "Date", "DateTime", "Record", "Value", "Binary", "Splitter",
                 "Combiner", "Replacer", "Comparer", "Duration", "Time", "Logical", "Int64", "Uri", "Json", "Xml"}


def _source_summary(analysis):
    tabs = [t for t in analysis["realTables"] if t.get("source")]
    conns = Counter()
    schemas, dbs, files = OrderedDict(), OrderedDict(), OrderedDict()
    for t in tabs:
        s = t["source"]
        if s.get("connector"):
            prefix = s["connector"].split(".")[0]
            if prefix in _FRIENDLY_SOURCES or prefix not in _M_TRANSFORMS:
                conns[_FRIENDLY_SOURCES.get(prefix, prefix)] += 1
        if s.get("database"):
            dbs[s["database"]] = 1
        if s.get("schema"):
            schemas[s["schema"]] = 1
        if s.get("file"):
            files[s["file"]] = 1
    if not conns:
        return ""
    names = [n for n, _ in conns.most_common()]
    parts = []
    if dbs:
        parts.append(f"database{'s' if len(dbs) > 1 else ''} {_join(list(dbs))}")
    if schemas:
        parts.append(f"schema{'s' if len(schemas) > 1 else ''} {_join(list(schemas))}")
    if files:
        parts.append(f"file{'s' if len(files) > 1 else ''} {_join(list(files))}")
    text = f"Data source: {_join(names)}"
    return text + (" — " + ", ".join(parts) if parts else "") + "."


def build_data_sources(document, analysis, primary, section_no):
    H.h1(document, f"{section_no}. Data Sources – Tables & Views Used")
    used, counts = tables_used(analysis, primary)
    tables = [t for t in analysis["realTables"] if t["name"] in used]
    from app import classify_dim_fact
    kinds = {t["name"]: classify_dim_fact(t["name"], analysis["relationships"]) for t in tables}
    n_views = sum(1 for t in tables if (t.get("source") or {}).get("objectKind") == "View")
    n_tabs = sum(1 for t in tables if (t.get("source") or {}).get("objectKind") == "Table")
    n_other = len(tables) - n_views - n_tabs
    bits = []
    if n_views or n_tabs:
        bits = [b for b in (f"{n_views} loaded from database views" if n_views else "",
                            f"{n_tabs} from database tables" if n_tabs else "",
                            f"{n_other} from another source or calculated in the report" if n_other else "") if b]
    msg = (f"The pages in this manual read from {len(tables)} data table{'s' if len(tables) != 1 else ''}"
           + (f" ({_join(bits)})" if bits and len(bits) > 0 and len(tables) > 0 else "") + ".")
    unused = len(analysis["realTables"]) - len(tables)
    if unused > 0:
        msg += f" A further {unused} table{'s' if unused != 1 else ''} in the model {'is' if unused == 1 else 'are'} not used by these pages."
    H.para(document, msg, size=10.5)
    for title, kind in (("Dimension / Reference Tables", "Dimension"), ("Fact / Transactional Tables", "Fact")):
        group = sorted([t for t in tables if kinds[t["name"]] == kind], key=lambda t: t["name"])
        if not group:
            continue
        H.h2(document, f"{section_no}.{1 if kind == 'Dimension' else 2}  {title}", log=False)
        H.data_table(document, ["Table", "Description"],
                     [[t["name"], describe_table(t, counts, kind)] for t in group], mono_cols={0})
        document.add_paragraph()


def build_report_structure(document, primary, page_items, section_no):
    H.h1(document, f"{section_no}. Report Structure")
    H.para(document, f"The report contains {_n(len(primary))} page{'s' if len(primary) != 1 else ''}:", size=10.5)
    for i, p in enumerate(primary, 1):
        H.h2(document, f"{section_no}.{i}  {_pname(p)}")
        s = page_summary(page_items[p["id"]], p)
        H.para(document, s, size=10.5)


def common_filters(analysis, primary):
    """Slicer fields present on every primary page, with their sync status."""
    per_page = []
    for p in primary:
        d = {}
        for s in analysis["evidence"].get(p["id"], {}).get("slicers", []):
            if s["field"]:
                d[s["field"]] = s
        per_page.append(d)
    if not per_page:
        return []
    common = set(per_page[0])
    for d in per_page[1:]:
        common &= set(d)
    out = []
    for f in sorted(common, key=lambda f: list(per_page[0]).index(f)):
        groups = {d[f]["sync"] for d in per_page}
        out.append({"field": f, "synced": len(groups) == 1 and None not in groups and len(primary) > 1})
    return out


def placeholder(document, caption):
    box = H.dashed_border_table(document, 100)
    c = box.rows[0].cells[0]
    c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = c.paragraphs[0].add_run("SCREENSHOT PLACEHOLDER")
    r.bold = True
    r.font.size = Pt(9)
    r.font.color.rgb = H.GREY
    p2 = c.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r2 = p2.add_run(caption)
    r2.italic = True
    r2.font.size = Pt(9)
    r2.font.color.rgb = H.GREY
    document.add_paragraph()


def build_common_filters(document, analysis, primary, section_no):
    filters = common_filters(analysis, primary)
    title = "Common Filters (Available on All Pages)" if filters else "Filters"
    H.h1(document, f"{section_no}. {title}")
    if filters:
        one = len(filters) == 1
        H.para(document, f"The following {'filter appears' if one else _n(len(filters)) + ' filters appear'} "
                         f"on every page of the report:", size=10.5)
        placeholder(document, "Filter panel — " + " / ".join(_field_label(f["field"]) for f in filters))
        for f in filters:
            line = f"{_field_label(f['field'])}  ({f['field']})"
            if f["synced"]:
                line += " — a selection made on one page carries over to the other pages"
            H.bullets(document, [line])
    else:
        H.para(document, "No filter appears on every page of the report.", size=10.5)
    for role in analysis["roles"]:
        tabs = [tp["table"] for tp in role["tablePermissions"]]
        if tabs:
            H.para(document, f"Row-level security: the role “{role['name']}” limits which rows each user "
                             f"can see, using filters on {_join(tabs)}.", size=10.5)


def build_value_conventions(document, analysis, primary, page_items, section_no):
    H.h1(document, f"{section_no}. Value & Display Conventions")
    kinds = Counter()
    seen = set()
    measures = analysis["measuresByName"]
    for p in primary:
        for it in page_items[p["id"]]:
            m = it.get("measure")
            if m and m not in seen and it["kind"] in ("card", "value", "status"):
                seen.add(m)
                k = it.get("unit") or format_kind((measures.get(m) or {}).get("formatString"))
                if k:
                    kinds[k] += 1
    if kinds:
        phr = {"percent": "percentages", "currency": "currency amounts", "number": "plain numbers"}
        H.para(document, "Indicators in this report are displayed as " +
               _join([f"{phr[k]} ({n})" for k, n in kinds.most_common()]) + ".", size=10.5)

    # colour table: only colours that appear in the report's own logic
    table = OrderedDict()
    for p in primary:
        for it in page_items[p["id"]]:
            rules = [r for r in it.get("rules", []) if r.get("chain") == min(
                [x.get("chain", 1) for x in it["rules"]] or [1])]
            for r in rules:
                nm = hex_to_name(r["colour"])
                e = table.setdefault(nm, {"labels": [], "where": []})
                if r.get("label") and r["label"] not in e["labels"]:
                    e["labels"].append(r["label"])
                if it["display"] not in e["where"]:
                    e["where"].append(it["display"])
    if table:
        H.para(document, "The report colours some indicators according to rules written into it. The colours "
                         "used, the label shown with each (where there is one) and where they appear:", size=10.5)
        rows = []
        for nm, e in table.items():
            where = _join(e["where"][:5]) + (f" and {len(e['where']) - 5} more" if len(e["where"]) > 5 else "")
            rows.append([nm.title(), ", ".join(e["labels"][:4]) or "—", where])
        H.data_table(document, ["Colour", "Label shown", "Where it appears"], rows)
        H.para(document, "The exact condition behind each colour is given in the “Key Things to Watch” "
                         "part of each page’s section.", size=10.5, italic=True)
        document.add_paragraph()
    if not kinds and not table:
        H.para(document, "The report does not define any special value formats or colour rules for the "
                         "indicators described in this manual.", size=10.5)


def _meaning(item):
    """The 'What it means' cell, assembled only from what is known."""
    parts = []
    d = item.get("definition")
    k = item["kind"]
    if k in ("table", "chart", "html_table"):
        cols = item.get("columns") or []
        if cols:
            shown = cols[:10]
            more = len(cols) - len(shown)
            parts.append("Columns: " + ", ".join(shown) + (f" and {more} more." if more > 0 else "."))
        return " ".join(parts) or "—"
    if k == "status" and d and d.source == "manual":
        return d.text
    if k == "status":
        basis = item.get("basis")
        if basis:
            parts.append(f"A status badge based on {basis}.")
        elif item.get("rules"):
            parts.append("A status badge; how its colour is decided is listed under \u201cKey Things to Watch\u201d.")
        else:
            parts.append("A status badge.")
        if d:
            lead = "" if basis else "General meaning of the term: "
            parts.append(lead + d.text + (" (Found online — please verify.)" if d.source == "web" else " (AI draft — please verify.)" if d.source == "ai" else ""))
        return " ".join(parts)
    if d:
        parts.append(d.text + {"web": " (Found online — please verify.)", "ai": " (AI draft — please verify.)",
                               "draft": " (Draft from the formula — please verify.)"}.get(d.source, ""))
    if item.get("calc") and not (d and d.source == "draft"):
        parts.append(f"Calculated as: {item['calc']}.")
    if item.get("label_logic"):
        parts.append("Shows a text label: " + item["label_logic"] + ".")
    also = item.get("also_shows")
    if also:
        lead = "Also shown on this tile: " if parts else "A summary tile that shows several figures together: "
        parts.append(lead + _join(also[:8]) + (f" and {len(also) - 8} more" if len(also) > 8 else "") + ".")
    if not parts:
        parts.append(H.NEEDS_MARK + "Definition needed \u2014 see the KPI Glossary.")
    return " ".join(parts)


from design_language import _words as _words_, _top, name_of


def _col(h):
    return f"{h} ({name_of(h)})"


def _size_txt(v):
    return f"{v:g} pt" if isinstance(v, (int, float)) else "\u2014"


def build_design_language(document, project_name, design, section_no):
    """The look of the report, read from its theme and formatting (design_language.py). Written only from what was found."""
    H.h1(document, f"{section_no}. Design Language")
    H.para(document, f"This section records how the {project_name} report looks, so that a new page or a new report can be built to match "
                     "it. Everything here was read from the report's own files; where the report sets nothing, Power BI's defaults apply "
                     "and nothing is invented.", size=10.5)
    design = design or {}
    if design.get("error") or not design:
        H.para(document, "The report's formatting could not be read, so this section is empty.", size=10.5)
        return
    th, k = design["theme"], 1

    # ---- theme and colours
    H.h2(document, f"{section_no}.{k}  Theme and colour palette"); k += 1
    cf, bf = th.get("custom_file"), th.get("base_file")
    if th.get("custom"):
        H.para(document, f"The report uses the custom theme \u201c{th['custom']}\u201d"
                         + (f" on top of the built-in Power BI theme {th['base']}" if th.get("base") else "") + ". "
                         "The custom theme file is stored inside the report, in StaticResources\\RegisteredResources.", size=10.5)
    elif th.get("base"):
        H.para(document, f"The report uses the built-in Power BI theme {th['base']} and has no custom theme file.", size=10.5)
    else:
        H.para(document, "The report files name no theme, so Power BI's default theme applies.", size=10.5)
    use = cf or bf
    notes = OrderedDict()
    def add(h, text):
        if h:
            notes.setdefault(h, [])
            if text not in notes[h]:
                notes[h].append(text)
    if use:
        for i, h in enumerate(use["data"], 1):
            add(h, f"Theme chart colour {i}")
        for key, h in use["colours"].items():
            add(h, EV_THEME_ROLE.get(key, key))
    for h, n, roles in design["colours"]:
        add(h, f"Set directly on {n} visual{'s' if n != 1 else ''}: " + ", ".join(roles))
    html = design["html"]
    for h, n in html["colours"][:8]:
        add(h, f"Inside HTML visuals ({n} measure{'s' if n != 1 else ''})")
    if notes:
        rows = [[h, name_of(h).title(), "; ".join(v[:3])] for h, v in list(notes.items())[:28]]
        H.swatch_table(document, ["Swatch", "Colour", "Used for"], rows, [0.16, 0.18, 0.66])
        document.add_paragraph()
    else:
        H.para(document, "No colours are set in the theme or typed into the visuals.", size=10.5)
    extra = []
    if design["theme_refs"]:
        extra.append(f"{design['theme_refs']} formatting settings pick a theme colour by number, so they follow the theme if it is changed")
    if design["rule_colours"]:
        extra.append(f"{design['rule_colours']} settings take their colour from a rule or a measure; those rules are described under "
                     "Value & Display Conventions and on each page")
    if th.get("images"):
        extra.append("images stored in the report: " + ", ".join(th["images"][:6]))
    if extra:
        H.bullets(document, [e[0].upper() + e[1:] + "." for e in extra])

    # ---- typography
    rows = []
    if use:
        for t in use["text"]:
            rows.append([TEXT_LABEL.get(t["class"], f"Theme: {t['class']}"), t["font"] or "\u2014", _size_txt(t["size"]), "Theme"])
    for t in design["typography"]:
        fonts = " / ".join(f for f, _ in t["fonts"]) or "(theme font)"
        sizes = _size_txt(t["size"]) + (f" (range {min(t['sizes']):g}\u2013{max(t['sizes']):g})" if len(t["sizes"]) > 1 else "")
        rows.append([t["element"], fonts, sizes, f"{t['n']} setting{'s' if t['n'] != 1 else ''} in visuals"])
    if html["measures"] and (html["fonts"] or html["sizes"]):
        rows.append(["Text inside HTML visuals", " / ".join(f for f, _ in html["fonts"]) or "\u2014",
                     ", ".join(s for s, _ in html["sizes"]) or "\u2014", f"{html['measures']} HTML measure{'s' if html['measures'] != 1 else ''}"])
    if rows:
        H.h2(document, f"{section_no}.{k}  Fonts and text sizes"); k += 1
        H.data_table(document, ["Where", "Font", "Size", "Set in"], rows, [0.34, 0.26, 0.22, 0.18])
        document.add_paragraph()

    # ---- canvas
    H.h2(document, f"{section_no}.{k}  Canvas and page layout"); k += 1
    if design["sizes"]:
        (w, h), n = design["sizes"][0]
        g = _ratio(w, h)
        same = len(design["sizes"]) == 1
        H.para(document, f"{'All' if same else 'Most'} pages use a canvas of {w} \u00D7 {h} pixels" + (f" ({g})" if g else "")
               + ("" if same else f" ({n} of {sum(c for _, c in design['sizes'])} pages)") + ".", size=10.5)
    gr = design["grid"]
    if "margin_left" in gr:
        H.para(document, f"Content starts about {gr['margin_left']} px from the left edge and {gr['margin_top']} px from the top.", size=10.5)
    if "gap_h" in gr or "gap_v" in gr:
        gaps = []
        if "gap_h" in gr:
            gaps.append(f"{gr['gap_h']} px apart side to side")
        if "gap_v" in gr:
            gaps.append(f"{gr['gap_v']} px apart top to bottom")
        H.para(document, "Neighbouring visuals are usually " + " and ".join(gaps) + ".", size=10.5)
    rows = [[p["name"], f"{p['width']} \u00D7 {p['height']}" if p["width"] and p["height"] else "\u2014", p["display"] or "\u2014",
             p["background"] or "Theme default", p["wallpaper"] or "\u2014"] for p in design["pages"]]
    if rows:
        H.data_table(document, ["Page", "Canvas (px)", "Fit option", "Page background", "Behind the page"], rows, [0.27, 0.15, 0.14, 0.26, 0.18])
        document.add_paragraph()

    # ---- cards
    st = design["style"]
    H.h2(document, f"{section_no}.{k}  Visual and card style"); k += 1
    lines = []
    if st["n"]:
        def share(x):
            return f"{x} of {st['n']}"
        if st["background"]:
            lines.append(f"Background set on {share(st['background'])} visuals.")
        if st["border"]:
            r = st["radius"]
            lines.append(f"Border on {share(st['border'])} visuals" + (f", corner radius {_top(r)[0]:g} px" + (" (most common)" if len(r) > 1 else "") if r else "") + ".")
        if st["shadow"]:
            lines.append(f"Shadow on {share(st['shadow'])} visuals.")
        if st["title"]:
            lines.append(f"Title switched on for {share(st['title'])} visuals.")
        if st["header_hidden"]:
            lines.append(f"The visual header icons are hidden on {share(st['header_hidden'])} visuals.")
        if st["padding"]:
            t_, r_, b_, l_ = _top(st["padding"])[0]
            lines.append(f"Inner padding, most common: top {t_:g}, right {r_:g}, bottom {b_:g}, left {l_:g} px.")
    dfl = (use or {}).get("defaults") or {}
    if dfl:
        bits = []
        for obj, info in dfl.items():
            part = ", ".join(f"{_words_(key)} {v}" for key, v in info.items() if key != "show" or v is not True)
            bits.append(f"{_words_(obj)}: {part}")
        lines.append("Default style set by the theme for every visual \u2013 " + "; ".join(bits) + ".")
    if html["measures"] and (html["radii"] or html["shadows"]):
        s = []
        if html["radii"]:
            s.append("rounded corners (" + ", ".join(r for r, _ in html["radii"]) + ")")
        if html["shadows"]:
            s.append(f"shadows in {html['shadows']} measure{'s' if html['shadows'] != 1 else ''}")
        lines.append("HTML visuals draw their own cards with " + " and ".join(s) + ".")
    if lines:
        H.para(document, "Counted from what the report sets explicitly:", size=10.5)
        H.bullets(document, lines)
    else:
        H.para(document, "The visuals do not override Power BI's default card style (no background, border, shadow or title is set).", size=10.5)

    # ---- how to match
    tips = []
    if th.get("custom"):
        tips.append(f"Apply the theme \u201c{th['custom']}\u201d (View > Themes > Browse for themes, using the file in the report's StaticResources folder).")
    elif th.get("base"):
        tips.append(f"Start from the built-in Power BI theme {th['base']}.")
    if design["sizes"]:
        (w, h), _n_ = design["sizes"][0]
        tips.append(f"Set the page canvas to {w} \u00D7 {h} pixels (Format page > Canvas settings).")
    if use and use["data"]:
        tips.append("Colour chart series in the theme order: " + ", ".join(_col(h) for h in use["data"][:6]) + ("." if len(use["data"]) <= 6 else ", and so on."))
    if design["typography"]:
        t0 = design["typography"][0]
        tips.append(f"Use {' / '.join(f for f, _ in t0['fonts']) or 'the theme font'} for text; {t0['element'].lower()} are "
                    f"{_size_txt(t0['size'])}.")
    if "gap_h" in gr:
        tips.append(f"Leave about {gr['gap_h']} px between visuals and keep content about {gr.get('margin_left', 0)} px from the edge.")
    if tips:
        H.para(document, "To build a new page or report in the same style:", size=10.5, bold=True)
        H.bullets(document, tips)
    document.add_paragraph()


EV_THEME_ROLE = {"background": "Page and card background (theme)", "secondaryBackground": "Second background (theme)",
                 "foreground": "Text (theme)", "tableAccent": "Table accent (theme)", "good": "Good (theme)",
                 "neutral": "Neutral (theme)", "bad": "Bad (theme)", "minimum": "Colour scale: lowest (theme)",
                 "center": "Colour scale: middle (theme)", "maximum": "Colour scale: highest (theme)"}
TEXT_LABEL = {"title": "Theme: title text", "callout": "Theme: big card numbers", "label": "Theme: labels", "header": "Theme: headers",
              "largeTitle": "Theme: large title", "smallLabel": "Theme: small labels", "boldLabel": "Theme: bold labels"}


def _ratio(w, h):
    from math import gcd
    g = gcd(int(w), int(h))
    a, b = int(w) // g, int(h) // g
    return f"{a}:{b}" if a <= 32 and b <= 32 else ""


def _usage_bullets(page, analysis, primary_ids):
    ev = analysis["evidence"].get(page["id"], {})
    out = []
    sl = [s for s in ev.get("slicers", []) if s["field"]]
    if sl:
        out.append("Use the filters on the page (" + _join([_field_label(s["field"]) for s in sl]) +
                   ") to choose what the figures show.")
    by_id = {p["id"]: p for p in analysis["pages"]}
    targets = [by_id[t] for t in ev.get("nav", []) if t in by_id and t != page["id"]]
    main = [_pname(t) for t in analysis["pages"] if t in targets and t["id"] in primary_ids]
    side = [_pname(t) for t in analysis["pages"] if t in targets and t["id"] not in primary_ids]
    if main:
        out.append("Use the navigation buttons to move to another page: " + _join(main) + ".")
    if side:
        out.append("Buttons on this page also open " + _join([f"“{s}”" for s in side]) +
                   ", which " + ("is a detail page" if len(side) == 1 else "are detail pages") +
                   " that is not part of the main navigation.")
    if ev.get("bookmarks"):
        out.append("Use the view buttons on the page to switch between its saved views: " +
                   _join([f"“{b}”" for b in ev["bookmarks"]]) + ".")
    return out


def _watch_bullets(page, items, analysis):
    out = []
    for it in items:
        sents = it.get("colour_sentences") or []
        if not sents:
            continue
        shown = [t.replace("Colour coding: ", "", 1) for t in sents[:3]]
        extra = len(sents) - len(shown)
        text = " ".join(("Also, " + x[len("Also: "):] if x.startswith("Also: ") else x) for x in shown)
        if extra:
            text += (f" ({extra} more colour rule{'s' if extra > 1 else ''} on this tile "
                     f"{'are' if extra > 1 else 'is'} listed in the technical reference.)")
        out.append(f"{it['display']}: {text}")
    ev = analysis["evidence"].get(page["id"], {}).get("visuals", {})
    names = {i.get("visual_id"): i["display"] for i in items if i.get("visual_id")}
    seen = set()
    for v in page["visuals"]:
        for r in ev.get(v["id"], {}).get("rules", []):
            sent = EV.describe_rule(r)
            key = (names.get(v["id"]), sent)
            if sent and key not in seen:
                seen.add(key)
                label = names.get(v["id"]) or "A table on this page"
                out.append(f"{label}: {sent}")
    return out


def build_page_section(document, page, items, analysis, primary_ids, section_no):
    name = _pname(page)
    H.h1(document, f"{section_no}. {name} Page")

    H.h2(document, f"{section_no}.1  What This Page Shows You", log=False)
    H.para(document, page_summary(items, page), size=10.5)
    placeholder(document, f"{name} page — full canvas, filters and visuals visible")

    H.h2(document, f"{section_no}.2  How to Use This Page", log=False)
    bullets = _usage_bullets(page, analysis, primary_ids)
    if bullets:
        H.bullets(document, bullets)
    else:
        H.para(document, "This page has no filters or navigation buttons of its own.", size=10.5)

    H.h2(document, f"{section_no}.3  Understanding What You’re Looking At", log=False)
    if items:
        H.data_table(document, ["What you see", "What it means"],
                     [[f"{it['display']}  ({KIND_LABEL.get(it['kind'], it['kind'])})", _meaning(it)] for it in items])
        document.add_paragraph()
    else:
        H.para(document, "This page has no indicators, tables or charts.", size=10.5)

    H.h2(document, f"{section_no}.4  Key Things to Watch", log=False)
    watch = _watch_bullets(page, items, analysis)
    if watch:
        H.bullets(document, watch)
    else:
        H.para(document, "No targets, thresholds or colour rules are defined for this page.", size=10.5)


def build_how_to_use(document, analysis, primary, section_no):
    H.h1(document, f"{section_no}. How to Use the Report")
    steps = []
    filters = common_filters(analysis, primary)
    if filters:
        synced = all(f["synced"] for f in filters)
        steps.append("Choose the filters (" + _join([_field_label(f["field"]) for f in filters]) +
                     f") at the top of any page — they appear on all {len(primary)} pages" +
                     (", and a selection carries over when you change page." if synced else "."))
    active = next((p for p in primary if p["id"] == analysis.get("activePage")), None)
    if active:
        steps.append(f"The report opens on the {_pname(active)} page.")
    nav_targets = Counter()
    for p in primary:
        nav_targets.update(t for t in analysis["evidence"].get(p["id"], {}).get("nav", []) if t != p["id"])
    if nav_targets:
        steps.append("Move between pages with the navigation buttons: " + _join([_pname(p) for p in primary]) + ".")
    steps.append("Read the section for each page in this manual to see what its indicators mean "
                 "and which thresholds and colours it uses.")
    for i, s in enumerate(steps, 1):
        para = document.add_paragraph()
        para.paragraph_format.space_after = Pt(4)
        r = para.add_run(f"{i}.  {s}")
        r.font.size = Pt(10.5)


# ---------------------------------------------------------------- entry point

def build_manual(project_name, analysis, page_items, output_path, meta,
                 toc_page_map=None, toc_entries=None):
    document = Document()
    document._toc_log = []
    st = document.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(10.5)
    for sec in document.sections:
        sec.left_margin = sec.right_margin = Pt(64)
        sec.top_margin = sec.bottom_margin = Pt(60)
        fp = sec.footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = fp.add_run(f"{project_name} – User Manual   |   Page ")
        r.font.size = Pt(8)
        H.add_page_number_field(fp)
    H.add_page_logo(document)
    H.copy_footer_to_first_page(document, f"{project_name} – User Manual   |   Page ")
    primary = [p for p in analysis["pages"] if p.get("mainNav")]
    primary_ids = {p["id"] for p in primary}

    H.build_cover(document, project_name, "User Manual")
    H.build_index(document, toc_page_map, toc_entries)
    H.build_doc_control(document, project_name, meta)
    if not toc_page_map:
        H.set_update_fields_on_open(document)

    build_introduction(document, project_name, analysis, primary, page_items)
    n = 1
    build_data_sources(document, analysis, primary, n); n += 1
    build_report_structure(document, primary, page_items, n); n += 1
    build_common_filters(document, analysis, primary, n); n += 1
    build_value_conventions(document, analysis, primary, page_items, n); n += 1
    build_design_language(document, project_name, analysis.get("design"), n); n += 1
    for p in primary:
        build_page_section(document, p, page_items[p["id"]], analysis, primary_ids, n)
        n += 1
    build_how_to_use(document, analysis, primary, n)
    document.save(str(output_path))
    return document._toc_log
