"""Run:  python tests/test_cross_check.py   -- AI mode compares each AI sentence with the offline wording and keeps the safer one."""
import sys, tempfile, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import checks
from checks import unsupported_words as U, Context, Checker
from glossary import Glossary

# --- the word check
M = {"DL": "direct labour", "FTE": "full-time equivalent", "QTY": "quantity"}
assert U("Total scanned labor hours divided by direct labour clocked hours.", "Scanned Hr Efficiency Scanned Labor Hours ÷ DL Clocked Hours", M) == []
assert U("Hours captured through barcode scans.", "ScannedHrs total Scanned Labor Hours", M) == ["captured", "barcode"]
assert "customer" in U("Average rating from customer feedback.", "Avg Rating average Rating Value", M)
assert "scheduled" in U("Walks completed out of walks scheduled.", "Gemba Completion % Gemba CompletedWalks ÷ Gemba Walks Total", M)
assert "unique" in U("Total unique employees.", "Admin count number of distinct Employee KEY", M)
assert U("The percentage of jobs with open quantity.", "Jobs QTY", M) == ["open"]            # QTY = quantity is a standard spelling-out
assert "direct" in U("Direct labour hours.", "Hours", M) and U("Direct labour hours.", "DL Hours", M) == []   # an explanation counts only where the abbreviation appears
assert U("Net revenue per clocked hour.", "Net Total Revenue ÷ DL Clocked Hours", M) == []

# --- inside the glossary, with a stand-in AI
class FakeAI:
    def __init__(self, text): self.text = text; self.calls = 0
    def draft(self, term, **ctx):
        self.calls += 1
        return {"text": self.text, "origin": "AI draft (fake) - please verify"}

def run(term, ai_text, calc, page="Efficiency", folder=None, cross=True, unit=None, inputs=None, ctx=None, name_context=None):
    d = folder or Path(tempfile.mkdtemp())
    context = Context(d / "context.txt")
    if ctx:
        context.set_meanings(ctx)
    g = Glossary(d / "glossary.json", ai=FakeAI(ai_text), checker=Checker(context))
    g.context, g.cross_check = context, cross
    ai_ctx = {"calc": calc, "basis": "", "page": page, "rules": []}
    out = g.lookup(term, ai_context=ai_ctx, draft={"calc": calc, "unit": unit, "inputs": inputs or []}, web=False)
    return g, out, d

# 1. the AI invents 'barcode' -> the offline formula wording is used, and the CSV says why
g, x, d = run("ScannedHrs", "Total working hours captured through barcode scans.", "total Scanned Labor Hours")
assert x.source == "draft" and x.text == "The total of Scanned Labor Hours." and "barcode" in x.origin, (x.source, x.text, x.origin)
assert g.cross_log["ScannedHrs"][0] == "offline formula"
# 2. the AI stays inside the report -> the AI sentence is kept
g, x, d = run("Rev per Clock Hour", "Net Total Revenue generated per Direct Labour clocked hour.", "Net Total Revenue ÷ DL Clocked Hours", ctx={"DL": "direct labour"})
assert x.source == "ai" and g.cross_log["Rev per Clock Hour"][0] == "ai kept", (x.source, g.cross_log)
# 3. the name itself says it plainly -> the plain reading wins even over a clean AI sentence
g, x, d = run("% Unscheduled Jobs", "The proportion of distinct document entries that are unscheduled sales orders out of all distinct document entries.",
              "number of distinct DOC Entry (counting only rows where Document Type is “Sales Order” and Open QTY > 0 and 1 further condition) ÷ number of distinct DOC Entry",
              unit="percent")
assert x.source == "draft" and x.text == "The percentage of jobs that are not scheduled." and g.cross_log["% Unscheduled Jobs"][0] == "offline name", x.text
# 4. no offline wording exists and the AI used outside words -> the AI sentence is kept, marked, and flagged for the clarification file
g, x, d = run("6 months Recorded Incidents", "Total number of safety incidents logged over a rolling period.", "", inputs=["Recordable Incidents", "Source Table"], page="Reports")
assert x.source == "ai" and x.note.startswith("The AI used words that are not in the report") and g.cross_log["6 months Recorded Incidents"][0] == "confirm", (x.note, g.cross_log)
assert "words not in the report" in x.origin
# 5. switched off: the AI sentence is used as it is
g, x, d = run("ScannedHrs", "Total working hours captured through barcode scans.", "total Scanned Labor Hours", cross=False)
assert x.source == "ai" and not g.cross_log
# 6. the decision is made again on a later run, from the saved AI sentence (and the offline run still has the AI text on file)
g2 = Glossary(d / "glossary.json", ai=None, checker=Checker(Context(d / "context.txt")))
g2.context = Context(d / "context.txt")
g, x, d = run("ScannedHrs", "Total working hours captured through barcode scans.", "total Scanned Labor Hours")
g3 = Glossary(d / "glossary.json", ai=None, checker=Checker(Context(d / "context.txt")))
g3.context = Context(d / "context.txt"); g3.save()
g3 = Glossary(d / "glossary.json", ai=None, checker=Checker(Context(d / "context.txt")))
g3.context = Context(d / "context.txt")
y = g3.lookup("ScannedHrs", ai_context={"calc": "total Scanned Labor Hours", "basis": "", "page": "Efficiency", "rules": []},
              draft={"calc": "total Scanned Labor Hours", "unit": None, "inputs": []}, web=False)
assert y.source == "draft" and y.text == "The total of Scanned Labor Hours.", (y.source, y.text)
# 7. a typed definition and a built-in one are never touched
g, x, d = run("Revenue", "Money earned from barcode scans.", "A ÷ B")
assert x.source == "seed" and not g.cross_log
print("cross-check tests passed")
