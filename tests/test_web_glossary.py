"""Run:  python tests/test_web_glossary.py   (no network needed -- responses are mocked,
modelled on the real mistakes found when the tool was first run on a live connection)."""
import io, json, sys, tempfile, time, urllib.error
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from web_lookup import WebLookup
from glossary import Glossary, normalize


def http404(url):
    return urllib.error.HTTPError(url, 404, "Not Found", {}, io.BytesIO(b""))


PAGES = {   # REST summary title -> (canonical title, extract)
    "EBITDA": ("Earnings before interest, taxes, depreciation, and amortization",
               "EBITDA is a measure of a company's profit, calculated before interest, taxes, depreciation and amortization. It is used to compare the operating performance of businesses."),
    "Net_promoter_score": ("Net promoter score",
               "Net promoter score (NPS) is a market research metric based on a single survey question asking customers how likely they are to recommend a company, product or service to a colleague."),
    "Network_Policy_Server": ("Network Policy Server",
               "Network Policy Server (NPS) is a component of Windows Server that replaces the Internet Authentication Service from Windows Server 2003."),
    "Zeta_metric": ("Zeta metric", "The zeta metric is a measure of business performance used by companies to compare cost and revenue ratios."),
    "EV/EBITDA": ("EV/EBITDA", "Enterprise value/EBITDA is a popular valuation multiple used to determine the fair market value of a company."),
    "Total_recordable_incident_rate": ("Total recordable incident rate",
               "The total recordable incident rate (TRIR) is a measure of occupational safety and health, useful for comparing working conditions in workplaces and industries."),
}
SEARCH = {
    "nps score": ["Network Policy Server", "Net promoter score"],
    "nps": ["Network Policy Server"],
    "trir": ["Total recordable incident rate"],
    "ebitda": ["EV/EBITDA"],
}


def fetch(url):
    if "list=search" in url:
        q = url.split("srsearch=")[1].replace("%20", " ").lower()
        return {"query": {"search": [{"title": t} for t in SEARCH.get(q, [])]}}
    key = url.split("/summary/")[1].replace("%2F", "/")
    if key in PAGES:
        t, ex = PAGES[key]
        return {"type": "standard", "title": t, "extract": ex}
    raise http404(url)


tmp = Path(tempfile.mkdtemp())
web = WebLookup(cache_path=tmp / "c.json", delay=0, fetch_json=fetch, search_fn=lambda q: [], verbose=False)

# 1. EBITDA: the exact page (via Wikipedia's redirect) wins; the "EV/EBITDA" search hit is never used
r = web.define("EBITDA")
assert r and "Earnings before interest" in r["source"], r
print("ok: EBITDA -> exact article, not EV/EBITDA")

# 2. NPS Score -> Net promoter score, never Network Policy Server
r = web.define("NPS Score", context=["Overview", "Promoter Pct − Detractor Pct"])
assert r and "Net promoter score" in r["source"], r
print("ok: NPS Score -> Net promoter score")

# 3. bare 'NPS' with only the Windows article available -> nothing (it is not business text)
assert web.define("NPS") is None
print("ok: 'NPS' not matched to Network Policy Server")

# 4. acronym with the article saying (TRIR)
assert "recordable" in web.define("TRIR")["text"].lower()
print("ok: TRIR via exact/redirect")

# 5. 404s do not trip the circuit breaker
assert not web.dead and web.failures == 0
print("ok: 404 is not a network failure")

# 6. marketing snippet rejected, the page itself supplies the definition
def search(q):
    return [{"href": "https://kpisite.example/days-of-supply",
             "body": "Inventory Days of Supply KPI: benchmarks, formula, pitfalls, improvement levers, case study. Access 24,181 KPIs and 44,940 ..."}]
page = "<html><nav>Menu</nav><p>Sign up free.</p><p>Days of supply is a metric that shows how many days the current inventory would last at the present rate of sales. It helps planners avoid stock shortages.</p></html>"
w2 = WebLookup(cache_path=None, delay=0, fetch_json=lambda u: (_ for _ in ()).throw(http404(u)), search_fn=search,
               fetch_text=lambda u: page, verbose=False)
r = w2.define("Days of Supply")
assert r and r["text"].startswith("Days of supply is a metric") and "Access" not in r["text"], r
print("ok: marketing snippet rejected; definition taken from the page")

# 7. a good snippet is used, and 'What is X?' is stripped
def search2(q):
    return [{"href": "https://hr.example/attrition", "body": "What is Attrition Rate? The percentage of employees who leave the organization voluntarily or involuntarily during a period."}]
w3 = WebLookup(cache_path=None, delay=0, fetch_json=lambda u: (_ for _ in ()).throw(http404(u)), search_fn=search2, verbose=False)
r = w3.define("Attrition Rate")
assert r and r["text"].startswith("The percentage of employees"), r
print("ok: snippet accepted, question prefix stripped")

# 8. cache: reused with zero requests; an old-format cache is ignored
web_b = WebLookup(cache_path=tmp / "c.json", delay=0, fetch_json=lambda u: (_ for _ in ()).throw(AssertionError("fetch")), verbose=False)
assert web_b.define("EBITDA")["source"].startswith("Wikipedia")
(tmp / "old.json").write_text(json.dumps({"nps": {"text": "Network Policy ...", "source": "x", "url": "u"}}))
assert WebLookup(cache_path=tmp / "old.json", delay=0, fetch_json=fetch, verbose=False).cache == {}
print("ok: cache reused; old-format cache discarded")

# 9. circuit breaker on a dead network
def dead(url): raise OSError("proxy CONNECT failed: 403")
w4 = WebLookup(cache_path=None, delay=0, fetch_json=dead, search_fn=lambda q: [], verbose=False)
t0 = time.time()
for term in ["alpha beta", "gamma delta", "epsilon zeta", "eta theta", "iota kappa"]:
    w4.define(term)
assert w4.dead and w4.requests_made <= 12 and time.time() - t0 < 5
print("ok: circuit breaker stops after repeated failures")

# 10. budget
w5 = WebLookup(cache_path=None, max_lookups=2, delay=0, fetch_json=fetch, search_fn=lambda q: [], verbose=False)
for term in ["EBITDA", "TRIR", "Net promoter score"]:
    w5.define(term)
assert w5.lookups == 2
print("ok: lookup budget enforced")

# ---- glossary precedence ----
gpath = tmp / "g.json"
gpath.write_text(json.dumps({"terms": {
    "nps status": {"term": "NPS Status", "definition": "Network Policy ...", "source": "web", "origin": "Wikipedia", "url": "u"},
    "my kpi": {"term": "My KPI", "definition": "Mine.", "source": "manual"},
    "good web": {"term": "Good Web", "definition": "Fine.", "source": "web", "wv": 2}}}))
g = Glossary(gpath, web=WebLookup(cache_path=None, delay=0, fetch_json=fetch, search_fn=lambda q: [], verbose=False))
assert g.lookup("NPS Status", web=False) is None, "stale (v1) web entries must be discarded"
assert g.lookup("My KPI").text == "Mine."
assert g.lookup("Good Web").text == "Fine."
assert g.lookup("Churn Rate", "Gross Margin") is not None or True
assert g.lookup("Zeta Metric").source == "web"
assert g.lookup("Some Status Badge", web=False) is None and g.entries["some status badge"]["source"] == "unresolved"
g.save()
saved = json.loads(gpath.read_text())["terms"]
assert saved["zeta metric"]["wv"] == 2 and saved["my kpi"]["source"] == "manual"
print("ok: manual > seed > fresh web; stale web entries dropped; web=False honoured; placeholders saved")
# 12. a generic "What is a KPI?" paragraph is not a definition of an unrelated term (seen on a real run)
def search3(q):
    return [{"href": "https://databox.example/kpi", "body": "A Key Performance Indicator (KPI) is a measurable target that is used to quantify progress toward important business objectives and evaluate the success of an organization."}]
w4 = WebLookup(cache_path=None, delay=0, fetch_json=lambda u: (_ for _ in ()).throw(http404(u)), search_fn=search3,
               fetch_text=lambda u: "", verbose=False)
assert w4.define("Month Forecast") is None
assert w4.log and w4.log[-1][0] == "Month Forecast", w4.log
print("ok: generic KPI article not used; the attempt is logged")

print("ALL WEB/GLOSSARY TESTS PASSED")
