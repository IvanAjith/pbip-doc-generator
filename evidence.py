"""
evidence.py -- facts read straight from the report's own JSON.

  * which pages the navigation buttons point to  -> which pages are "main"
  * which visuals carry conditional formatting   -> colour statements in the manual

Rule for everything in here: report a thing only when the JSON proves it.
Formatting entries that point at a field the visual does not actually
display (a common leftover after copy/paste) are ignored.
"""
import json
import math
import re
from collections import defaultdict
from pathlib import Path

from dax_explain import Explainer, hex_to_name, humanize_column, is_colour_literal

_CMP = {0: "=", 1: ">", 2: "≥", 3: "<", 4: "≤"}


# ---------------------------------------------------------------- helpers

def _lit(node):
    """Literal value of a {'Literal': {'Value': "'abc'"}} node, else None."""
    if not isinstance(node, dict):
        return None
    v = node.get("Literal", {}).get("Value") if "Literal" in node else None
    if v is None:
        return None
    v = str(v)
    if len(v) >= 2 and v[0] == "'" and v[-1] == "'":
        return v[1:-1].replace("''", "'")
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)[DLMdlm]?", v)
    if m:
        f = float(m.group(1))
        return f"{int(f):,}" if f.is_integer() else f"{f:g}"
    if v.lower() in ("true", "false", "null"):
        return v.lower()
    return v


def _field_name(node):
    """Readable name of a Measure / Column / Aggregation node."""
    if not isinstance(node, dict):
        return None
    if "Measure" in node:
        return node["Measure"].get("Property")
    if "Column" in node:
        return humanize_column(node["Column"].get("Property", ""))
    if "Aggregation" in node:
        return _field_name(node["Aggregation"].get("Expression"))
    if "HierarchyLevel" in node:
        return node["HierarchyLevel"].get("Level")
    return None


def _render_condition(c, ex=None):
    """Condition node -> 'Net Sentiment ≥ 0'; None if not understood."""
    if not isinstance(c, dict):
        return None
    if "Comparison" in c:
        cmp = c["Comparison"]
        op = _CMP.get(cmp.get("ComparisonKind"))
        l = _field_name(cmp.get("Left"))
        r = _lit(cmp.get("Right"))
        lm = (cmp.get("Left") or {}).get("Measure")
        if lm and ex is not None and r is not None and re.fullmatch(r"-?\d*\.?\d+", r or ""):
            mm = ex.measures.get(lm.get("Property")) or {}
            if "%" in (mm.get("formatString") or "") and abs(float(r)) <= 10:
                r = f"{float(r) * 100:g}%"
        if op and l and r is not None:
            return f"{l} {op} {r}" if re.fullmatch(r"-?[\d,.]+%?", r) else f"{l} {op} “{r}”"
        return None
    if "And" in c or "Or" in c:
        k = "And" if "And" in c else "Or"
        a, b = _render_condition(c[k].get("Left"), ex), _render_condition(c[k].get("Right"), ex)
        return f"{a} {k.lower()} {b}" if a and b else None
    if "Not" in c:
        inner = _render_condition(c["Not"].get("Expression"), ex)
        return f"not ({inner})" if inner else None
    if "In" in c:
        exprs = c["In"].get("Expressions", [])
        vals = [_lit(v[0]) if isinstance(v, list) and v else None for v in c["In"].get("Values", [])]
        f = _field_name(exprs[0]) if exprs else None
        if f and vals and all(v is not None for v in vals):
            return f"{f} is " + " or ".join(f"“{v}”" for v in vals)
    return None


def _find_expr(o):
    """First {'expr': {...}} found under a property value."""
    if isinstance(o, dict):
        if "expr" in o and isinstance(o["expr"], dict):
            return o["expr"]
        for v in o.values():
            r = _find_expr(v)
            if r:
                return r
    elif isinstance(o, list):
        for v in o:
            r = _find_expr(v)
            if r:
                return r
    return None


def _property_words(obj_name, prop):
    p = prop.lower()
    o = obj_name.lower()
    if "font" in p or (o == "labels" and p == "color"):
        what = "text colour"
    elif "back" in p or "fill" in p:
        what = "background colour"
    elif "line" in p or "outline" in p or "border" in p:
        what = "border colour"
    else:
        what = "colour"
    return what


# ---------------------------------------------------------------- per-visual formatting

def _projections(vobj):
    out = []
    for role, rv in (vobj.get("query", {}).get("queryState", {}) or {}).items():
        for pr in rv.get("projections", []):
            f = pr.get("field", {})
            kind = next(iter(f), None)
            body = f.get(kind, {}) if kind else {}
            prop = body.get("Property") or body.get("Name")
            out.append({
                "queryRef": (pr.get("queryRef") or "").lower(),
                "name": prop,
                "display": pr.get("displayName") or pr.get("nativeQueryRef") or prop,
                "isMeasure": kind == "Measure",
            })
    return out


def visual_format_rules(vobj, explainer: Explainer):
    """Conditional-formatting rules that are provably active on this visual."""
    fields = _projections(vobj)
    refs = {f["queryRef"] for f in fields}
    names = {(f["name"] or "").lower() for f in fields}
    rules = []
    for obj_name, entries in (vobj.get("objects") or {}).items():
        for entry in entries if isinstance(entries, list) else []:
            sel = entry.get("selector") or {}
            meta = (sel.get("metadata") or "").lower()
            target = None
            if meta:
                if meta not in refs:
                    tail = meta.split(".", 1)[-1]
                    if tail not in names:
                        continue                     # stale entry for a field not on this visual
                target = next((f["display"] or f["name"] for f in fields
                               if f["queryRef"] == meta or (f["name"] or "").lower() == meta.split(".", 1)[-1]), None)
            for prop, val in (entry.get("properties") or {}).items():
                pl = prop.lower()
                if not ("color" in pl or "colour" in pl or "fill" in pl or pl == "background"):
                    continue                          # e.g. a button's text *content*, not a colour
                expr = _find_expr(val)
                if not expr:
                    continue
                kind = next(iter(expr))
                what = _property_words(obj_name, prop)
                if kind == "Conditional":
                    cases = []
                    for case in expr["Conditional"].get("Cases", []):
                        cond = _render_condition(case.get("Condition"), explainer)
                        colour = _lit(case.get("Value"))
                        if cond is None or not colour or not is_colour_literal(colour):
                            cases = None
                            break
                        cases.append({"cond": cond, "colour": colour})
                    if cases:
                        rules.append({"kind": "rules", "what": what, "target": target, "cases": cases,
                                      "object": obj_name})
                elif kind == "Measure":
                    mname = expr["Measure"].get("Property")
                    logic = explainer.colour_rules(mname) if explainer and mname else []
                    if logic and len({hex_to_name(r["colour"]) for r in logic}) == 1:
                        continue                      # every branch gives the same colour: no visible effect
                    rules.append({"kind": "measure", "what": what, "target": target, "measure": mname,
                                  "logic": logic, "object": obj_name})
                elif kind == "FillRule":
                    fr = expr["FillRule"]
                    grad = fr.get("FillRule", {})
                    g = grad.get("linearGradient2") or grad.get("linearGradient3") or {}
                    cols = []
                    for end in ("min", "mid", "max"):
                        c = _lit((g.get(end) or {}).get("color"))
                        if c and is_colour_literal(c):
                            cols.append(c)
                    driver = _field_name(fr.get("Input"))
                    if cols and driver:
                        rules.append({"kind": "gradient", "what": what, "target": target, "driver": driver,
                                      "colours": cols, "object": obj_name})
    return rules


def describe_rule(rule):
    """One plain-English sentence for a rule (colour names come from the hex
    values themselves; nothing is said about what a colour 'means')."""
    where = f"the {rule['target']} column’s {rule['what']}" if rule.get("target") else f"the {rule['what']}"
    if rule["kind"] == "rules":
        parts = [f"{hex_to_name(c['colour'])} when {c['cond']}" for c in rule["cases"]]
        return f"{where[0].upper() + where[1:]} turns " + ", ".join(parts[:-1]) + (
            (" and " if len(parts) > 1 else "") + parts[-1]) + "."
    if rule["kind"] == "gradient":
        names = [hex_to_name(c) for c in rule["colours"]]
        return (f"{where[0].upper() + where[1:]} shades from {' to '.join(names)} "
                f"according to {rule['driver']}.")
    if rule["kind"] == "measure":
        logic = rule.get("logic") or []
        head = f"{where[0].upper() + where[1:]} is set by the measure “{rule['measure']}”"
        if logic:
            bits = []
            for r in logic:
                nm = hex_to_name(r["colour"])
                lab = f" ({r['label']})" if r.get("label") else ""
                bits.append(f"{nm}{lab} when {r['cond']}" if r["cond"] else f"{nm}{lab} otherwise")
            return head + ": " + "; ".join(bits) + "."
        return head + "."
    return ""


# ---------------------------------------------------------------- report scan

def scan_report(report_dir: Path, explainer: Explainer):
    """-> {page_id: {'meta': {...}, 'nav': set(page_ids), 'visuals': {vid: {'rules': [...]}}}}"""
    root = report_dir / "definition" / "pages"
    out = {}
    nav_re = re.compile(r'"navigationSection"\s*:\s*\{\s*"expr"\s*:\s*\{\s*"Literal"\s*:\s*\{\s*"Value"\s*:\s*"\'([^\']+)\'"')
    for pdir in sorted(p for p in root.iterdir() if p.is_dir()):
        try:
            pj = json.loads((pdir / "page.json").read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        binding = pj.get("pageBinding") or {}
        entry = {"meta": {"visibility": pj.get("visibility"), "type": pj.get("type") or binding.get("type"),
                          "binding": binding.get("type")},
                 "nav": set(), "visuals": {}, "slicers": [], "bookmarks": []}
        vroot = pdir / "visuals"
        if vroot.exists():
            for vf in sorted(vroot.glob("*/visual.json")):
                try:
                    text = vf.read_text(encoding="utf-8-sig")
                    vj = json.loads(text)
                except Exception:
                    continue
                entry["nav"].update(nav_re.findall(text))
                vobj = vj.get("visual", {})
                if vobj.get("visualType") == "slicer":
                    proj = _projections(vobj)
                    grp = (vobj.get("syncGroup") or vj.get("syncGroup") or {}).get("groupName")
                    field = None
                    for pr in (vobj.get("query", {}).get("queryState", {}) or {}).values():
                        for pp in pr.get("projections", []):
                            f = pp.get("field", {})
                            body = f.get("Column") or f.get("HierarchyLevel") or {}
                            ent = ((body.get("Expression") or {}).get("SourceRef") or {}).get("Entity")
                            if body.get("Property") and ent:
                                field = f"{ent}.{body['Property']}"
                                break
                        if field:
                            break
                    entry["slicers"].append({"field": field, "sync": grp,
                                             "label": (proj[0]["display"] if proj else None)})
                entry["visuals"][vj.get("name")] = {
                    "rules": visual_format_rules(vobj, explainer),
                    "fields": _projections(vobj),
                }
        out[pdir.name] = entry
    # bookmarks, grouped by the page they were saved on
    bdir = report_dir / "definition" / "bookmarks"
    if bdir.exists():
        for bf in sorted(bdir.glob("*.bookmark.json")):
            try:
                bj = json.loads(bf.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            sec = (bj.get("explorationState") or {}).get("activeSection")
            if sec in out and bj.get("displayName"):
                out[sec]["bookmarks"].append(bj["displayName"])
    return out


_FALLBACK_NAME_RE = re.compile(r"\b(test|duplicate|copy of|backup|scratch|temp|draft|wip)\b", re.I)


def classify_pages(pages, evidence, active_page_id):
    """Sets page['nonprodFlag'] to a short reason (or None for a main page)
    and page['mainNav'] to True/False, using the navigation graph:

    * a main page is the landing page, or a page that the navigation
      buttons of at least 40% of the button-bearing pages point at
    * a page reachable only from one or two pages (a drill-in / detail
      view) or from none (scratch) is not a main page

    If the report has no navigation buttons at all, it falls back to page
    visibility and type, then to a short list of obvious scratch names.
    """
    by_id = {p["id"]: p for p in pages}
    sources = {pid: e["nav"] - {pid} for pid, e in evidence.items() if e["nav"] - {pid}}
    indeg = defaultdict(set)
    for src, targets in sources.items():
        for t in targets:
            indeg[t].add(src)

    if sources:
        small = len(sources) <= 3            # a handful of linked pages has no real hierarchy: one link is enough
        thr = 1 if small else max(2, math.ceil(0.4 * len(sources)))
        landing = active_page_id if active_page_id in by_id else (pages[0]["id"] if pages else None)
        def _detail(pid):
            m = evidence.get(pid, {}).get("meta", {})
            return m.get("type") == "Tooltip" or m.get("binding") == "Tooltip"
        def _drill(pid):
            return evidence.get(pid, {}).get("meta", {}).get("binding") == "Drillthrough"
        main = {landing} | {t for t, s in indeg.items()
                            if len(s) >= thr and not _detail(t) and not (small and _drill(t))}
        for p in pages:
            pid = p["id"]
            meta = evidence.get(pid, {}).get("meta", {})
            if pid in main:
                p["nonprodFlag"], p["mainNav"] = None, True
                continue
            p["mainNav"] = False
            if meta.get("type") == "Tooltip" or meta.get("binding") == "Tooltip":
                p["nonprodFlag"] = "tooltip page"
            elif meta.get("binding") == "Drillthrough":
                p["nonprodFlag"] = "drill-through page"
            elif indeg.get(pid):
                names = sorted(by_id[s]["displayName"].strip() for s in indeg[pid] if s in by_id)
                p["nonprodFlag"] = "not in main navigation — linked only from " + ", ".join(names)
            else:
                p["nonprodFlag"] = "not linked from any page"
    else:
        for p in pages:
            meta = evidence.get(p["id"], {}).get("meta", {})
            reason = None
            if meta.get("type") == "Tooltip":
                reason = "tooltip page"
            elif meta.get("binding") == "Drillthrough":
                reason = "drill-through page"
            elif meta.get("visibility") == "HiddenInViewMode":
                reason = "hidden page"
            elif _FALLBACK_NAME_RE.search(p["displayName"]):
                reason = "name suggests a scratch page"
            p["nonprodFlag"], p["mainNav"] = reason, reason is None
    return pages
