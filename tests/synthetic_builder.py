"""Builds small synthetic PBIP projects from other business domains to test the doc generator."""
import json, os, shutil, sys, uuid
from pathlib import Path

def w(path, text):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text, encoding="utf-8")

def lit(v): return {"expr": {"Literal": {"Value": v}}}

def proj_field(entity, prop, measure=False):
    return {"field": {("Measure" if measure else "Column"): {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}},
            "queryRef": f"{entity}.{prop}", "nativeQueryRef": prop}

def nav_button(name, target, label, x):
    return {"name": name, "position": {"x": x, "y": 5, "z": 100, "height": 28, "width": 90, "tabOrder": 100},
            "visual": {"visualType": "actionButton",
                       "objects": {"text": [{"properties": {"show": lit("true")}},
                                            {"properties": {"text": lit(f"'{label}'")}, "selector": {"id": "default"}}]},
                       "visualContainerObjects": {"visualLink": [{"properties": {
                           "show": lit("true"), "type": lit("'PageNavigation'"), "navigationSection": lit(f"'{target}'")}}]}}}

def slicer(name, entity, col, x, sync=None):
    v = {"name": name, "position": {"x": x, "y": 40, "z": 10, "height": 30, "width": 160, "tabOrder": 10},
         "visual": {"visualType": "slicer", "query": {"queryState": {"Values": {"projections": [proj_field(entity, col)]}}},
                    "objects": {"data": [{"properties": {"mode": lit("'Dropdown'")}}]}}}
    if sync: v["syncGroup"] = {"groupName": sync, "fieldChanges": True, "filterChanges": True}
    return v

def card(name, entity, measure, x, y, cond=None):
    v = {"name": name, "position": {"x": x, "y": y, "z": 5, "height": 100, "width": 180, "tabOrder": 5},
         "visual": {"visualType": "card", "query": {"queryState": {"Values": {"projections": [proj_field(entity, measure, True)]}}}}}
    if cond:
        v["visual"]["objects"] = {"labels": [{"properties": {"color": {"solid": {"color": {"expr": cond}}}}}]}
    return v

def case(entity, measure, kind, right, colour):
    return {"Condition": {"Comparison": {"ComparisonKind": kind, "Left": {"Measure": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": measure}},
                                         "Right": {"Literal": {"Value": right}}}}, "Value": {"Literal": {"Value": f"'{colour}'"}}}

def table_visual(name, entity, cols, measures, x, y, cond=None, title=None):
    projs = [proj_field(entity, c) for c in cols]
    projs += [proj_field("_Measures", m, True) for m in measures]
    v = {"name": name, "position": {"x": x, "y": y, "z": 3, "height": 220, "width": 420, "tabOrder": 3},
         "visual": {"visualType": "tableEx", "query": {"queryState": {"Values": {"projections": projs}}}, "objects": {}}}
    if title: v["visual"]["visualContainerObjects"] = {"title": [{"properties": {"text": lit(f"'{title}'")}}]}
    if cond:
        meas, rules = cond
        v["visual"]["objects"]["values"] = [{"properties": {"fontColor": {"solid": {"color": {"expr": {"Conditional": {"Cases": rules}}}}}},
                                             "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": f"_Measures.{meas}"}}]
    return v

def chart(name, entity, cat, measure, x, y, vt="columnChart", title=None):
    v = {"name": name, "position": {"x": x, "y": y, "z": 2, "height": 220, "width": 420, "tabOrder": 2},
         "visual": {"visualType": vt, "query": {"queryState": {"Category": {"projections": [proj_field(entity, cat)]},
                                                               "Y": {"projections": [proj_field("_Measures", measure, True)]}}}}}
    if title: v["visual"]["visualContainerObjects"] = {"title": [{"properties": {"text": lit(f"'{title}'")}}]}
    return v

def build(root, name, source_m, tables, measures, pages, relationships, landing, rls=None):
    root = Path(root); shutil.rmtree(root, ignore_errors=True)
    rep, sm = root / f"{name}.Report", root / f"{name}.SemanticModel"
    w(rep / "definition.pbir", json.dumps({"version": "4.0", "datasetReference": {"byPath": {"path": f"../{name}.SemanticModel"}}}))
    ids = {p["name"]: uuid.uuid4().hex[:20] for p in pages}
    w(rep / "definition/pages/pages.json", json.dumps({"pageOrder": [ids[p["name"]] for p in pages], "activePageName": ids[landing]}))
    w(rep / "definition/report.json", json.dumps({"themeCollection": {"baseTheme": {"name": "CY24"}}}))
    w(rep / "definition/version.json", json.dumps({"version": "2.0.0"}))
    for p in pages:
        pid = ids[p["name"]]
        pj = {"name": pid, "displayName": p["name"], "displayOption": "FitToPage", "height": 720, "width": 1280}
        if p.get("hidden"): pj["visibility"] = "HiddenInViewMode"
        if p.get("drill"): pj["pageBinding"] = {"name": uuid.uuid4().hex[:16], "type": "Drillthrough", "parameters": []}
        if p.get("tooltip"): pj["pageBinding"] = {"name": uuid.uuid4().hex[:16], "type": "Tooltip", "parameters": []}
        w(rep / f"definition/pages/{pid}/page.json", json.dumps(pj))
        vis = []
        x = 10
        for t in p.get("nav", []):
            vis.append(nav_button(f"nav{len(vis)}", ids[t], t, x)); x += 100
        for i, f in enumerate(p.get("filters", [])):
            vis.append(slicer(f"sl{i}", f[0], f[1], 10 + 170 * i, sync=f[2] if len(f) > 2 else None))
        for i, c in enumerate(p.get("cards", [])):
            vis.append(card(f"c{i}", "_Measures", c[0], 10 + 190 * i, 90, cond=c[1] if len(c) > 1 else None))
        for i, t in enumerate(p.get("tables", [])):
            vis.append(table_visual(f"t{i}", *t["args"], **t.get("kw", {})))
        for i, c in enumerate(p.get("charts", [])):
            vis.append(chart(f"ch{i}", *c["args"], **c.get("kw", {})))
        for v in vis:
            w(rep / f"definition/pages/{pid}/visuals/{v['name']}/visual.json", json.dumps(v))
    # semantic model
    w(sm / "definition.pbism", json.dumps({"version": "4.2"}))
    w(sm / "definition/database.tmdl", "database\n\tcompatibilityLevel: 1606\n")
    w(sm / "definition/model.tmdl", "model Model\n\tculture: en-US\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n")
    for t in tables:
        lines = [f"table {t['name']}", f"\tlineageTag: {uuid.uuid4()}", ""]
        for c, dt in t["columns"]:
            q = (lambda n: f"'{n}'" if " " in n else n)
            lines += [f"\tcolumn {q(c)}", f"\t\tdataType: {dt}", f"\t\tlineageTag: {uuid.uuid4()}", "\t\tsummarizeBy: none", f"\t\tsourceColumn: {c}", ""]
        lines += [f"\tpartition {t['name']} = m", "\t\tmode: import", "\t\tsource =", "\t\t\t\tlet"]
        lines += ["\t\t\t\t    " + l for l in source_m(t["name"]).splitlines()]
        lines += ["\t\t\t\tin", "\t\t\t\t    Result", ""]
        w(sm / f"definition/tables/{t['name']}.tmdl", "\n".join(lines))
    lines = ["table _Measures", f"\tlineageTag: {uuid.uuid4()}", ""]
    for m in measures:
        expr = m["expr"].strip("\n")
        lines.append(f"\tmeasure '{m['name']}' =")
        lines += ["\t\t\t" + l for l in expr.splitlines()]
        if m.get("fmt"): lines.append(f"\t\tformatString: {m['fmt']}")
        lines += [f"\t\tlineageTag: {uuid.uuid4()}", ""]
    w(sm / "definition/tables/_Measures.tmdl", "\n".join(lines))
    rel = []
    for a, b in relationships:
        rel += [f"relationship {uuid.uuid4()}", f"\tfromColumn: {a}", f"\ttoColumn: {b}", ""]
    w(sm / "definition/relationships.tmdl", "\n".join(rel))
    if rls:
        w(sm / "definition/roles/Regional.tmdl", rls)
    return ids
