"""glossary_export.py -- the built-in glossary on paper, and the way it grows.

  python run.py --export-glossary [FILE.xlsx]   the built-in + shared terms, by domain, to show to anyone
  python run.py --export-shared  [FILE.csv]     definitions found/written on THIS computer that are not shared yet
  python run.py --merge-shared   FILE.csv       add the rows a reviewer marked Y to shared_glossary.csv

The tool never writes into the shared list by itself: an AI or web sentence is a draft, and a client's own
measure names must not end up in a list every colleague (and every client) receives. A person decides.
"""
import csv
import re
from datetime import date
from pathlib import Path

from seed_glossary import SEED

HERE = Path(__file__).resolve().parent
SHARED_CSV = HERE / "shared_glossary.csv"
SHARED_COLS = ["Term", "Also known as", "Domain", "Better", "Definition", "Source", "Added"]
CAND_COLS = ["Approve (Y/N)", "Term", "Domain", "Definition", "Where it came from", "Notes for the reviewer"]
SHARED_ORIGIN = "shared glossary"


def _norm(term):
    from glossary import normalize
    return normalize(term)


def read_shared(path=SHARED_CSV):
    """Rows of shared_glossary.csv as seed-style entries."""
    out = []
    p = Path(path)
    if not p.exists():
        return out
    with open(p, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            term, definition = (r.get("Term") or "").strip(), (r.get("Definition") or "").strip()
            if not term or not definition:
                continue
            aliases = [a.strip() for a in re.split(r"[;|]", r.get("Also known as") or "") if a.strip()]
            better = (r.get("Better") or "").strip().lower() or None
            out.append({"terms": [term] + aliases, "category": (r.get("Domain") or "General").strip() or "General",
                        "better": better if better in ("higher", "lower") else None, "definition": definition,
                        "origin": SHARED_ORIGIN, "added": (r.get("Added") or "").strip(),
                        "source": (r.get("Source") or "").strip()})
    return out


def known_keys(shared_path=SHARED_CSV):
    keys = set()
    for e in list(SEED) + read_shared(shared_path):
        keys.update(_norm(t) for t in e["terms"])
    return keys


# ------------------------------------------------------------------ 1. the list on paper
def rows_by_domain(shared_path=SHARED_CSV):
    rows = []
    for e in SEED:
        rows.append({"Domain": e.get("category", "General"), "Term": e["terms"][0], "Also known as": "; ".join(e["terms"][1:]),
                     "Better": e.get("better") or "", "Definition": e["definition"], "From": "Built in", "Added": ""})
    for e in read_shared(shared_path):
        rows.append({"Domain": e["category"], "Term": e["terms"][0], "Also known as": "; ".join(e["terms"][1:]),
                     "Better": e.get("better") or "", "Definition": e["definition"],
                     "From": "Shared by the team", "Added": e.get("added", "")})
    rows.sort(key=lambda r: (r["Domain"].lower(), r["Term"].lower()))
    return rows


def export_xlsx(path, shared_path=SHARED_CSV):
    """-> (path written, number of terms). Falls back to CSV when openpyxl is missing."""
    rows = rows_by_domain(shared_path)
    path = Path(path)
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        path = path.with_suffix(".csv")
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        return path, len(rows)

    head_fill, head_font = PatternFill("solid", fgColor="1F3A5F"), Font(bold=True, color="FFFFFF")
    wrap = Alignment(wrap_text=True, vertical="top")
    cols = ["Domain", "Term", "Also known as", "Better", "Definition", "From", "Added"]
    widths = [14, 28, 34, 9, 90, 18, 12]

    def table(ws, data, start_row=1):
        for c, (name, w) in enumerate(zip(cols, widths), 1):
            cell = ws.cell(row=start_row, column=c, value=name)
            cell.fill, cell.font, cell.alignment = head_fill, head_font, Alignment(vertical="center")
            ws.column_dimensions[get_column_letter(c)].width = w
        for r, row in enumerate(data, start_row + 1):
            for c, name in enumerate(cols, 1):
                ws.cell(row=r, column=c, value=row[name]).alignment = wrap
        _fit_page(ws)
        ws.print_title_rows = f"{start_row}:{start_row}"
        ws.freeze_panes = ws.cell(row=start_row + 1, column=1)
        ws.auto_filter.ref = f"A{start_row}:{get_column_letter(len(cols))}{start_row + len(data)}"

    def _fit_page(ws):                         # prints on one page width, landscape
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True

    wb = Workbook()
    ov = wb.active
    _fit_page(ov)
    ov.title = "Overview"
    domains = {}
    for r in rows:
        domains.setdefault(r["Domain"], []).append(r)
    names = sum(1 + len([a for a in r["Also known as"].split(";") if a.strip()]) for r in rows)
    lines = [
        ("Built-in KPI glossary", "title"),
        (f"{len(rows)} definitions ({names} names including alternative names) across {len(domains)} domains. "
         f"Generated on {date.today().strftime('%d/%m/%Y')}.", None),
        ("", None),
        ("How the tool uses this list", "h"),
        ("1. The tool reads every indicator and measure name from the Power BI file.", None),
        ("2. It looks each name up here by an exact match on the name or an alternative name (capital letters, % signs and "
         "brackets are ignored; a time window such as '6 months' or 'YTD' around a name is ignored too).", None),
        ("3. A match is used as it is, and the glossary document says 'Built-in glossary'. Domain is a label for reading; the tool "
         "does not guess the report's domain.", None),
        ("4. Names that are not here are searched online (optional), written by an AI (optional), or drafted from the measure's "
         "own formula. Anything you type into the glossary document always wins.", None),
        ("5. 'Shared by the team' rows were added by colleagues after review and work offline in the same way.", None),
        ("", None),
        ("Terms per domain", "h"),
    ]
    r = 1
    for text, style in lines:
        cell = ov.cell(row=r, column=1, value=text)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        if style == "title":
            cell.font = Font(bold=True, size=16, color="1F3A5F")
        elif style == "h":
            cell.font = Font(bold=True, size=12, color="1F3A5F")
        if text and not style:
            ov.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
            ov.row_dimensions[r].height = 15 * max(1, len(text) // 95 + 1)
        r += 1
    for c, name in enumerate(["Domain", "Terms", "Examples"], 1):
        cell = ov.cell(row=r, column=c, value=name)
        cell.fill, cell.font = head_fill, head_font
    for d in sorted(domains, key=lambda x: (-len(domains[x]), x)):
        r += 1
        ov.cell(row=r, column=1, value=d).alignment = Alignment(vertical="top")
        ov.cell(row=r, column=2, value=len(domains[d])).alignment = Alignment(horizontal="center", vertical="top")
        ov.cell(row=r, column=3, value=", ".join(x["Term"] for x in domains[d][:6])).alignment = wrap
    ov.column_dimensions["A"].width, ov.column_dimensions["B"].width, ov.column_dimensions["C"].width = 28, 10, 80

    table(wb.create_sheet("All terms"), rows)
    for d in sorted(domains):
        table(wb.create_sheet(re.sub(r"[\[\]\\*?:/]", "-", d)[:31]), domains[d])
    wb.save(path)
    return path, len(rows)


# ------------------------------------------------------------------ 2. what this computer learned
def candidates(glossary, shared_path=SHARED_CSV):
    """Entries in this computer's glossary that are worth proposing to the shared list."""
    have = known_keys(shared_path)
    out = []
    for k, e in sorted(glossary.entries.items()):
        text = (e.get("definition") or "").strip()
        src = e.get("source")
        if not text or src not in ("manual", "web", "ai") or k in have:
            continue
        if src == "ai" and e.get("note"):
            note = "AI sentence was marked 'Check': " + e["note"]
        else:
            note = ""
        came = {"manual": "Written by a person (glossary document / my_definitions.csv)",
                "web": "Found online: " + (e.get("origin") or "") + (" " + e["url"] if e.get("url") else ""),
                "ai": "AI draft: " + (e.get("origin") or "")}[src]
        out.append({"Approve (Y/N)": "", "Term": e.get("term") or k, "Domain": e.get("category") or "", "Definition": text,
                    "Where it came from": came, "Notes for the reviewer": note})
    return out


def export_candidates(glossary, out_path, shared_path=SHARED_CSV):
    rows = candidates(glossary, shared_path)
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CAND_COLS)
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def merge_candidates(csv_path, shared_path=SHARED_CSV, today=None):
    """Append the rows marked Y. -> (added, skipped_already_known, skipped_unfinished)."""
    today = today or date.today().strftime("%d/%m/%Y")
    have = known_keys(shared_path)
    new, known, unfinished = [], 0, 0
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if not (r.get("Approve (Y/N)") or "").strip().lower().startswith("y"):
                continue
            term, text = (r.get("Term") or "").strip(), (r.get("Definition") or "").strip()
            if not term or not text:
                unfinished += 1
                continue
            k = _norm(term)
            if k in have:
                known += 1
                continue
            have.add(k)
            came = (r.get("Where it came from") or "").split(":")[0].strip() or "Reviewed addition"
            new.append({"Term": term, "Also known as": "", "Domain": (r.get("Domain") or "").strip() or "General", "Better": "",
                        "Definition": text, "Source": "Reviewed addition (" + came + ")", "Added": today})
    if new:
        p = Path(shared_path)
        fresh = not p.exists() or not p.read_text(encoding="utf-8-sig").strip()
        with open(p, "a", newline="", encoding="utf-8-sig" if fresh else "utf-8") as f:
            w = csv.DictWriter(f, fieldnames=SHARED_COLS)
            if fresh:
                w.writeheader()
            w.writerows(new)
    return len(new), known, unfinished
