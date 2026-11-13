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
            return "Your own definition (my_definitions.csv)"
        if d.source == "ai":
            return "AI draft — please verify." + (f"\nCheck: {d.note}" if getattr(d, "note", "") else "")
        if d.source == "draft":
            return "Draft from the formula — please verify."
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

    primary = [p for p in analysis["pages"] if p.get("mainNav")]
    landing = analysis.get("activePage")
    ordered = [p for p in primary if p["id"] != landing] + [p for p in primary if p["id"] == landing]

    H.build_cover(document, project_name, "KPI Glossary")
    H.build_doc_control(document, project_name, meta, title_suffix="KPI Glossary")

    H.h1(document, "About This Glossary", log=False)
    H.para(document, f"This glossary explains the indicators used in the {project_name} report in plain language. "
                     "Each entry shows what the indicator means, how the report calculates it (taken from the "
                     "report’s own formulas), and where the definition came from.", size=10.5)
    H.bullets(document, [
        "Built-in glossary — a standard definition that ships with the tool.",
        "Your own definition — typed by you in this document (or in glossary\\my_definitions.csv) and kept on every later run.",
        "Draft from the formula — built automatically from the report’s own formula (pale yellow). It says how the "
        "figure is calculated; please check it also says what it means to the business.",
        "AI draft / Found online — written or found by the optional AI or web steps (pale yellow); please verify.",
        "Needs your definition (strong yellow) — nothing could be built or found.",
    ])
    H.para(document, "To correct or add a definition: type directly over the text in the “What it means” column and save "
                     "this file. For this glossary that is all you need to do. Run the tool again only if you also want "
                     "your wording in the user manual and the HTML reference; that run also stores it so every later run "
                     "keeps it. Keep this file in the output folder until then.", size=10.5, bold=True)

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
    missing = [i for i in flat if not i.get("definition") and not i.get("also_shows") and not i.get("label_logic")
               and i["kind"] != "status"]
    if missing:
        H.para(document, f"{len(missing)} of the {len(flat)} indicators below are shaded strong yellow because no definition "
                         "could be built or found. Their calculation, where known, is still taken from the report.",
               size=10.5, italic=True)

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
            rows.append([it["display"], meaning, calc, _source_text(it) + (f"\nAlso shown on: {appears}" if appears else "")])
        fills = {(ri, 1): DRAFT_FILL for ri, (key, e) in enumerate(sorted(entries.items(), key=lambda kv: kv[1]["item"]["display"].lower()))
                 if e["item"].get("definition") and e["item"]["definition"].source in ("draft", "ai", "web")}
        H.data_table(document, ["Indicator", "What it means", "How it is calculated", "Source"], rows, fills=fills)
        document.add_paragraph()

    # measures that are displayed only in tables / charts (each also has a row in my_definitions.csv)
    extras = page_items.get("_extra") or []
    extras = [e for e in extras if normalize(e["display"]) not in seen]
    if extras:
        H.h1(document, "Other Measures Shown in Tables and Charts", log=False)
        H.para(document, "These measures are shown as table columns or chart values. Definitions come from the same "
                         "sources as above; yellow cells are waiting for a definition in glossary\\my_definitions.csv.",
               size=10.5)
        rows = []
        for e in sorted(extras, key=lambda e: e["display"].lower()):
            meaning = _meaning(e)
            if glossary is not None:
                glossary.record_generated(normalize(e["display"]) or e["display"].lower(), Glossary._clean(meaning))
            rows.append([e["display"], meaning, e.get("calc") or "—",
                         _source_text(e) + f"\nShown on: {e['page']}"])
        ordered_x = sorted(extras, key=lambda e: e["display"].lower())
        fills = {(ri, 1): DRAFT_FILL for ri, e in enumerate(ordered_x)
                 if e.get("definition") and e["definition"].source in ("draft", "ai", "web")}
        H.data_table(document, ["Measure", "What it means", "How it is calculated", "Source"], rows, fills=fills)
    document.save(str(output_path))


def _pname_list(names):
    seen = []
    for n in names:
        if n not in seen:
            seen.append(n)
    return ", ".join(seen)
