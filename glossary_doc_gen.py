"""
glossary_doc_gen.py -- the KPI Glossary Word document.

One plain-English entry per indicator used on the report's main pages,
grouped by page, with where the definition came from and how the figure is
calculated (read from the report's own DAX). Measures that only appear inside
tables are listed at the end with their calculation, without a definition.
"""
from collections import OrderedDict

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

import docx_helpers as H
from glossary import normalize, Glossary
from kpis import is_chrome_measure


DRAFT_FILL = "FFF2CC"


def _pname(p):
    return p["displayName"].strip()


def _source_text(item):
    d = item.get("definition")
    if not d and item.get("kind") == "status":
        return "The report's colour rules"
    if d:
        if d.source == "web":
            return f"Found online — {d.origin}" + (f" ({d.url})" if d.url else "") + ". Please verify."
        if d.source == "manual":
            return "Your own definition"
        if d.source == "ai":
            return "AI draft — please verify." + (f"\nCheck: {d.note}" if getattr(d, "note", "") else "")
        if d.source == "draft":
            return "Draft from the formula — please verify."
        if d.origin.startswith("KPI document"):
            return d.origin.replace("KPI document:", "KPI document \u2014", 1)
        if d.origin == "shared glossary":
            return "Shared glossary — added and reviewed by your team."
        return "Built-in glossary"
    return "Needs your definition"


def _meaning(item):
    d = item.get("definition")
    if d and d.source == "manual":
        return d.text                      # the user's own words replace the whole cell
    if item["kind"] == "status":
        if item.get("basis"):
            base = f"A status badge based on {item['basis']}."
        elif item.get("colour_sentences"):
            base = "A status badge. " + item["colour_sentences"][0].rstrip(".") + "."
        elif item.get("rules"):
            base = "A status badge; its colour rules are listed on the page\u2019s “Key Things to Watch”."
        else:
            base = "A status badge."
        return f"{base} {d.text}".strip() if d else base
    if d:
        return d.text
    if item.get("label_logic"):
        return "Shows a text label: " + item["label_logic"] + "."
    also = item.get("also_shows")
    if also:
        return "A summary tile that shows several figures together: " + ", ".join(also[:8]) + "."
    return (H.NEEDS_MARK + "Definition needed \u2014 type it over this text.")


def build_glossary_doc(project_name, analysis, page_items, output_path, meta, glossary=None):
    document = Document()
    st = document.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(10.5)
    for sec in document.sections:
        sec.left_margin = sec.right_margin = Pt(64)
        sec.top_margin = sec.bottom_margin = Pt(60)
        fp = sec.footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = fp.add_run(f"{project_name} – KPI Glossary   |   Page ")
        r.font.size = Pt(8)
        H.add_page_number_field(fp)
    H.add_page_logo(document)
    H.copy_footer_to_first_page(document, f"{project_name} – KPI Glossary   |   Page ")

    primary = [p for p in analysis["pages"] if p.get("mainNav")]
    landing = analysis.get("activePage")
    ordered = [p for p in primary if p["id"] != landing] + [p for p in primary if p["id"] == landing]

    H.build_cover(document, project_name, "KPI Glossary")
    H.build_doc_control(document, project_name, meta, title_suffix="KPI Glossary")

    groups = OrderedDict()                      # page name -> {key: entry}
    seen = {}
    for p in ordered:
        for it in page_items[p["id"]]:
            if it["kind"] not in ("card", "value", "status"):
                continue
            key = normalize(it["display"]) or it["display"].lower()
            if key in seen:
                seen[key]["also"].append(_pname(p))
                continue
            entry = {"item": it, "also": []}
            seen[key] = entry
            groups.setdefault(_pname(p), OrderedDict())[key] = entry

    flat = [e["item"] for g in groups.values() for e in g.values()]
    extras = [e for e in (page_items.get("_extra") or []) if normalize(e["display"]) not in seen]
    total = len(flat) + len(extras)
    H.h1(document, "What This Glossary Contains", log=False)
    H.para(document, f"This glossary lists the {total} KPIs used in the {project_name} report, grouped by the report page "
                     f"where they appear ({len(groups)} page{'' if len(groups) == 1 else 's'}"
                     + (", plus the KPIs shown only in tables and charts" if extras else "") + "). "
                     "For each KPI it gives two things: what it means, in plain language, and how the report calculates it, "
                     "taken from the report\u2019s own formulas.", size=10.5)

    for page_name, entries in groups.items():
        H.h1(document, f"{page_name}", log=False)
        rows = []
        for key, e in sorted(entries.items(), key=lambda kv: kv[1]["item"]["display"].lower()):
            it = e["item"]
            appears = _pname_list(e["also"])
            calc = it.get("calc") or "—"
            meaning = _meaning(it)
            if glossary is not None:
                glossary.record_generated(normalize(it["display"]) or it["display"].lower(), Glossary._clean(meaning))
            rows.append([it["display"], meaning, calc])
        fills = None
        H.data_table(document, ["KPI", "What it means", "How it is calculated"], rows, fills=fills)
        document.add_paragraph()

    # measures that are displayed only in tables / charts (each also has a row in my_definitions.csv)
    if extras:
        H.h1(document, "Other KPIs Shown in Tables and Charts", log=False)
        H.para(document, "These KPIs are shown as table columns or chart values rather than as headline figures.", size=10.5)
        rows = []
        for e in sorted(extras, key=lambda e: e["display"].lower()):
            meaning = _meaning(e)
            if glossary is not None:
                glossary.record_generated(normalize(e["display"]) or e["display"].lower(), Glossary._clean(meaning))
            rows.append([e["display"], meaning, e.get("calc") or "—"])
        fills = None
        H.data_table(document, ["KPI", "What it means", "How it is calculated"], rows, fills=fills)
    document.save(str(output_path))


def _pname_list(names):
    seen = []
    for n in names:
        if n not in seen:
            seen.append(n)
    return ", ".join(seen)
