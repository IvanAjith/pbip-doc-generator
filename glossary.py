"""
glossary.py -- definitions for the terms a report uses.

Where a definition comes from, in priority order:

  1. glossary/glossary.json, entries marked "manual" -- yours; always wins.
  2. The small built-in seed list (seed_glossary.py) -- exact term matches only.
  3. glossary/glossary.json, entries found online earlier -- reused on re-runs.
  4. A fresh web lookup (web_lookup.py) -- saved to glossary.json as
     "web", unverified, with its source URL.
  5. Nothing -- the term is saved to glossary.json with an empty definition so
     you can fill it in; the manual then says only what the DAX proves.

Matching is exact on the normalised name ("Gemba Completion %" ->
"gemba completion"), never by substring, so "Net Revenue per DL Hour" can
not borrow the definition of "Net Revenue".
"""
import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path

from seed_glossary import SEED
from formula_draft import formula_draft, ORIGIN as ORIGIN_DRAFT

_UNIT_TOKENS = {"pct", "percent", "percentage", "ratio"}
WEB_VERSION = 2
CSV_NAME = "my_definitions.csv"
CSV_COLS = ["Term", "Your definition (type here)", "Suggested definition", "Where the suggestion came from", "Page", "Report formula (for reference)"]


def normalize(term: str) -> str:
    t = re.sub(r"\([^)]*\)", " ", term or "")       # drop "(12M)", "(overview)"
    t = t.replace("%", " ")
    words = [w for w in re.findall(r"[a-z0-9]+", t.lower()) if w not in _UNIT_TOKENS]
    return " ".join(words)


@dataclass
class Definition:
    text: str
    source: str            # 'manual' | 'seed' | 'web' | 'ai' | 'draft'
    origin: str = ""       # e.g. "Wikipedia - Total recordable incident rate"
    url: str = ""
    category: str = ""
    better: str = None     # general convention; glossary document only

    @property
    def verified(self):
        return self.source in ("manual", "seed")


class Glossary:
    def __init__(self, path, web=None, ai=None):
        self.path = Path(path)
        self.web = web
        self.ai = ai
        self.used = {}                     # key -> {"term", "page"}; terms this run actually needed
        self.entries = {}                  # normalised key -> dict
        self.generated = {}                # key -> the "What it means" text written into the glossary document last time
        self.word_edits = 0
        self.dirty = False
        self.unresolved = []
        if self.path.exists():
            try:
                _j = json.loads(self.path.read_text(encoding="utf-8-sig"))
                self.entries = _j.get("terms", {})
                self.generated = _j.get("generated", {})
            except Exception:
                self.entries = {}
            for k, e in list(self.entries.items()):       # web matches saved by older versions were unreliable
                if e.get("source") == "web" and e.get("wv") != WEB_VERSION:
                    self.entries[k] = {"term": e.get("term", k), "definition": "", "source": "unresolved"}
                    self.dirty = True
        self.csv_path = self.path.parent / CSV_NAME
        self._csv_extra = {}               # user rows for terms not used in this run (kept when the file is rewritten)
        self._load_csv()
        self._seed = {}
        for e in SEED:
            for t in e["terms"]:
                self._seed[normalize(t)] = e

    # -------------------------------------------------------------- lookup
    def lookup(self, *names, **kw):
        d = self._lookup(*names, **kw)
        keys = [normalize(n or "") for n in names if normalize(n or "")]
        if keys and keys[0] in self.used:
            self.used[keys[0]]["def"] = d
        return d

    def _lookup(self, *names, context=(), web=True, web_names=None, ai_context=None, draft=None):
        """Try each candidate name (e.g. card label, then measure name)."""
        keys = []
        for n in names:
            k = normalize(n or "")
            if k and k not in keys:
                keys.append(k)
        if not keys:
            return None
        ctx = list(context)
        self.used.setdefault(keys[0], {"term": names[0], "page": (ctx or [""])[0], "calc": ctx[1] if len(ctx) > 1 else ""})
        for k in keys:                                    # 1. manual
            e = self.entries.get(k)
            if e and e.get("source") == "manual" and e.get("definition"):
                return self._from_entry(e)
        for k in keys:                                    # 2. seed
            if k in self._seed:
                s = self._seed[k]
                return Definition(s["definition"], "seed", "built-in glossary",
                                  category=s.get("category", ""), better=s.get("better"))
        for k in keys:                                    # 3. learned earlier
            e = self.entries.get(k)
            if e and e.get("definition"):
                return self._from_entry(e)
        if self.web is not None and web:                  # 4. web
            for n in (web_names if web_names is not None else names):
                if not n:
                    continue
                r = self.web.define(n, context)
                if r:
                    k = normalize(n)
                    self.entries[k] = {"term": n, "definition": r["text"], "source": "web",
                                       "origin": r["source"], "url": r["url"], "verified": False,
                                       "wv": WEB_VERSION}
                    self.dirty = True
                    return self._from_entry(self.entries[k])
        if self.ai is not None and ai_context is not None:   # 5. AI draft (optional, clearly labelled)
            r = self.ai.draft(names[0], **ai_context)
            if r:
                k = keys[0]
                self.entries[k] = {"term": names[0], "definition": r["text"], "source": "ai",
                                   "origin": r["origin"], "url": "", "verified": False, "wv": WEB_VERSION}
                self.dirty = True
                return self._from_entry(self.entries[k])
        if draft:                                         # 6. draft rephrased from the report's own formula (offline)
            text = formula_draft(draft.get("calc"), draft.get("unit"), draft.get("inputs"))
            if text:
                return Definition(text, "draft", ORIGIN_DRAFT)
        k = keys[0]                                       # 7. unresolved placeholder
        if k not in self.entries:
            self.entries[k] = {"term": names[0], "definition": "", "source": "unresolved"}
            self.dirty = True
        if names[0] not in self.unresolved:
            self.unresolved.append(names[0])
        return None

    # -------------------------------------------------------------- edits made in the glossary document
    @staticmethod
    def _clean(t):
        return re.sub(r"\s+", " ", t or "").strip()

    def record_generated(self, key, text):
        """Remember what the glossary document said for this row, so a later change can be recognised as an edit."""
        if self.generated.get(key) != text:
            self.generated[key] = text
            self.dirty = True

    def absorb_word_edits(self, docx_path, needs_mark="\u26A0"):
        """Read the glossary document written by the previous run. Any 'What it means' cell that now differs from what
        the tool wrote is the user's own definition: keep it as a manual entry."""
        path = Path(docx_path)
        if not path.exists() or not self.generated:
            return 0
        try:
            from docx import Document
            doc = Document(str(path))
        except Exception:
            return 0
        n = 0
        for t in doc.tables:
            head = [self._clean(c.text) for c in t.rows[0].cells] if t.rows else []
            if len(head) < 2 or head[0] not in ("Indicator", "Measure") or head[1] != "What it means":
                continue
            for r in t.rows[1:]:
                term = self._clean(r.cells[0].text)
                text = self._clean(r.cells[1].text)
                k = normalize(term) or term.lower()
                was = self.generated.get(k)
                if was is None or not text or text == "\u2014" or text.startswith(needs_mark) or text == self._clean(was):
                    continue
                self.entries[k] = {"term": term, "definition": text, "source": "manual", "from_word": True}
                if k in self._csv_extra:
                    self._csv_extra[k]["mine"] = text
                self.generated[k] = text
                self.dirty = True
                n += 1
        self.word_edits = n
        return n

    def _load_csv(self):
        if not self.csv_path.exists():
            return
        try:
            with open(self.csv_path, newline="", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    term = (row.get("Term") or "").strip()
                    mine = (row.get(CSV_COLS[1]) or "").strip()
                    if mine.lower() in ("ok", "okay", "accept", "yes", "y", "agree"):   # "ok" = keep the suggestion
                        mine = (row.get(CSV_COLS[2]) or "").strip()
                    if not term or not mine:
                        continue
                    k = normalize(term)
                    self.entries[k] = {"term": term, "definition": mine, "source": "manual", "from_csv": True}
                    self._csv_extra[k] = {"term": term, "mine": mine, "page": row.get("Page", "")}
        except Exception:
            pass

    def _write_csv(self):
        rows, done = [], set()
        for k, u in self.used.items():
            d = u.get("def")
            mine = d.text if d and d.source == "manual" else ""
            sugg = d.text if d and d.source != "manual" else ""
            origin = {"web": "Web: " + (d.origin if d else ""), "ai": (d.origin if d else "AI draft"),
                      "seed": "Built-in glossary", "draft": "Draft built from the formula"}.get(d.source if d else "", "")
            rows.append([u["term"], mine, sugg, origin if sugg else "", u["page"], u.get("calc", "")])
            done.add(k)
        for k, u in self._csv_extra.items():              # keep what you typed for terms this report doesn't use
            if k not in done:
                rows.append([u["term"], u["mine"], "", "", u.get("page", ""), ""])
        rows.sort(key=lambda r: (bool(r[1]), bool(r[2]), r[0].lower()))   # blank terms first, then suggestions, then done
        try:
            with open(self.csv_path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(CSV_COLS)
                w.writerows(rows)
        except PermissionError:
            print(f"  (could not write {self.csv_path.name} -- is it open in Excel? Close it and run again.)")

    @staticmethod
    def _from_entry(e):
        return Definition(e["definition"], e.get("source", "manual"), e.get("origin", ""),
                          e.get("url", ""), e.get("category", ""))

    # -------------------------------------------------------------- persistence
    def save(self):
        self._write_csv()
        if not self.dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "_readme": ("Definitions used by the generated documents. Edit any entry: set \"source\" to "
                        "\"manual\" and write your own \"definition\" -- manual entries always win and are "
                        "never overwritten. Entries with source \"web\" were found online and are unverified; "
                        "entries with source \"unresolved\" have no definition yet."),
            "terms": dict(sorted((k, v) for k, v in self.entries.items() if not v.get("from_csv"))),
            "generated": self.generated,
        }
        self.path.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
        self.dirty = False
