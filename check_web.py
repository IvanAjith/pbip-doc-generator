import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from web_lookup import WebLookup

terms = ["Inventory Turnover", "Churn Rate", "TRIR", "Net Promoter Score",
         "Gross Margin", "Days of Supply", "Attrition Rate", "EBITDA"]
web = WebLookup(cache_path=None, max_lookups=20, delay=0.5, verbose=True)
for t in terms:
    r = web.define(t)
    print("\n=== " + t)
    if r:
        print(r["text"])
        print("source:", r["source"], "|", r["url"])
    else:
        print("NOTHING FOUND")
    if web.dead:
        print("\nWEB BLOCKED:", web.dead_reason)
        break
print("\nSUMMARY: searched", web.lookups, "| found", web.found, "| blocked:", web.dead, web.dead_reason)
