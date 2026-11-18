"""clarify.py -- the "Needs your clarification" file.

Every run writes  Needs_Your_Clarification.txt  next to the three documents. It asks, in plain words, for what only a person can supply:
  PART 1  what an abbreviation in a KPI name stands for (CB, EOL ...)
  PART 2  what a KPI means, when no definition could be built or found (and, with --clarify-drafts, to confirm drafts)
You type each answer after ">>>", save, and run the same command again: abbreviations go to context.txt, definitions go into the
glossary file (so the glossary grows), the three documents are rebuilt, and the file comes back saying nothing is needed.
(An older Needs_Your_Clarification.csv from version 1.9 is still read.)
"""
import csv
import re
from pathlib import Path

NAME = "Needs_Your_Clarification.txt"
LEGACY_CSV = "Needs_Your_Clarification.csv"
NONE_TEXT = "No clarification needed"
OK_WORDS = ("ok", "okay", "accept", "yes", "y", "agree")
_SEC = "=" * 8


def _one_line(text):
    return " ".join((text or "").split())


def write(path, project, abbrs, needed, drafts=()):
    """abbrs: [(token, [names])]; needed / drafts: dicts with term, page, calc (+ draft). -> number of questions."""
    n = len(abbrs) + len(needed) + len(drafts)
    L = [f"NEEDS YOUR CLARIFICATION  -  {project}", ""]
    if n == 0:
        L += [NONE_TEXT.upper() + ".", "", "Every KPI has a definition and every abbreviation is explained. The three documents are ready to share.", ""]
        Path(path).write_text("\n".join(L), encoding="utf-8")
        return 0
    L += ["How this works:",
          "  1. Type your answer on the line that starts with  >>>  (a few lines are fine; leave it blank to skip a question).",
          "  2. Save this file, then run the same command again.",
          "  3. Your answers are kept for later runs, the three documents are rebuilt with them, and this file shrinks.",
          "Write for someone who does not know the business: plain, everyday words.", ""]
    i = 0
    if abbrs:
        L += [f"{_SEC} PART 1: WHAT DO THESE ABBREVIATIONS STAND FOR? {_SEC}",
              "They appear in KPI names. Write the full words, for example:   >>> comeback", ""]
        for tok, names in abbrs:
            i += 1
            L += [f"[A{i}] {tok}", "     seen in: " + ", ".join(names[:4]) + (" ..." if len(names) > 4 else ""), ">>> ", ""]
    j = 0
    if needed or drafts:
        L += [f"{_SEC} PART 2: WHAT DOES EACH KPI MEAN? {_SEC}",
              "Say what it measures, in a sentence or two. (How it is calculated is taken from the report's own formula.)", ""]
        for r in needed:
            j += 1
            L += [f"[K{j}] {r['term']}", f"     page: {r.get('page') or '-'}", f"     formula: {_one_line(r.get('calc')) or '-'}",
                  "     No definition was found for this one.", ">>> ", ""]
        for r in drafts:
            j += 1
            L += [f"[K{j}] {r['term']}", f"     page: {r.get('page') or '-'}", f"     formula: {_one_line(r.get('calc')) or '-'}",
                  f"     draft: {_one_line(r.get('draft'))}"] + ([f"     check: {_one_line(r['note'])}"] if r.get("note") else []) + [
                  "     Type OK to keep this draft, or write your own wording.", ">>> ", ""]
    Path(path).write_text("\n".join(L), encoding="utf-8")
    return n


def read(path):
    """-> (abbreviations {TOKEN: meaning}, definitions [(term, text)]). Blank answers are ignored; OK keeps the shown draft."""
    p = Path(path)
    abbr, defs = {}, []
    if p.exists():
        try:
            lines = p.read_text(encoding="utf-8-sig").splitlines()
        except OSError:
            lines = []
        cur, ans, active, draft = None, [], False, ""

        def flush():
            nonlocal cur, ans, active, draft
            if cur:
                text = " ".join(x.strip() for x in ans if x.strip()).strip()
                if text:
                    if cur[0] == "A":
                        abbr[cur[1].upper()] = text
                    else:
                        if text.lower().rstrip(".") in OK_WORDS:
                            text = draft
                        if text:
                            defs.append((cur[1], text))
            cur, ans, active, draft = None, [], False, ""

        for line in lines:
            m = re.match(r"^\[([AK])\d+\]\s+(.+?)\s*$", line)
            if m:
                flush()
                cur = (m.group(1), m.group(2))
                continue
            if line.startswith(_SEC) or line.startswith("NEEDS YOUR"):
                flush()
                continue
            if cur is None:
                continue
            if line.startswith(">>>"):
                active = True
                ans.append(line[3:])
            elif active:
                ans.append(line)
            else:
                d = re.match(r"^\s+draft:\s*(.*)$", line)
                if d:
                    draft = d.group(1).strip()
        flush()
    legacy = p.with_name(LEGACY_CSV)
    if legacy.exists():
        try:
            with open(legacy, newline="", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    term = (row.get("Term") or "").strip()
                    mine = (row.get("Your definition (type here)") or "").strip()
                    if not term or not mine or term == NONE_TEXT:
                        continue
                    if mine.lower() in OK_WORDS:
                        mine = (row.get("Draft (for your information)") or "").strip()
                    if mine:
                        defs.append((term, mine))
        except Exception:
            pass
    return abbr, defs
