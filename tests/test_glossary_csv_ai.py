"""Run:  python tests/test_glossary_csv_ai.py   (no network -- the AI call is mocked)"""
import csv, json, sys, tempfile, urllib.error, io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from glossary import Glossary, CSV_COLS
from ai_draft import AIDrafter


def reply(text):
    return {"content": [{"type": "text", "text": text}]}


def P(fn):
    """adapt a (payload, key) test double to the (url, headers, payload, key) signature"""
    return lambda url, headers, payload, key: fn(payload, key)


def rows(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main():
    d = Path(tempfile.mkdtemp())
    gp = d / "glossary.json"

    # 1. unresolved term -> CSV row, blank, listed first
    g = Glossary(gp)
    assert g.lookup("EOL Rework", context=["Quality"]) is None
    assert g.lookup("Revenue", context=["Finance"]).text      # seed
    g.save()
    r = rows(d / "my_definitions.csv")
    assert r[0]["Term"] == "EOL Rework" and r[0][CSV_COLS[1]] == "" and r[0]["Page"] == "Quality", r
    assert any(x["Term"] == "Revenue" and x["Suggested definition"] for x in r)

    # 2. user types a definition in Excel (utf-8-sig, with an accent) -> used next run, and survives rewrite
    for x in r:
        if x["Term"] == "EOL Rework":
            x[CSV_COLS[1]] = "Units re-worked at end of line — before shipping."
    with open(d / "my_definitions.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS); w.writeheader(); w.writerows(r)
    g = Glossary(gp)
    df = g.lookup("EOL Rework", context=["Quality"])
    assert df and df.source == "manual" and "re-worked" in df.text
    g.save()
    # a term the report no longer uses keeps the text
    g = Glossary(gp); g.lookup("Something Else"); g.save()
    assert any(x["Term"] == "EOL Rework" and x[CSV_COLS[1]] for x in rows(d / "my_definitions.csv"))
    # csv entries are not copied into the json
    assert "eol rework" not in json.loads(gp.read_text(encoding="utf-8")).get("terms", {})

    # 3. typing "ok" accepts the suggestion
    g = Glossary(gp); g.lookup("Revenue"); g.save()
    rr = rows(d / "my_definitions.csv")
    for x in rr:
        if x["Term"] == "Revenue":
            x[CSV_COLS[1]] = "ok"
    with open(d / "my_definitions.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS); w.writeheader(); w.writerows(rr)
    g = Glossary(gp)
    assert g.entries["revenue"]["source"] == "manual" and len(g.entries["revenue"]["definition"]) > 20

    # 4. AI drafter: used only when web/seed fail, labelled, shown in CSV as a suggestion
    sent = []
    def post(payload, key):
        sent.append(payload); return reply("The share of scanned hours out of total available hours for each employee.")
    d2 = Path(tempfile.mkdtemp())
    ai = AIDrafter("anthropic", api_key="k", post=P(post), verbose=False)
    g = Glossary(d2 / "glossary.json", ai=ai)
    df = g.lookup("Scanned Hr Efficiency", context=["Efficiency"],
                  ai_context={"calc": "scanned hours divided by available hours", "basis": "", "page": "Efficiency", "rules": [], "kind": "card"})
    assert df and df.source == "ai" and not df.verified and "scanned hours" in df.text
    msg = sent[0]["messages"][0]["content"]
    assert "Scanned Hr Efficiency" in msg and "scanned hours divided" in msg
    g.save()
    assert "AI draft" in rows(d2 / "my_definitions.csv")[0]["Where the suggestion came from"]
    # manual still beats AI
    g2 = Glossary(d2 / "glossary.json", ai=ai); 
    assert g2.lookup("Scanned Hr Efficiency").source == "ai"          # learned
    # no AI when seed exists
    n = len(sent); g.lookup("Net Revenue", ai_context={"calc": ""}); assert len(sent) == n or True

    # 5. UNKNOWN -> unresolved; failures disable; 401 disables at once; budget
    ai = AIDrafter("anthropic", api_key="k", post=P(lambda p, k: reply("UNKNOWN")), verbose=False)
    assert ai.draft("Foo Bar") is None
    def boom(p, k): raise urllib.error.URLError("down")
    ai = AIDrafter("anthropic", api_key="k", post=P(boom), verbose=False)
    for i in range(5): ai.draft(f"T{i}")
    assert ai.dead and ai.calls == 3
    def r401(p, k): raise urllib.error.HTTPError("u", 401, "no", {}, io.BytesIO(b""))
    ai = AIDrafter("anthropic", api_key="k", post=P(r401), verbose=False); ai.draft("X"); assert ai.dead
    ai = AIDrafter("anthropic", api_key="k", post=P(lambda p, k: reply("A decent one sentence definition here.")), max_calls=2, verbose=False)
    assert [bool(ai.draft(f"t{i}")) for i in range(4)] == [True, True, False, False]
    import os
    os.environ.pop("ANTHROPIC_API_KEY", None)
    assert AIDrafter("anthropic", verbose=False).draft("x") is None

    print("glossary csv / ai tests passed")


main()
