"""design_language.py -- reads how a report LOOKS, so the User Manual can record its design language.

Everything comes from the report's own files; nothing is guessed and nothing is sent anywhere:
  * the theme      report.json -> themeCollection / resourcePackages, and the theme .json files under StaticResources
                   (data colours, background / foreground, good / neutral / bad, text classes, default card style)
  * the canvas     each page.json: width, height, fit option, page and wallpaper colours
  * the visuals    every visual.json: colours typed into a visual (title, background, border, data points ...), fonts,
                   font sizes, corner radius, shadow, padding, whether the title and header icons are shown, and the
                   spacing between neighbouring visuals
  * HTML visuals   colours, fonts, sizes and radii written inside measures that return HTML (many reports keep their
                   look there instead of in the theme)
A colour that a rule or a measure chooses (conditional formatting) is only counted, not listed: those rules are
described under "Value & Display Conventions" in the manual.

collect(report_dir, pages, measures) -> dict (see the end of this file); it never raises.
"""
import json
import re
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path

from dax_explain import hex_to_name

HEX_RE = re.compile(r"#(?:[0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b")
THEME_COLOUR_KEYS = ("background", "secondaryBackground", "foreground", "tableAccent", "good", "neutral", "bad",
                     "minimum", "center", "maximum")
ELEMENT_LABEL = {"title": "Visual titles", "subTitle": "Visual subtitles", "labels": "Data labels and card numbers",
                 "values": "Table and matrix values", "categoryAxis": "Category axis labels", "valueAxis": "Value axis labels",
                 "legend": "Legends", "columnHeaders": "Table column headers", "rowHeaders": "Matrix row headers",
                 "text": "Button and text-box text", "general": "General text"}
ROLE = {("title", "fontColor"): "visual title text", ("subTitle", "fontColor"): "subtitle text",
        ("background", "color"): "visual background", ("border", "color"): "visual border", ("dropShadow", "color"): "shadow",
        ("dataPoint", "fill"): "bars, lines and slices", ("labels", "color"): "data labels and card numbers",
        ("values", "fontColor"): "table and matrix values", ("values", "backColor"): "table and matrix value background",
        ("columnHeaders", "fontColor"): "table header text", ("columnHeaders", "backColor"): "table header background",
        ("fill", "fillColor"): "button or shape fill", ("outline", "lineColor"): "button or shape outline",
        ("categoryAxis", "labelColor"): "axis labels", ("valueAxis", "labelColor"): "axis labels",
        ("legend", "labelColor"): "legend text", ("divider", "color"): "divider line",
        ("grid", "gridVerticalColor"): "table grid lines", ("grid", "gridHorizontalColor"): "table grid lines"}
CONTAINER_OBJECTS = ("title", "subTitle", "background", "border", "dropShadow", "visualHeader", "padding", "divider")
SIZE_PROPS = {"fontsize", "labelfontsize", "titlefontsize", "textsize"}


# ---------------------------------------------------------------- small readers

def _load(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}


def _norm_hex(h):
    h = h.strip().upper()
    if len(h) == 4:
        h = "#" + "".join(c * 2 for c in h[1:])
    return h


def _lit(node):
    """The literal value of a PBIR property: 'Segoe UI' -> Segoe UI, 12D -> 12, true -> True; None if it is not a literal."""
    try:
        v = node["expr"]["Literal"]["Value"]
    except (KeyError, TypeError):
        return None
    if not isinstance(v, str):
        return v
    if len(v) >= 2 and v[0] == "'" and v[-1] == "'":
        return v[1:-1].replace("''", "'")
    if v in ("true", "false"):
        return v == "true"
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)[DLM]?", v)
    if m:
        f = float(m.group(1))
        return int(f) if f == int(f) else f
    return v


def _colour(node):
    """('hex', '#RRGGBB') | ('theme', ColorId, Percent) | ('rule',) | None for a PBIR colour property."""
    if not isinstance(node, (dict, list)):
        return None
    stack = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, dict):
            if "ThemeDataColor" in n and isinstance(n["ThemeDataColor"], dict):
                t = n["ThemeDataColor"]
                return ("theme", t.get("ColorId"), t.get("Percent", 0))
            lit = n.get("Literal")
            if isinstance(lit, dict) and isinstance(lit.get("Value"), str):
                m = HEX_RE.search(lit["Value"])
                if m:
                    return ("hex", _norm_hex(m.group(0)))
            if any(k in n for k in ("FillRule", "Conditional", "Measure", "Aggregation")):
                return ("rule",)
            stack.extend(n.values())
        elif isinstance(n, list):
            stack.extend(n)
    return None


def _hex_in(node):
    """First #hex colour anywhere inside a theme-file value (a string, or {'solid': {'color': '#fff'}})."""
    if isinstance(node, str):
        m = HEX_RE.fullmatch(node.strip())
        return _norm_hex(node) if m else None
    if isinstance(node, dict):
        for v in node.values():
            h = _hex_in(v)
            if h:
                return h
    if isinstance(node, list):
        for v in node:
            h = _hex_in(v)
            if h:
                return h
    return None


def name_of(h):
    """A plain colour name. Greys and off-whites are split by lightness (hex_to_name calls every pale grey white)."""
    c = h.lstrip("#")
    r, g, b = (int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    if max(r, g, b) - min(r, g, b) < 0.06:
        l = (max(r, g, b) + min(r, g, b)) / 2
        return "white" if l > 0.97 else "light grey" if l > 0.8 else "black" if l < 0.15 else "dark grey" if l < 0.3 else "grey"
    return hex_to_name(h)


def _words(s):
    return re.sub(r"(?<!^)(?=[A-Z])", " ", s).lower().replace("color", "colour")


def _role(obj, prop):
    return ROLE.get((obj, prop)) or f"{_words(obj)} {_words(prop)}".replace("font colour", "text colour")


def _props(objects):
    for oname, arr in (objects or {}).items():
        if not isinstance(arr, list):
            continue
        for entry in arr:
            if isinstance(entry, dict):
                for pname, val in (entry.get("properties") or {}).items():
                    yield oname, pname, val


def _top(counter, n=1):
    return [k for k, _ in counter.most_common(n)]


# ---------------------------------------------------------------- the theme

def _theme_file(d):
    out = {"name": d.get("name"), "data": [], "colours": OrderedDict(), "text": [], "defaults": OrderedDict(), "overrides": 0}
    out["data"] = [h for h in (_hex_in(c) for c in d.get("dataColors") or []) if h]
    for k in THEME_COLOUR_KEYS:
        h = _hex_in(d.get(k))
        if h:
            out["colours"][k] = h
    for cls, v in (d.get("textClasses") or {}).items():
        if isinstance(v, dict) and (v.get("fontFace") or v.get("fontSize")):
            out["text"].append({"class": cls, "font": v.get("fontFace"), "size": v.get("fontSize"), "colour": _hex_in(v.get("color"))})
    vs = d.get("visualStyles") or {}
    star = (vs.get("*") or {}).get("*") or {}
    for obj in ("background", "border", "title", "dropShadow", "subTitle", "visualHeader"):
        arr = star.get(obj)
        e = arr[0] if isinstance(arr, list) and arr and isinstance(arr[0], dict) else None
        if not e:
            continue
        info = {}
        for k, v in e.items():
            if k in ("color", "fontColor", "background", "backColor"):
                h = _hex_in(v)
                if h:
                    info[k] = h
            elif isinstance(v, (str, int, float, bool)):
                info[k] = v
        if info:
            out["defaults"][obj] = info
    out["overrides"] = len([k for k in vs if k != "*"])
    return out


def _theme(report_dir):
    rep = _load(Path(report_dir) / "definition" / "report.json")
    tc = rep.get("themeCollection") or {}
    base = (tc.get("baseTheme") or {}).get("name")
    custom = (tc.get("customTheme") or {}).get("name")
    files, images = [], []
    for pk in rep.get("resourcePackages") or []:
        pname = pk.get("name") or pk.get("type") or ""
        for it in pk.get("items") or []:
            if it.get("type") in ("BaseTheme", "CustomTheme"):
                files.append((it["type"], Path(report_dir) / "StaticResources" / pname / (it.get("path") or "")))
            elif it.get("type") == "Image" and it.get("name"):
                images.append(it["name"])
    sr = Path(report_dir) / "StaticResources"
    if not files and sr.exists():
        for f in sorted(sr.rglob("*.json")):
            files.append(("BaseTheme" if "BaseThemes" in f.parts else "CustomTheme", f))
    custom_d = base_d = None
    for kind, f in files:
        d = _load(f)
        if not d:
            continue
        if kind == "CustomTheme" and custom_d is None:
            custom_d = _theme_file(d)
            custom_d["file"] = f.name
        elif kind == "BaseTheme" and base_d is None:
            base_d = _theme_file(d)
            base_d["file"] = f.name
    return {"base": base or (base_d or {}).get("name"), "custom": custom or (custom_d or {}).get("name"),
            "custom_file": custom_d, "base_file": base_d, "images": images}


# ---------------------------------------------------------------- HTML written inside measures

def _html_design(measures):
    cols, fonts, sizes, radii = Counter(), Counter(), Counter(), Counter()
    n = shadows = 0
    for m in measures or []:
        e = m.get("expression") or ""
        if not re.search(r"<\s*(?:div|span|table|style|td|svg|p)\b", e, re.I):
            continue
        n += 1
        cols.update({_norm_hex(h) for h in HEX_RE.findall(e)})
        fonts.update({re.split(r",", f)[0].strip(" '\"\\") for f in re.findall(r"font-family\s*:\s*([^;\"<>}]+)", e, re.I)} - {""})
        sizes.update({a + b.lower() for a, b in re.findall(r"font-size\s*:\s*(\d+(?:\.\d+)?)\s*(px|pt|em|rem|%)", e, re.I)})
        radii.update({a + b.lower() for a, b in re.findall(r"border-radius\s*:\s*(\d+(?:\.\d+)?)\s*(px|em|rem|%)", e, re.I)})
        shadows += 1 if re.search(r"box-shadow\s*:", e, re.I) else 0
    return {"measures": n, "colours": cols.most_common(10), "fonts": fonts.most_common(4), "sizes": sizes.most_common(4),
            "radii": radii.most_common(3), "shadows": shadows}


# ---------------------------------------------------------------- pages and visuals

def _page_look(pj):
    """-> (description of the page colour, description of the wallpaper behind the page)"""
    def one(name):
        arr = (pj.get("objects") or {}).get(name)
        if not isinstance(arr, list) or not arr or not isinstance(arr[0], dict):
            return None
        pr = arr[0].get("properties") or {}
        c = _colour(pr.get("color"))
        t = _lit(pr.get("transparency"))
        if "image" in pr:
            return "a picture"
        if c is None:
            return None
        if c[0] == "hex":
            txt = f"{c[1]} ({name_of(c[1])})"
        elif c[0] == "theme":
            txt = f"theme colour {c[1]}"
        else:
            txt = "set by a rule"
        if isinstance(t, (int, float)) and t >= 100:
            return "none (fully transparent)"
        return txt + (f", {int(t)}% transparent" if isinstance(t, (int, float)) and t > 0 else "")
    return one("background"), one("outspace")


def _visual(vj, acc, content):
    vo = vj.get("visual") or {}
    cont, obj = vo.get("visualContainerObjects") or {}, vo.get("objects") or {}
    seen = set()
    if content:
        st = acc["style"]
        st["n"] += 1
        for name, key in (("title", "title"), ("background", "background"), ("border", "border"), ("dropShadow", "shadow")):
            arr = cont.get(name)
            if isinstance(arr, list) and arr and isinstance(arr[0], dict):
                show = _lit((arr[0].get("properties") or {}).get("show"))
                if show is not False and (arr[0].get("properties") or {}):
                    st[key] += 1
        vh = cont.get("visualHeader")
        if isinstance(vh, list) and vh and isinstance(vh[0], dict) and _lit((vh[0].get("properties") or {}).get("show")) is False:
            st["header_hidden"] += 1
        for oname, pname, val in _props({"border": cont.get("border")}):
            if pname == "radius" and isinstance(_lit(val), (int, float)):
                st["radius"][_lit(val)] += 1
        pad = {p: _lit(v) for o, p, v in _props({"padding": cont.get("padding")}) if isinstance(_lit(v), (int, float))}
        if pad:
            st["padding"][tuple(pad.get(k, 0) for k in ("top", "right", "bottom", "left"))] += 1
    for src in (cont, obj):
        for oname, pname, val in _props(src):
            low = pname.lower()
            if "fontfamily" in low and isinstance(_lit(val), str):
                acc["fonts"][oname][_lit(val)] += 1
            elif (low in SIZE_PROPS or low.endswith("fontsize")) and isinstance(_lit(val), (int, float)):
                acc["sizes"][oname][_lit(val)] += 1
            c = _colour(val)
            if c is None:
                continue
            key = (oname, pname, c)
            if key in seen:
                continue
            seen.add(key)
            if c[0] == "hex":
                acc["colours"][c[1]] += 1
                acc["where"][c[1]][_role(oname, pname)] += 1
            elif c[0] == "theme":
                acc["theme_refs"][(c[1], c[2])] += 1
            else:
                acc["rules"] += 1


def _grid(rect_pages):
    """The most common margin from the page edge and gap between neighbouring visuals, over all pages."""
    left, top, gh, gv = Counter(), Counter(), Counter(), Counter()
    for rects in rect_pages:
        if len(rects) < 3:
            continue
        left[round(min(r[0] for r in rects))] += 1
        top[round(min(r[1] for r in rects))] += 1
        for a in rects:
            best_h = best_v = None
            for b in rects:
                if a is b:
                    continue
                gap = b[0] - (a[0] + a[2])
                over = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
                if 0 < gap <= 60 and over > 0.5 * min(a[3], b[3]) and (best_h is None or gap < best_h):
                    best_h = gap
                gap = b[1] - (a[1] + a[3])
                over = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
                if 0 < gap <= 60 and over > 0.5 * min(a[2], b[2]) and (best_v is None or gap < best_v):
                    best_v = gap
            if best_h is not None:
                gh[round(best_h)] += 1
            if best_v is not None:
                gv[round(best_v)] += 1
    out = {}
    if left:
        out["margin_left"] = _top(left)[0]
        out["margin_top"] = _top(top)[0]
    if sum(gh.values()) >= 4:
        out["gap_h"] = _top(gh)[0]
    if sum(gv.values()) >= 4:
        out["gap_v"] = _top(gv)[0]
    return out


def collect(report_dir, pages, measures):
    """pages: the analysis page list (id, displayName, mainNav, visuals with id and category). -> design dict, never raises."""
    try:
        return _collect(Path(report_dir), pages, measures)
    except Exception as exc:                                  # the manual must still be built
        return {"error": str(exc), "found": False}


def _collect(report_dir, pages, measures):
    use = [p for p in pages if p.get("mainNav")] or list(pages)
    acc = {"colours": Counter(), "where": defaultdict(Counter), "theme_refs": Counter(), "rules": 0,
           "fonts": defaultdict(Counter), "sizes": defaultdict(Counter),
           "style": {"n": 0, "title": 0, "background": 0, "border": 0, "shadow": 0, "header_hidden": 0,
                     "radius": Counter(), "padding": Counter()}}
    page_rows, rect_pages, sizes = [], [], Counter()
    content_cat = {"HTML Content (custom visual)", "KPI Card", "Table", "Chart"}
    for p in use:
        pdir = report_dir / "definition" / "pages" / p["id"]
        pj = _load(pdir / "page.json")
        bg, wall = _page_look(pj)
        w, h = pj.get("width") or p.get("width"), pj.get("height") or p.get("height")
        if w and h:
            sizes[(int(w), int(h))] += 1
        cat = {v["id"]: v["category"] for v in p.get("visuals", [])}
        rects = []
        vdir = pdir / "visuals"
        if vdir.exists():
            for vf in sorted(vdir.iterdir()):
                vj = _load(vf / "visual.json")
                if not vj:
                    continue
                category = cat.get(vj.get("name"), "")
                _visual(vj, acc, category in content_cat)
                pos = vj.get("position") or {}
                if category in content_cat or category == "Slicer":
                    try:
                        rects.append((float(pos["x"]), float(pos["y"]), float(pos["width"]), float(pos["height"])))
                    except (KeyError, TypeError, ValueError):
                        pass
        rect_pages.append(rects)
        page_rows.append({"name": (p.get("displayName") or p["id"]).strip(), "width": w, "height": h,
                          "display": pj.get("displayOption"), "background": bg, "wallpaper": wall})
    theme = _theme(report_dir)
    html = _html_design(measures)
    fonts = {o: c for o, c in acc["fonts"].items() if c}
    typography = []
    for o, c in sorted(fonts.items(), key=lambda kv: -sum(kv[1].values())):
        sz = acc["sizes"].get(o) or Counter()
        typography.append({"element": ELEMENT_LABEL.get(o) or _words(o).capitalize(), "fonts": c.most_common(2),
                           "size": _top(sz)[0] if sz else None, "sizes": sorted(sz), "n": sum(c.values())})
    for o, sz in acc["sizes"].items():                           # sizes with no font set on that element
        if o not in fonts and sz:
            typography.append({"element": ELEMENT_LABEL.get(o) or _words(o).capitalize(), "fonts": [], "size": _top(sz)[0],
                               "sizes": sorted(sz), "n": sum(sz.values())})
    colours = [(h, n, [r for r, _ in acc["where"][h].most_common(2)]) for h, n in acc["colours"].most_common(12)]
    grid = _grid(rect_pages)
    d = {"theme": theme, "pages": page_rows, "sizes": sizes.most_common(), "colours": colours,
         "theme_refs": sum(acc["theme_refs"].values()), "rule_colours": acc["rules"], "typography": typography,
         "style": acc["style"], "html": html, "grid": grid}
    cf, bf = theme.get("custom_file"), theme.get("base_file")
    d["found"] = bool(colours or typography or html["measures"] or cf or bf or theme.get("base") or theme.get("custom")
                      or acc["style"]["background"] or acc["style"]["border"] or acc["style"]["shadow"])
    return d
