"""clarify.py -- the "Needs your clarification" file.

Every run writes  Needs_Your_Clarification.csv  next to the three documents. It lists the indicators the tool could not define
(the yellow cells in the glossary) -- or, with --clarify-drafts, also every draft that still needs a person to confirm it.
You type the meaning in the last column and run the same command again: the answers are stored in the glossary file, the three
documents are rebuilt with them, and the file comes back empty ("No clarification needed").
"""
import csv
from pathlib import Path

NAME = "Needs_Your_Clarification.csv"
COLS = ["Term", "Page", "Why we are asking", "Report formula (for reference)", "Draft (for your information)",
        "Your definition (type here)"]
NONE_TEXT = "No clarification needed"
OK_WORDS = ("ok", "okay", "accept", "yes", "y", "agree")


def write(path, needed, drafts=()):
    """needed / drafts: lists of dicts with term, page, calc and (for drafts) draft. Returns the number of rows written."""
    rows = []
    for r in needed:
        rows.append([r["term"], r.get("page", ""), "No definition found - please write one", r.get("calc", ""), "", ""])
    for r in drafts:
        rows.append([r["term"], r.get("page", ""), "Draft - type ok to accept it, or write your own wording",
                     r.get("calc", ""), r.get("draft", ""), ""])
    if not rows:
        rows = [[NONE_TEXT, "", "All definitions are in place. The three documents are ready to share.", "", "", ""]]
        count = 0
    else:
        count = len(rows)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(COLS)
        w.writerows(rows)
    return count


def read(path):
    """-> list of (term, definition). 'ok' keeps the draft shown on that row. Rows left blank are ignored."""
    p = Path(path)
    if not p.exists():
        return []
    out = []
    try:
        with open(p, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                term = (row.get(COLS[0]) or "").strip()
                mine = (row.get(COLS[5]) or "").strip()
                if not term or not mine or term == NONE_TEXT:
                    continue
                if mine.lower() in OK_WORDS:
                    mine = (row.get(COLS[4]) or "").strip()
                    if not mine:
                        continue
                out.append((term, mine))
    except Exception:
        return []
    return out
