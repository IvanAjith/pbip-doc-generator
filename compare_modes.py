"""compare_modes.py -- put two runs side by side (for example offline vs AI).

  python run.py --compare-glossaries gl_offline gl_ai [FILE.xlsx]

Each folder is the glossary folder of one run (it holds my_definitions.csv). The result is an Excel file with
  Summary         how many definitions came from where in each run, and how many changed
  Changed         only the terms whose definition differs, side by side
  All terms       every term, side by side
"""
import csv
from collections import Counter
from pathlib import Path

CSV_NAME = "my_definitions.csv"


def _kind(origin, text):
    o = (origin or "").lower()
    if not text:
        return "Needs your definition"
    if o.startswith("built-in") or o.startswith("shared"):
        return "Built-in glossary"
    if "formula" in o:
        return "Draft from the formula"
    if o.startswith("web"):
        return "Web"
    if "ai" in o:
        return "AI draft"
    return "Your own" if not o else origin


def read_run(folder):
    p = Path(folder)
    p = p / CSV_NAME if p.is_dir() else p
    if not p.exists():
        raise SystemExit(f"Cannot find {p}. Run the tool with --glossary {Path(folder)}\\glossary.json first.")
    rows = {}
    with open(p, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            term = (r.get("Term") or "").strip()
            if not term:
                continue
            mine = (r.get("Your definition (type here)") or "").strip()
            sugg = (r.get("Suggested definition") or "").strip()
            origin = (r.get("Where the suggestion came from") or "").strip()
            text = mine or sugg
            rows[term.lower()] = {"term": term, "text": text, "kind": "Your own" if mine else _kind(origin, text),
                                  "origin": origin, "page": r.get("Page", ""), "calc": r.get("Report formula (for reference)", "")}
    return rows


def compare(a_folder, b_folder, a_name="Offline", b_name="AI"):
    a, b = read_run(a_folder), read_run(b_folder)
    out = []
    for k in sorted(set(a) | set(b)):
        x = a.get(k) or {"term": b[k]["term"], "text": "", "kind": "(not in this run)", "origin": "", "page": "", "calc": ""}
        y = b.get(k) or {"term": a[k]["term"], "text": "", "kind": "(not in this run)", "origin": "", "page": "", "calc": ""}
        same = x["text"].strip() == y["text"].strip()
        out.append({"term": x["term"], "page": x["page"] or y["page"], "formula": x["calc"] or y["calc"],
                    "a_kind": x["kind"], "a_text": x["text"], "b_kind": y["kind"], "b_text": y["text"], "same": same})
    return out, Counter(r["a_kind"] for r in out), Counter(r["b_kind"] for r in out)


def write(a_folder, b_folder, path="Offline_vs_AI.xlsx", a_name="Offline", b_name="AI"):
    rows, ca, cb = compare(a_folder, b_folder, a_name, b_name)
    changed = [r for r in rows if not r["same"]]
    kinds = sorted(set(ca) | set(cb))
    summary = [("Terms compared", len(rows), ""), ("Same definition in both runs", len(rows) - len(changed), ""),
               ("Different definition", len(changed), "")]
    summary += [(f"Source: {k}", ca.get(k, 0), cb.get(k, 0)) for k in kinds]
    head = ["Term", "Page", f"{a_name} source", f"{a_name} definition", f"{b_name} source", f"{b_name} definition", "Same?"]

    def line(r):
        return [r["term"], r["page"], r["a_kind"], r["a_text"], r["b_kind"], r["b_text"], "yes" if r["same"] else "NO"]

    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
    except ImportError:
        path = str(Path(path).with_suffix(".csv"))
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f); w.writerow(head); w.writerows(line(r) for r in rows)
        return path, len(rows), len(changed)
    wb = Workbook()
    ws = wb.active; ws.title = "Summary"
    ws.append(["", a_name, b_name]); ws.append(["Terms compared", len(rows)]); ws.append(["Same definition in both runs", len(rows) - len(changed)])
    ws.append(["Different definition", len(changed)]); ws.append([])
    ws.append(["Where the definition came from", a_name, b_name])
    for k in kinds:
        ws.append([k, ca.get(k, 0), cb.get(k, 0)])
    for c in ws[1] + ws[6]:
        c.font = Font(bold=True)
    ws.column_dimensions["A"].width = 36; ws.column_dimensions["B"].width = 14; ws.column_dimensions["C"].width = 14
    for title, data in (("Changed", changed), ("All terms", rows)):
        s = wb.create_sheet(title)
        s.append(head)
        for c in s[1]:
            c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="1F4E79")
        for r in data:
            s.append(line(r))
        for col, w in zip("ABCDEFG", (28, 18, 20, 60, 20, 60, 8)):
            s.column_dimensions[col].width = w
        for row in s.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(wrap_text=True, vertical="top")
        s.freeze_panes = "A2"; s.auto_filter.ref = s.dimensions
    wb.save(path)
    return path, len(rows), len(changed)
