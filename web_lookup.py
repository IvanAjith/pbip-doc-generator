"""
web_lookup.py -- finds a plain-English definition of a business term online.

Sources, in order:
  1. Wikipedia, by exact title (its redirects know that "EBITDA" is
     "Earnings before interest, taxes, depreciation, and amortization").
  2. Wikipedia search, accepting only an article whose title IS the term, is
     made only of words from the term, or whose first lines say "(ACRONYM)".
  3. A general web search (the optional `ddgs` package): the snippet if it
     reads like a definition, otherwise the first definitional sentence of the
     page itself.

Guards against wrong answers (found by testing on real reports):
  * A candidate must read like business / measurement text (vocabulary check),
    so "NPS" can not become "Network Policy Server".
  * Marketing snippets ("benchmarks, formula, case study ... access 24,000
    KPIs") are rejected.
  * Where several articles qualify, words from the report itself (the
    measure's formula, the page name) break the tie.
  * Every result carries its source name and URL and is saved UNVERIFIED.

Practicalities:
  * Results (including "nothing found") are cached on disk.
  * A per-run request budget and a circuit breaker (stops after repeated
    network failures) keep a run from stalling when there is no internet.
    A "page not found" (404) is a normal answer, not a network failure.
  * `fetch_json`, `fetch_text` and `search_fn` can be replaced, which is how
    the tests run without a network.
"""
import html as _html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

USER_AGENT = "pbip-doc-generator/2.0 (local documentation tool)"
CACHE_VERSION = 2
_NOISE_WORDS = {"html", "card", "pill", "status", "table", "title", "hdr", "header"}
_STOP = {"the", "a", "an", "of", "and", "or", "per", "to", "in", "on", "for", "by", "vs", "rate", "total",
         "is", "are", "with", "from", "this", "that", "what"}

# Words that business / measurement text uses. A candidate with fewer than
# two of these in its opening lines is not about a business measure.
_BIZ_VOCAB = set("""
metric metrics measure measures measured measuring measurement indicator indicators kpi kpis ratio percentage percent
proportion rate rates revenue revenues profit profits cost costs margin margins sales customer customers employee employees
employment workforce inventory stock supply production quality safety incident incidents injury injuries performance
efficiency productivity delivery deliveries order orders financial finance accounting business businesses company companies
market marketing survey surveys score scores satisfaction churn retention turnover attrition hiring operations operational
manufacturing service services cash earnings income expense expenses budget forecast target benchmark analytics management
logistics warehouse risk compliance subscribers subscription users price pricing investment investor portfolio asset assets
return yield equity debt capital loan credit fund funds interest tax taxes time hours labor labour wages pay payroll
organization organisation industry occupational worker workers staff period year annual quarterly monthly
""".split())

_MARKETING_RE = re.compile(
    r"benchmarks?,?\s+formula|case study|access\s+[\d,]+\s+kpis|sign up|free trial|download|click here|subscribe|"
    r"learn more|pricing plans?|request a demo|\btemplates?\b|best practices for|\bour (?:platform|software|solution)",
    re.I)
_DEFN_RE = re.compile(r"\b(is|are|was|measures?|refers? to|represents?|calculated|defined as|means|describes?|"
                      r"expresses?|indicates?|shows?)\b", re.I)


def _words(s):
    return [w for w in re.findall(r"[a-z0-9]+", (s or "").lower())]


def clean_term(term: str) -> str:
    """'Gemba Completion %' -> 'Gemba Completion'; drops report-plumbing words."""
    t = re.sub(r"\([^)]*\)", " ", term)
    t = re.sub(r"[%_#]", " ", t)
    words = [w for w in t.split() if w.lower() not in _NOISE_WORDS]
    return " ".join(words).strip()


def _stem(w):
    return w[:-1] if len(w) > 3 and w.endswith("s") else w


def _significant(term):
    return [_stem(w) for w in _words(term) if w not in _STOP and len(w) > 1]


def _vocab_hits(text):
    return len({w for w in _words(text[:700]) if w in _BIZ_VOCAB})


def _context_tokens(context):
    toks = set()
    for c in context or ():
        toks.update(_stem(w) for w in _words(str(c)) if w not in _STOP and len(w) > 3)
    return toks


def _default_fetch_json(url, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _default_fetch_text(url, timeout=8, limit=600_000):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; pbip-doc-generator)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(limit).decode("utf-8", errors="replace")


def _sentences(text):
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"\s*\([^()]*(?:pronounced|IPA|/[^/]+/)[^()]*\)", "", text)
    return [p for p in re.split(r"(?<=[.!?])\s+(?=[A-Z])", text) if p]


def _first_sentences(text, max_chars=320):
    out = ""
    for p in _sentences(text):
        if out and len(out) + len(p) + 1 > max_chars:
            break
        out = f"{out} {p}".strip()
        if len(out) >= 140:
            break
    out = out[:max_chars].rstrip()
    return out if out[-1:] in ".!?" else (re.sub(r"[^.!?]*$", "", out).strip() or "")


def _strip_question(text):
    """'What is Attrition Rate? The percentage of ...' -> 'The percentage of ...'"""
    return re.sub(r"^\s*(?:what\s+(?:is|are)\s+[^?]{1,80}\?\s*)", "", text or "", flags=re.I)


class WebLookup:
    def __init__(self, cache_path=None, max_lookups=40, delay=0.4, offline=False,
                 fetch_json=None, search_fn=None, fetch_text=None, verbose=True):
        self.cache_path = Path(cache_path) if cache_path else None
        self.cache = {}
        if self.cache_path and self.cache_path.exists():
            try:
                raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and raw.get("_v") == CACHE_VERSION:      # older caches held wrong matches
                    self.cache = raw.get("terms", {})
            except Exception:
                self.cache = {}
        self.max_lookups = max_lookups
        self.delay = delay
        self.offline = offline
        self.fetch_json = fetch_json or _default_fetch_json
        self.fetch_text = fetch_text or _default_fetch_text
        self.search_fn = search_fn if search_fn is not None else self._ddgs_search
        self.verbose = verbose
        self.requests_made = 0
        self.failures = 0
        self.lookups = 0
        self.log = []
        self.dead = False                 # circuit breaker
        self.dead_reason = ""
        self.found = 0

    # ---------------------------------------------------------- public
    @property
    def available(self):
        return not self.offline and not self.dead and self.lookups < self.max_lookups

    def define(self, term: str, context=()):
        """-> {'text','source','url'} or None."""
        key = " ".join(_words(clean_term(term)))
        if not key:
            return None
        if key in self.cache:
            return self.cache[key] or None
        if not self.available:
            return None
        self.lookups += 1
        result = None
        try:
            result = (self._wikipedia_direct(term, context) or self._wikipedia_search(term, context)
                      or self._web_search(term, context))
        except _NetworkDown:
            return None
        if result and not self._relevant(term, result["text"]):
            self._note(term, "rejected", "generic text about KPIs, not about the term: " + result["text"][:80])
            result = None
        self.cache[key] = result            # negative results are cached too
        if result:
            self.found += 1
            self._note(term, "found", result["source"] + " " + result["url"])
        else:
            if not self.log or self.log[-1][0] != term:
                self._note(term, "nothing found", "")
        self._save()
        return result

    _GENERIC_ARTICLE = re.compile(r"\bkey performance indicators?\b|\bKPIs?\b|\bperformance metrics?\b", re.I)

    @classmethod
    def _relevant(cls, term, text):
        """Reject generic text about KPIs or metrics in general (e.g. the 'What is a KPI?' paragraph that search
        engines return for almost any made-up business term) unless the term itself is about KPIs."""
        if cls._GENERIC_ARTICLE.search(text or "") and not cls._GENERIC_ARTICLE.search(term or ""):
            return False
        return True

    def _note(self, term, outcome, detail):
        self.log.append((term, outcome, detail))

    def write_log(self, path):
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("Web lookup log -- one line per term searched. Send this file if definitions are missing.\n")
                f.write(f"requests made: {self.requests_made}; failures: {self.failures}; "
                        f"web {'DISABLED: ' + self.dead_reason if self.dead else 'ok'}\n\n")
                for t, o, d in self.log:
                    f.write(f"{t!r:45} {o:14} {d}\n")
        except OSError:
            pass

    # ---------------------------------------------------------- plumbing
    def _down(self, e):
        self.failures += 1
        self._note("(network)", "error", f"{type(e).__name__}: {str(e)[:100]}")
        if self.failures >= 3:
            self.dead = True
            self.dead_reason = f"{type(e).__name__}: {str(e)[:120]}"
            if self.verbose:
                print(f"  (web lookup disabled for this run — {self.dead_reason})")
            raise _NetworkDown()

    def _get(self, url):
        self.requests_made += 1
        time.sleep(self.delay)
        try:
            data = self.fetch_json(url)
            self.failures = 0
            return data
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):                  # "no such page" is an answer, not an outage
                self.failures = 0
                return None
            self._down(e)
            return None
        except Exception as e:                        # network, TLS, proxy, JSON, timeout
            self._down(e)
            return None

    # ---------------------------------------------------------- candidate checks
    @staticmethod
    def _text_ok(text, min_vocab=2):
        if not text or len(text) < 40 or _MARKETING_RE.search(text):
            return False
        return _vocab_hits(text) >= min_vocab

    @staticmethod
    def _acronyms(term):
        return [t for t in re.findall(r"[A-Za-z0-9&]+", re.sub(r"[%_]", " ", term))
                if t.isupper() and 2 <= len(t) <= 8 and t.isalpha()]

    def _summary(self, title):
        surl = "https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title.replace(" ", "_"), safe="")
        summ = self._get(surl)
        if not summ or summ.get("type") == "disambiguation":
            return None
        text = _first_sentences(summ.get("extract", ""))
        page = ((summ.get("content_urls") or {}).get("desktop") or {}).get("page") or \
            "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
        return {"title": summ.get("title", title), "text": text, "url": page, "raw": summ.get("extract", "")}

    # ---------------------------------------------------------- 1. exact title
    def _wikipedia_direct(self, term, context):
        base = clean_term(term)
        if not base:
            return None
        variants = []
        for v in (base, base[:1].upper() + base[1:].lower(), " ".join(w if w.isupper() else w.capitalize()
                                                                   for w in base.split())):
            if v not in variants:
                variants.append(v)
        for v in variants[:3]:
            s = self._summary(v)
            if s and self._text_ok(s["text"]):
                return {"text": s["text"], "source": "Wikipedia — " + s["title"], "url": s["url"]}
        return None

    # ---------------------------------------------------------- 2. search
    def _wikipedia_search(self, term, context):
        base = clean_term(term)
        sig = set(_significant(base))
        acr = self._acronyms(base)
        if not sig:
            return None
        ctx = _context_tokens(context)
        url = ("https://en.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit=5"
               "&srsearch=" + urllib.parse.quote(base))
        data = self._get(url)
        hits = ((data or {}).get("query") or {}).get("search") or []
        best, best_key = None, None
        for h in hits[:4]:
            title = h.get("title", "")
            tt = set(_significant(title))
            if tt == sig:
                rank = 100
            elif tt and tt <= sig and len(tt) >= max(1, len(sig) - 1):
                rank = 60
            elif acr:
                rank = 40
            else:
                continue
            s = self._summary(title)
            if not s or not self._text_ok(s["text"]):
                continue
            if rank == 40:                                          # acronym route: the article must say "(ACRONYM)"
                if not any(re.search(r"\(\s*" + re.escape(a) + r"\s*\)", s["raw"][:500]) for a in acr):
                    continue
                rest = sig - {_stem(a.lower()) for a in acr}
                blob = {_stem(w) for w in _words(title + " " + s["raw"][:500])}
                if rest and not rest <= blob:
                    continue
                if not rest and not (ctx & {_stem(w) for w in _words(s["raw"][:600])}) and _vocab_hits(s["raw"]) < 3:
                    continue
            overlap = len(ctx & {_stem(w) for w in _words(s["raw"][:700])})
            key = (rank, overlap, _vocab_hits(s["raw"]))
            if best_key is None or key > best_key:
                best, best_key = s, key
        if best:
            return {"text": best["text"], "source": "Wikipedia — " + best["title"], "url": best["url"]}
        return None

    # ---------------------------------------------------------- 3. general web
    def _web_search(self, term, context):
        if not self.search_fn:
            return None
        base = clean_term(term)
        sig = _significant(base)
        if not sig:
            return None
        q = f'what is "{base}" definition KPI metric'
        self.requests_made += 1
        time.sleep(self.delay)
        try:
            results = self.search_fn(q) or []
        except Exception as e:
            self._down(e)
            return None
        self.failures = 0
        fallback_pages = []
        for r in results:
            full = re.sub(r"\s+", " ", _html.unescape(r.get("body", "") or "")).strip()
            body = _strip_question(full)
            was_question = body != full
            url = r.get("href") or r.get("url") or ""
            host = urllib.parse.urlparse(url).netloc.replace("www.", "")
            blow = full.lower()
            if not all(w in blow for w in sig[:2]):
                fallback_pages.append((url, host))
                continue
            text = _first_sentences(body)
            if (len(text) >= 60 and not _MARKETING_RE.search(body)
                    and (_DEFN_RE.search(text[:240]) or was_question) and _vocab_hits(text) >= 1):
                return {"text": text, "source": host or "web search", "url": url}
            fallback_pages.append((url, host))
        for url, host in fallback_pages[:2]:                    # the snippet was no definition: read the page itself
            if not url or not url.startswith("http"):
                continue
            s = self._page_definition(url, sig)
            if s:
                return {"text": s, "source": host or "web page", "url": url}
        return None

    def _page_definition(self, url, sig):
        self.requests_made += 1
        time.sleep(self.delay)
        try:
            raw = self.fetch_text(url)
        except urllib.error.HTTPError:
            return None
        except Exception as e:
            self._down(e)
            return None
        raw = re.sub(r"(?is)<(script|style|nav|footer|header|aside|form)\b.*?</\1>", " ", raw)
        text = _html.unescape(re.sub(r"(?s)<[^>]+>", " ", raw))
        for s in _sentences(text):
            low = s.lower()
            if (60 <= len(s) <= 320 and all(w in low for w in sig[:2]) and _DEFN_RE.search(s[:160])
                    and not _MARKETING_RE.search(s) and _vocab_hits(s) >= 1 and s[:1].isupper()):
                return _strip_question(s)
        return None

    @staticmethod
    def _ddgs_search(query):
        try:
            from ddgs import DDGS
        except Exception:
            try:
                from duckduckgo_search import DDGS
            except Exception:
                return []
        return list(DDGS().text(query, max_results=6))

    # ---------------------------------------------------------- housekeeping
    def _save(self):
        if not self.cache_path:
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps({"_v": CACHE_VERSION, "terms": self.cache}, indent=1,
                                                  ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass


class _NetworkDown(Exception):
    pass
