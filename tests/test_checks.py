"""AI drafts are vetted against what was sent: invented numbers, guessed abbreviations, copied sentences, ratios."""
import io, json, os, sys, tempfile, urllib.error
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["PBIP_DOC_GENERATOR_HOME"] = tempfile.mkdtemp()
import checks
from checks import Checker, Context, spelled_out, clean_text, facts_text, initials_definitions
from ai_draft import AIDrafter
from glossary import Glossary

F = lambda term, calc="", page="Safety", rules=(): facts_text(term, calc=calc, page=page, rules=rules)

# --- numbers
ck = Checker()
r = ck.validate("Service Scores", "Overall score with a target of at least 400%.", F("Service Scores"))
assert not r.ok and "400" in r.hard[0]
r = ck.validate("Quality Status", "Red above 10%, green otherwise.", F("Quality Status", rules=["red when EOL Rework % > 10%"]))
assert r.ok, r.hard                                       # the number was supplied -> fine
r = Checker().validate("X", "Orders for the Standex V5 report in 5S and 30-day windows.", F("X 30 days 5S"))
assert r.ok, r.hard                                       # 'V5' and '5S' are names, '30' was supplied
print("ok: numbers")

# --- abbreviations
assert spelled_out("CB", "The 30-day raw customer bracket cost.")
assert spelled_out("LOC", "local operating company balance")
assert spelled_out("DOC", "distinct document entries")
assert spelled_out("EOL", "end-of-line rework")
assert spelled_out("FT", "full-time employees")
assert not spelled_out("KEY", "distinct employee keys")
assert not spelled_out("PASS", "records with a passing result")
assert not spelled_out("CB", "Percentage of claims relative to normal production")   # dropped, not guessed
ck = Checker()
r = ck.validate("30D Claims", "The 30-day raw customer bracket cost per labour hour.", F("30D Claims", "30 Days Raw CB Cost divided by DL Hours"))
assert not r.ok and r.guessed == ["CB"] and "CB" in ck.guessed
ctx = Context(); ctx.abbr["CB"] = "chargeback"
r = Checker(ctx).validate("30D Claims", "The 30-day raw chargeback cost per labour hour.", F("30D Claims", "30 Days Raw CB Cost divided by DL Hours"))
assert r.ok, r.hard                                      # defined in the context file -> not a guess
assert initials_definitions(["Labour Classification is “Direct Labour (DL) FT” and “InDirect Labour (IDL) FT”"]) == {"DL": "Direct Labour", "IDL": "In Direct Labour"}
c2 = Context(); c2.learn_from_report(['x = "Direct Labour (DL) FT"'])
r = Checker(c2).validate("Net Rev per DL", "Net revenue per direct labour hour.", F("Net Rev per DL", "Net Total Revenue divided by DL Clocked Hours"))
assert r.ok, r.hard                                      # the report itself spells DL out
print("ok: abbreviations")

# --- ratio, copies, filler
r = Checker().validate("Count %", "Total count of records where the table is Near Miss.", F("Count %", "Count of Record ID as a percentage of count of Record ID"))
assert not r.ok and "ratio" in r.hard[0]
ck = Checker()
assert ck.validate("A", "The number of records that were closed in the period.", F("A")).ok
r = ck.validate("B", "The number of records that were closed in the period.", F("B"))
assert not r.ok and "same sentence" in r.hard[0]
ck = Checker()
assert ck.validate("% Positive", "The percentage of positive mentions out of all mentions.", F("% Positive", "Positive as a percentage of Mentions")).ok
assert ck.validate("% Negative", "The percentage of negative mentions out of all mentions.", F("% Negative", "Negative as a percentage of Mentions")).ok   # parallel, not copied
assert clean_text("Net revenue per hour, shown on the Revenue page of the Standex V5 report.") == "Net revenue per hour."
assert clean_text("Hours used to track idle time on the Efficiency page of the Standex V5 report.") == "Hours used to track idle time."
print("ok: ratio / copies / filler")

# --- the soft check keeps the draft but says what to look at
r = Checker().validate("Delivery", "Percentage of orders meeting fulfillment reliability criteria.", F("Delivery", "Delivery KEY as a percentage of Delivery KEY"))
assert r.ok and r.soft and "fulfillment" in r.soft[0]
print("ok: soft flags")

# --- the context file: created, extended, read
d = Path(tempfile.mkdtemp()); cp = d / "context.txt"
c = Context(cp)
assert c.write_template({"CB", "LOC"}) and "CB = " in cp.read_text() and "LOC = " in cp.read_text()
assert not Context(cp).abbr                               # blank meanings are ignored
cp.write_text(cp.read_text().replace("CB = ", "CB = chargeback").replace("Domain: ", "Domain: manufacturing"))
c = Context(cp)
assert c.abbr == {"CB": "chargeback"} and c.domain == "manufacturing"
assert any("CB = chargeback" in l for l in c.prompt_lines()) and any("manufacturing" in l for l in c.prompt_lines())
assert c.write_template({"CB", "WO"}) and sum(l.startswith("CB") for l in cp.read_text().splitlines()) == 1 and "WO = " in cp.read_text()   # only the new one is added
assert not c.write_template({"CB"})
print("ok: context file")

# --- AIDrafter + checker end to end (fake service)
def fake(text):
    return lambda url, h, p, k: {"choices": [{"message": {"content": text}}]}
sent = []
def spy(url, h, p, k):
    sent.append(json.dumps(p))
    return {"choices": [{"message": {"content": "The 30-day raw customer bracket cost per labour hour."}}]}
cp2 = d / "context2.txt"; cp2.write_text("Domain: manufacturing\n", encoding="utf-8")      # CB is NOT defined here
ai = AIDrafter("openai", api_key="K", post=spy, verbose=False); ai.checker = Checker(Context(cp2))
assert ai.draft("30D Claims", calc="30 Days Raw CB Cost divided by DL Hours", page="Quality") is None
assert ai.rejected_n == 1 and ai.drafted == 0 and not ai.dead
assert "manufacturing" in sent[0]                          # the context reaches the AI
cp.write_text(cp.read_text() + "DL = direct labour\n")
ai = AIDrafter("openai", api_key="K", post=fake("Cost of chargebacks per direct labour hour, shown on the Quality page."), verbose=False)
ai.checker = Checker(Context(cp))
r = ai.draft("30D Claims", calc="30 Days Raw CB Cost divided by DL Hours", page="Quality")
assert r and r["text"] == "Cost of chargebacks per direct labour hour." and ai.drafted == 1
print("ok: AIDrafter + checker")

# --- Glossary: an AI draft saved by an older run is vetted again
gp = d / "glossary.json"
gp.write_text(json.dumps({"terms": {"service scores": {"term": "Service Scores", "definition": "Score with a target of 400%.", "source": "ai",
                                                       "origin": "AI draft", "verified": False},
                                    "month end backlog": {"term": "Month End Backlog", "definition": "Sales order value waiting to ship at month end.",
                                                          "source": "ai", "origin": "AI draft", "verified": False}}}), encoding="utf-8")
g = Glossary(gp, checker=Checker())
bad = g.lookup("Service Scores", context=["Voc"], ai_context={"calc": "", "basis": "", "page": "Voc", "rules": [], "kind": "value"},
               draft={"calc": "Built from Rating Value", "unit": None, "inputs": []})
assert bad is None or bad.source != "ai", bad                                  # dropped, falls back
good = g.lookup("Month End Backlog", context=["Delivery"], ai_context={"calc": "total of Line NET Amount", "basis": "", "page": "Delivery", "rules": [], "kind": "value"})
assert good and good.source == "ai"
print("ok: glossary re-checks saved AI drafts")
print("checks tests passed")
