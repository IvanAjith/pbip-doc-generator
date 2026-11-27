"""kpi_document.py -- reads the company's own KPI document (Excel, CSV or Word) that sits next to the report.

The layouts differ from project to project, so nothing here assumes a fixed one:
  * every sheet / table is searched for a header row (a KPI-name column plus a definition and/or calculation column), wherever it is;
    a sheet with no recognisable header is read by its shape (a short distinct name column next to a long text column);
  * sheets that are not KPI lists (cover page, region list, colour codes, worked examples) are skipped and reported;
  * a "Legend" sheet of abbreviations (TP = Time Period) is read as abbreviations.
What comes out is a list of entries (name, aliases, definition, calculation, ...). The document's definition is the company's own
wording, so the glossary uses it before the built-in list; its calculation text is only used to cross-check the report's formula.
"""
import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

SUFFIXES = (".xlsx", ".xlsm", ".csv", ".docx")
UNREADABLE = (".xls", ".doc")

NAME_WORDS = ["key performance indicator", "kpi name", "measure name", "metric name", "indicator name", "kpi", "measure", "metric",
              "indicator", "term", "name"]                                    # most specific first
DEF_WORDS = ["definition", "description", "meaning", "what it", "explanation", "purpose", "what is"]
CALC_WORDS = ["calculation", "formula", "methodology", "logic", "how it is calculated", "computation", "derivation", "dax"]
AREA_WORDS = ["functional area", "area", "category", "channel", "domain", "page", "subject"]
UNIT_WORDS = ["unit of measure", "uom", "unit"]
NOT_A_NAME = {"unit", "uom", "time", "period", "frequency", "comparator", "comparators", "owner", "source", "status", "type", "remark",
              "remarks", "date", "version", "attribute", "existing", "new", "channel", "area", "functional"}

_ABBR = {"avg": "average", "qty": "quantity", "amt": "amount", "cnt": "count", "no": "number", "nos": "number", "pct": "", "vs": "vs"}
_STOP = {"of", "the", "a", "an", "and", "in", "for", "to", "by", "per"}
_GENERIC = {"total", "sum", "count", "value", "selected", "period", "basis", "level", "given", "numbers", "number", "time", "date", "based",
            "using", "from", "till", "with", "that", "this", "each", "which", "where", "when", "into", "than", "then", "also", "only",
            "last", "current", "month", "year", "quarter", "average", "volume", "sales", "same", "also", "taken", "take", "ensure"}


@dataclass
class DocEntry:
    name: str
    aliases: list = field(default_factory=list)
    definition: str = ""
    calc: str = ""
    unit: str = ""
    area: str = ""
    file: str = ""
    sheet: str = ""
    row: int = 0
    used: bool = False             # matched a KPI of the report

    @property
    def where(self):
        return f"{self.file}" + (f" ({self.sheet})" if self.sheet else "")


@dataclass
class DocResult:
    path: Path
    entries: list = field(default_factory=list)
    abbreviations: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)       # one line per sheet / table, for the check file
    skipped: list = field(default_factory=list)
    error: str = ""


# ------------------------------------------------------------------ small helpers
def clean(text):
    t = "" if text is None else str(text)
    return " ".join(t.replace(" ", " ").split())


def tidy_definition(text):
    t = clean(text)
    if not t:
        return ""
    t = t[0].upper() + t[1:]
    return t if t[-1] in ".!?)" else t + "."


def tidy_calc(text):
    t = clean(text)
    return re.sub(r"^=\s*", "", t)


def _words(text):
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _has_word(text, phrase):
    return re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"s?(?![a-z0-9])", (text or "").lower()) is not None


def match_key(name):
    """A spelling-tolerant key for comparing KPI names: '# of Outlets (IDDs)' and 'Number of Outlets' share one."""
    t = (name or "").lower().replace("#", " number ").replace("&", " and ")
    t = re.sub(r"\([^)]*\)", " ", t)
    toks = []
    for w in re.findall(r"[a-z0-9]+", t):
        w = _ABBR.get(w, w)
        if not w or w in _STOP or w in ("ratio", "percent", "percentage"):
            continue
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        toks.append(w)
    return " ".join(sorted(set(toks)))


def _aliases(name):
    out = []
    parts = re.split(r"\s+or\s+|\n\s*or\s*", name or "", flags=re.I)
    if len(parts) > 1:
        out += [clean(p) for p in parts if clean(p)]
    m = re.search(r"\(([A-Z][A-Za-z0-9&]{1,6})\)\s*$", clean(name))
    if m:
        out.append(m.group(1))
    return [a for a in out if a and a != clean(name)]


# ------------------------------------------------------------------ table detection (works on rows of cells, any file type)
def _role(header):
    h = clean(header).lower()
    if not h:
        return None
    if any(_has_word(h, w) for w in DEF_WORDS):
        return "def"
    if any(_has_word(h, w) for w in CALC_WORDS):
        return "calc"
    if any(_has_word(h, w) for w in UNIT_WORDS):
        return "unit"
    if any(_has_word(h, w) for w in AREA_WORDS) and not any(_has_word(h, w) for w in NAME_WORDS[:7]):
        return "area"
    return None


def _name_rank(header):
    h = clean(header).lower()
    if not h or _role(header) in ("def", "calc", "unit"):
        return None
    toks = set(_words(h))
    if toks & NOT_A_NAME and not any(_has_word(h, w) for w in NAME_WORDS[:4]):
        return None
    for i, w in enumerate(NAME_WORDS):
        if _has_word(h, w):
            return i
    return None


def _column(rows, c, start):
    return [clean(r[c]) if c < len(r) else "" for r in rows[start:]]


def _distinct_ratio(vals):
    v = [x.lower() for x in vals if x]
    return len(set(v)) / len(v) if v else 0


def find_header(rows, scan=40):
    """-> (row index, {role: column}) of the first row that has a KPI-name column plus a definition or calculation column."""
    for i, r in enumerate(rows[:scan]):
        cells = [clean(c) for c in r]
        if sum(1 for c in cells if c) < 2:
            continue
        roles = {}
        for c, h in enumerate(cells):
            role = _role(h)
            if role and role not in roles:
                roles[role] = c
        if "def" not in roles and "calc" not in roles:
            continue
        cands = [(rk, -_distinct_ratio(_column(rows, c, i + 1)), c) for c, h in enumerate(cells)
                 if (rk := _name_rank(h)) is not None]
        if not cands:
            continue
        roles["name"] = sorted(cands)[0][2]
        return i, roles
    return None, None


def guess_columns(rows):
    """No header row: a short, distinct text column next to a long text column. -> {'name': c, 'def': c} or None."""
    width = max((len(r) for r in rows), default=0)
    stats = {}
    for c in range(width):
        vals = [clean(r[c]) if c < len(r) else "" for r in rows]
        vals = [v for v in vals if v and not re.fullmatch(r"[\d.,%\-/: ]+", v)]
        if len(vals) >= 3:
            stats[c] = (len(vals), sum(len(v) for v in vals) / len(vals), _distinct_ratio(vals))
    names = [c for c, (n, avg, d) in stats.items() if d >= 0.9 and avg <= 60]
    for nc in names:
        for dc, (n, avg, d) in stats.items():
            if dc > nc and avg >= 35 and avg >= 1.5 * stats[nc][1]:
                both = sum(1 for r in rows if nc < len(r) and dc < len(r) and clean(r[nc]) and clean(r[dc]))
                if both >= 3:
                    return {"name": nc, "def": dc}
    return None


def table_entries(rows, file, sheet):
    """Entries found in one table of rows. -> (entries, note)."""
    rows = [list(r) for r in rows]
    hi, roles = find_header(rows)
    guessed = False
    if roles is None:
        roles = guess_columns(rows)
        if roles is None:
            return [], "no KPI table found"
        hi, guessed = -1, True
    out, header = [], [clean(c) for c in rows[hi]] if hi >= 0 else []
    for off, r in enumerate(rows[hi + 1:]):
        get = lambda role: clean(r[roles[role]]) if role in roles and roles[role] < len(r) else ""
        name = get("name")
        if not name or re.fullmatch(r"[\d.,%\-/: ]+", name) or [clean(c) for c in r] == header:
            continue
        d, calc = get("def"), get("calc")
        out.append(DocEntry(name=name, aliases=_aliases(str(r[roles["name"]]) if roles["name"] < len(r) else name),
                            definition=tidy_definition(d), calc=tidy_calc(calc), unit=get("unit"), area=get("area"),
                            file=file, sheet=sheet, row=hi + 2 + off))
    if not out:
        return [], "no KPI rows found under the header"
    nd, nc = sum(1 for e in out if e.definition), sum(1 for e in out if e.calc)
    where = f"header guessed from the layout" if guessed else f"header on row {hi + 1}"
    return out, f"{len(out)} KPIs ({where}; {nd} with a definition, {nc} with a calculation)"


# ------------------------------------------------------------------ legend sheets (TP = Time Period)
def legend_abbreviations(rows):
    """A sheet that has a cell 'Legend': short token + meaning pairs below it."""
    start = None
    for i, r in enumerate(rows[:15]):
        if any(clean(c).lower() == "legend" for c in r):
            start = i + 1
            break
    out = {}
    if start is None:
        return out
    for r in rows[start:]:
        cells = [clean(c) for c in r if clean(c)]
        if len(cells) >= 2 and re.fullmatch(r"[A-Za-z][A-Za-z0-9&/]{1,7}", cells[0]):
            meaning = re.split(r"\s*\(", cells[1])[0].strip(" -:")
            initials = "".join(w[0] for w in re.findall(r"[A-Za-z]+", meaning)).upper()
            if 2 <= len(meaning) <= 60 and initials[:len(cells[0])] == cells[0].upper():   # TP = Time Period, not BILLING = Primary
                out[cells[0].upper()] = meaning
    return out


# ------------------------------------------------------------------ readers
def _read_xlsx(path, res):
    import openpyxl
    wb = openpyxl.load_workbook(str(path), data_only=True)
    visible, hidden = [], []
    for ws in wb.worksheets:
        (visible if ws.sheet_state == "visible" else hidden).append(ws)
    for group in (visible, hidden):
        if group is hidden and res.entries:                  # the KPI list was found on a visible sheet: hidden sheets are only reported
            for ws in hidden:                                # a hidden legend still explains the abbreviations
                ab = legend_abbreviations([list(r) for r in ws.iter_rows(values_only=True)])
                res.abbreviations.update(ab)
                res.skipped.append(f"'{ws.title}' (hidden sheet" + (f", legend: {len(ab)} abbreviations read)" if ab else ")"))
            break
        for ws in group:
            rows = [list(r) for r in ws.iter_rows(values_only=True)]
            ab = legend_abbreviations(rows)
            if ab:
                res.abbreviations.update(ab)
                res.skipped.append(f"'{ws.title}' (legend: {len(ab)} abbreviations read)")
                continue
            ents, note = table_entries(rows, path.name, ws.title)
            if ents:
                res.entries += ents
                res.notes.append(f"sheet '{ws.title}': {note}")
            else:
                res.skipped.append(f"'{ws.title}' ({note}" + (", hidden" if group is hidden else "") + ")")


def _read_csv(path, res):
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    try:
        dialect = csv.Sniffer().sniff(text[:4000], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(text.splitlines(), dialect))
    ents, note = table_entries(rows, path.name, "")
    if ents:
        res.entries += ents
        res.notes.append(f"{note}")
    else:
        res.skipped.append(f"{path.name} ({note})")


def _read_docx(path, res):
    from docx import Document
    doc = Document(str(path))
    for n, t in enumerate(doc.tables, 1):
        rows = [[c.text for c in r.cells] for r in t.rows]
        ents, note = table_entries(rows, path.name, f"table {n}")
        if ents:
            res.entries += ents
            res.notes.append(f"table {n}: {note}")
        else:
            res.skipped.append(f"table {n} ({note})")
    if res.entries:
        return
    paras = [(p.style.name if p.style is not None else "", clean(p.text)) for p in doc.paragraphs if clean(p.text)]
    heads = [i for i, (s, t) in enumerate(paras) if s.lower().startswith("heading") and len(t) <= 80]
    found = []
    for k, i in enumerate(heads):
        end = heads[k + 1] if k + 1 < len(heads) else len(paras)
        body = " ".join(t for s, t in paras[i + 1:end] if not s.lower().startswith("heading"))
        if body:
            found.append(DocEntry(name=paras[i][1], aliases=_aliases(paras[i][1]), definition=tidy_definition(body),
                                  file=path.name, sheet="headings", row=i + 1))
    if len(found) >= 3:
        res.entries += found
        res.notes.append(f"{len(found)} KPIs read as heading + paragraph")
        return
    found = []
    for i, (s, t) in enumerate(paras):
        m = re.match(r"^([^:–—\-]{2,60}?)\s*(?::|–|—|-)\s+(.{20,})$", t)
        if m and len(m.group(1).split()) <= 8:
            found.append(DocEntry(name=clean(m.group(1)), aliases=_aliases(m.group(1)), definition=tidy_definition(m.group(2)),
                                  file=path.name, sheet="lines", row=i + 1))
    if len(found) >= 3:
        res.entries += found
        res.notes.append(f"{len(found)} KPIs read from 'name: definition' lines")
    else:
        res.skipped.append(f"{path.name} (no KPI table or list found)")


def read_document(path):
    path = Path(path)
    res = DocResult(path)
    try:
        if path.suffix.lower() in (".xlsx", ".xlsm"):
            _read_xlsx(path, res)
        elif path.suffix.lower() == ".csv":
            _read_csv(path, res)
        elif path.suffix.lower() == ".docx":
            _read_docx(path, res)
        else:
            res.error = "format not supported (save it as .xlsx, .docx or .csv)"
    except Exception as e:                                   # an unreadable file must never stop the run
        res.error = f"could not be read ({type(e).__name__}: {e})"
    return res


_SKIP_NAMES = ("needs_your_clarification", "my_definitions", "shared_glossary", "built_in_kpi_glossary", "_kpi_glossary", "_user_manual",
               "_kpi_documentation", "kpi_document_check", "domains_catalog")
_SKIP_DIRS = (".report", ".semanticmodel", ".pbi", "definition", "__pycache__", ".git")


def find_documents(source_dir):
    """KPI documents lying in the source folder (and its sub-folders), outside the Power BI project folders."""
    src = Path(source_dir)
    out, unreadable = [], []
    if not src.is_dir():
        return out, unreadable
    for p in sorted(src.rglob("*")):
        if not p.is_file() or p.name.startswith(("~$", ".")):
            continue
        rel = p.relative_to(src).parts[:-1]
        if any(part.lower().endswith(_SKIP_DIRS) or part.lower() in _SKIP_DIRS for part in rel):
            continue
        if any(s in p.stem.lower() for s in _SKIP_NAMES):
            continue
        if p.suffix.lower() in SUFFIXES:
            out.append(p)
        elif p.suffix.lower() in UNREADABLE:
            unreadable.append(p)
    return out, unreadable


# ------------------------------------------------------------------ the library the glossary asks
class KpiDocument:
    def __init__(self, results=()):
        self.results = list(results)
        self.entries = [e for r in self.results for e in r.entries]
        self._index = {}
        for e in self.entries:                               # an entry with a definition wins over one without
            for n in [e.name] + e.aliases:
                k = match_key(n)
                if not k:
                    continue
                cur = self._index.get(k)
                if cur is None or (e.definition and not cur.definition):
                    self._index[k] = e

    def __bool__(self):
        return bool(self.entries)

    def find(self, name):
        k = match_key(name)
        if not k:
            return None
        e = self._index.get(k)
        if e is not None:
            return e
        toks = set(k.split())
        if len(toks) < 2:
            return None
        best, score = None, 0.0                              # one word apart is still the same KPI ("Billing" vs "Billings %")
        for key, cand in self._index.items():
            ct = set(key.split())
            j = len(toks & ct) / len(toks | ct)
            if j > score:
                best, score = cand, j
        return best if score >= 0.85 else None


# ------------------------------------------------------------------ cross-check with the report's formula
_OPS = [("average", r"\b(average|avg|mean)\b", r"average|divide|/|per\b|divided"),
        ("count", r"\b(count|number of|# of)\b", r"count|distinctcount|countrows|sumx|number of|how many"),
        ("sum", r"\b(sum|total)\b", r"sum|calculate|total|\+|adds?\b")]


def differences(entry, calc_words, dax):
    """Reasons why the document's calculation may not describe the report's formula (empty when nothing stands out)."""
    text = entry.calc
    if not text:
        return []
    facts = f"{calc_words or ''} {dax or ''} {entry.name}".lower()
    out = []
    for label, in_doc, in_formula in _OPS:
        if re.search(in_doc, text.lower()) and not re.search(in_formula, facts):
            out.append(f"the document speaks of {'an ' if label == 'average' else 'a '}{label}, the formula shows none")
    sig = {w for w in _words(text) if len(w) >= 4 and w not in _GENERIC}
    if len(sig) >= 4:
        stems = lambda ws: {w[:5] for w in ws}
        hit = len(stems(sig) & stems(_words(facts))) / len(stems(sig))
        if hit < 0.2:
            out.append("the words of the document's calculation hardly appear in the formula")
    return out


def check(kdoc, used, measure_names, abbrs_added=0):
    """Reconcile the document with the report. used: {key: {term, calc, def, doc}}. -> dict of lists."""
    rep = {"from_doc": [], "calc_only": [], "not_in_doc": [], "not_in_report": [], "differ": []}
    keys_in_report = {match_key(n) for n in measure_names}
    for u in used.values():
        e = u.get("doc")
        d = u.get("def")
        if e is None:
            rep["not_in_doc"].append(u["term"])
            continue
        e.used = True
        if d is not None and d.origin.startswith("KPI document"):
            rep["from_doc"].append(u["term"])
        elif not e.definition:
            rep["calc_only"].append((u["term"], d.origin if d is not None and d.origin else (d.source if d is not None else "")))
        diff = differences(e, u.get("calc", ""), u.get("dax", ""))
        if diff:
            rep["differ"].append((u["term"], e, diff))
    for e in kdoc.entries:
        if not e.used and match_key(e.name) not in keys_in_report and not any(match_key(a) in keys_in_report for a in e.aliases):
            rep["not_in_report"].append(e)
    return rep


def write_check(path, project, kdoc, rep, unreadable=()):
    L = [f"KPI DOCUMENT CHECK  -  {project}", ""]
    L.append("Documents read:")
    for r in kdoc.results:
        L.append(f"  {r.path.name}" + (f"   -- {r.error}" if r.error else ""))
        L += [f"     {n}" for n in r.notes]
        L += [f"     skipped: {s}" for s in r.skipped]
        if r.abbreviations:
            L.append(f"     abbreviations read from its legend: " + ", ".join(f"{k} = {v}" for k, v in list(r.abbreviations.items())[:8]))
    for p in unreadable:
        L.append(f"  {p.name}   -- not read: save it as .xlsx / .docx / .csv")
    L += ["", "What happened:",
          f"  {len(rep['from_doc'])} definition(s) in the glossary come from the KPI document.",
          f"  {len(rep['calc_only'])} KPI(s) are in the document with a calculation but no definition; their definition came from the other sources.",
          f"  {len(rep['not_in_doc'])} KPI(s) of the report are not in the document.",
          f"  {len(rep['not_in_report'])} KPI(s) of the document were not found in the report.",
          f"  {len(rep['differ'])} KPI(s) where the document's calculation may not match the report's formula: please verify.", ""]
    if rep["differ"]:
        L.append("PLEASE VERIFY - the document and the formula may disagree:")
        for term, e, why in rep["differ"]:
            L += [f"  - {term}", f"      document ({e.where}, row {e.row}): {e.calc[:300]}", f"      why flagged: {'; '.join(why)}"]
        L.append("")
    if rep["not_in_doc"]:
        L += ["In the report but not in the KPI document:"] + [f"  - {t}" for t in sorted(set(rep["not_in_doc"]))] + [""]
    if rep["not_in_report"]:
        L += ["In the KPI document but not found in the report (planned, renamed, or removed?):"]
        L += [f"  - {e.name}" + (f"   [{e.area}]" if e.area else "") for e in rep["not_in_report"]] + [""]
    if rep["calc_only"]:
        L += ["In the document with a calculation but no definition (definition from another source):"]
        L += [f"  - {t}   <- {o}" for t, o in rep["calc_only"]] + [""]
    Path(path).write_text("\n".join(L), encoding="utf-8")
