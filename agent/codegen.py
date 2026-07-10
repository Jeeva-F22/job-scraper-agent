"""Stage 5: Code Generator. Writes the standalone Python scraper file from the plan.

The generated script must run with zero LLM calls, using only stdlib + requests +
beautifulsoup4/lxml. This module never writes site-specific logic itself -- it only
asks the LLM to, and the LLM's plan-following code is what ends up on disk.
"""
import os
import re as _stdlib_re  # only used here to strip markdown code fences from the LLM's own reply, not for data extraction

OUTPUT_SCHEMA_DOC = """
Each output line must be a JSON object with exactly these keys:
{
  "title": str|null,
  "job_id": str|null,
  "location": {"city": str|null, "state": str|null, "country": str|null, "country_code": str|null},
  "url": str|null,
  "apply_url": str|null,
  "date_posted": str|null,   // ISO 8601 date if parseable, else null
  "date_posted_text": str|null,  // raw text always preserved if present, even if unparseable
  "job_description": str|null,
  "employment_type": str|null,
  "work_type": str|null,
  "salary_range": str|null
}
"""

_SYSTEM_BASE = """You are the Code Generator for an autonomous scraper-writing system. Write ONE standalone,
self-contained Python 3 script implementing EXACTLY the scrape plan you are given. The script will be
executed with zero human review and zero LLM calls at runtime -- it must be correct and defensive.

Hard requirements:
1. {imports_rule}
2. Field extraction: CSS selectors (via BeautifulSoup, or Playwright locators if using Playwright) or
   JSON-path-style dict/list traversal ONLY.
   NEVER use the `re` module or any regex for extracting field values from page/response content.
   (You may use `re` for nothing -- avoid importing it entirely.)
   HTML PARSING: never call `BeautifulSoup(x, "lxml")` directly -- lxml's recovery mode silently DROPS whole
   subtrees on some real career pages (verified: it returned zero <input> elements from a page whose raw text
   held four, one containing the entire job list as embedded JSON). Include this helper VERBATIM and use it
   for every HTML parse in the script:
   ```python
   def parse_html(text):
       if isinstance(text, bytes):
           text = text.decode("utf-8", errors="replace")
       text = text or ""
       soup = BeautifulSoup(text, "lxml")
       for tag in ("input", "script", "a"):
           raw_count = text.count("<" + tag)
           if raw_count >= 2 and len(soup.find_all(tag)) < raw_count // 2:
               return BeautifulSoup(text, "html.parser")
       return soup
   ```
   ALSO: some career sites (e.g. Zoho Recruit-style boards) embed the ENTIRE job list as JSON inside a hidden
   `<input value="...">` element (HTML-escaped) in the RAW page HTML -- if the plan/evidence mentions such an
   embedded blob (source_type embedded_json with an input/hidden container), read it with
   `json.loads(soup.find("input", id=<the id from evidence>).get("value"))` -- BeautifulSoup already unescapes
   the attribute -- and take every field (title, city/state/country, id, description, dates) from that
   structured data directly instead of scraping visible DOM elements.
3. Any field not structurally present in the source must be written as JSON `null`. Never guess, never
   parse it out of free text, never leave a placeholder string. If a text field (e.g. job_description) comes
   through HTML-entity-escaped (e.g. `&lt;div&gt;`, `&amp;`), run it through stdlib `html.unescape` before
   writing it out.
4. India filtering: use ONLY structural fields (country / country_code / a server-side API filter param)
   as specified in the plan. Never substring-match the job description to decide India-ness.
   Location strings vary in shape across companies ("Bengaluru, India", "Bengaluru", "New York, NY, United
   States", "Bengaluru; Gurugram"). You MUST include this EXACT helper function verbatim in every generated
   script that parses a free-text location field, and call it for every job (adapt only the dict contents if
   you find more India cities in the actual data -- keep the same two-step logic and comma-splitting behavior):

   ```python
   _INDIA_CITY_FALLBACK = {
       "bengaluru": "Bengaluru", "bangalore": "Bangalore", "mumbai": "Mumbai", "delhi": "Delhi",
       "new delhi": "New Delhi", "gurugram": "Gurugram", "gurgaon": "Gurgaon", "noida": "Noida",
       "hyderabad": "Hyderabad", "chennai": "Chennai", "pune": "Pune", "kolkata": "Kolkata",
       "ahmedabad": "Ahmedabad",
   }

   def resolve_location(location_raw):
       # returns (city, state, country, country_code) -- all None if unresolvable, never guessed.
       if not location_raw:
           return (None, None, None, None)
       first_segment = location_raw.split(";")[0].strip()  # some platforms join multiple locations with ';'
       parts = [p.strip() for p in first_segment.split(",")]
       if len(parts) >= 2:
           # explicit "City, [State,] Country" format -- last segment is the country
           city = parts[0] or None
           state = parts[1] if len(parts) >= 3 else None
           country_raw = parts[-1]
           if country_raw.lower() in ("india", "in"):
               return (city, state, "India", "IN")
           return (city, state, country_raw or None, None)
       # no comma: bare city name -- only resolve via the small generic fallback dict, never guess otherwise
       bare = first_segment.lower()
       if bare in _INDIA_CITY_FALLBACK:
           return (_INDIA_CITY_FALLBACK[bare], None, "India", "IN")
       return (None, None, None, None)
   ```

   Call `resolve_location(location_raw)` to get city/state/country/country_code for every job, then keep only
   jobs where country_code == "IN" (or country == "India") for the India filter. Do not write your own
   from-scratch location-parsing logic instead of this -- use this function. This dict is generic world-knowledge infrastructure you author yourself, not a per-domain
   branch, so it's fine to include even though the plan doesn't spell out every city.
5. Output schema (one JSON object per line, JSONL, UTF-8):
""" + OUTPUT_SCHEMA_DOC + """
6. Pagination must fully traverse all pages per the plan's exact stop condition -- do not stop at page 1.
   MANDATORY UNIVERSAL TERMINATION RULE (applies no matter the source_type or pagination_scheme): a page/
   response is "done" when it contributes ZERO records not already in your dedupe/seen set -- NEVER rely on
   "response was empty" alone as the stop condition. Many real sources (a misfiring page param, a source
   that ignores pagination entirely, an API that clamps to page 1 for any page number) return the SAME
   non-empty content for every page number forever; an emptiness-only check will then loop until the page
   cap and the sandbox/timeout kills the run. Concretely: track a `seen` set of dedupe keys across the whole
   run, and after processing each page compute `new_count = number of this page's records whose dedupe key
   was NOT already in seen`; if `new_count == 0`, stop pagination immediately (do not just skip -- break the
   loop). This applies equally to JSON-API pagination, embedded-JSON pages with a page/offset param, and
   rendered/scrolled pages.
7. Deduplicate on the plan's dedupe_key (job_id or url) before writing output -- never emit the same job twice.
8. Normalize all URLs to absolute form using `urllib.parse.urljoin` (stdlib, not regex).
9. Dates: try `datetime.fromisoformat` / documented API date formats via `datetime.strptime` with EXPLICIT
   known format strings (not regex) as typed parsing; on failure keep `date_posted_text` and set
   `date_posted` to null. Never invent a date.
10. HTTP requests must retry with exponential backoff (e.g. up to 3 retries, sleeping 1s/2s/4s) on 429 or
    5xx responses, and MUST send a COMPLETE, realistic browser User-Agent -- not a bare "Mozilla/5.0".
    Many corporate WAFs return 403 Forbidden to minimal/blank User-Agents. Use exactly this header set:
      HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
      }
    Treat 403 like a retryable block: retry with backoff; if it still 403s after retries, skip that one job
    (log to stderr) rather than treating it as fatal. When fetching many detail pages in a loop, sleep briefly
    (~0.3-0.5s) between requests to avoid rate-based blocking. If ALL detail fetches 403 (WAF hard-block), fall
    back to `firecrawl_render(job_url)` for the detail page (Firecrawl bypasses the WAF) before giving up.
    If any query/body param is boolean-flavored
    (e.g. a `content=true` flag), pass it as the literal string `'true'`/`'false'`, NOT a Python `True`/`False` --
    `requests` serializes Python booleans as `'True'`/`'False'` in query strings, which most APIs silently
    ignore, silently degrading your response.
11. The script must accept an optional CLI arg for the output path, defaulting to `output.jsonl` in the
    script's own directory. It must always produce this file, even if zero India jobs are found (write an
    empty file in that case) -- an empty JSONL is a VALID, SUCCESSFUL result, not an error.
12. On any unrecoverable error (source unreachable, blocked, schema totally changed), the script must
    still write whatever valid output file it can (even if empty) and print a clear one-line error summary
    to stderr, then exit non-zero -- it must never hang indefinitely or crash without writing output.
13. Start the file with a module docstring that names the source_type + pagination_scheme AND gives the exact
    standalone run command, e.g.:
    '''
    Standalone job scraper for <domain> (India roles). Generated by the agent; runs with NO LLM calls.
    Run:  python scraper.py [output.jsonl]
    <If this scraper uses firecrawl_render, add:> Requires env var FIRECRAWL_API_KEY (renders JS/bot-protected
    pages). Set it first:  Windows:  set FIRECRAWL_API_KEY=fc-...   Linux/Mac:  export FIRECRAWL_API_KEY=fc-...
    source_type=<...>, pagination=<...>.
    '''
14. No network calls to any LLM API. If the script uses firecrawl_render, it reads FIRECRAWL_API_KEY from env;
    if that var is missing, print a clear one-line instruction to stderr telling the user to set it (with the
    export/set command) and exit non-zero -- do not fail with a confusing traceback.
{playwright_rules}
Return ONLY the raw Python source code. No markdown fences, no commentary before or after."""

_IMPORTS_RULE_HTTP = "Only stdlib + `requests` + `bs4`/`lxml` (already installed) may be imported. No other third-party libs."
_IMPORTS_RULE_BROWSER = (
    "Only stdlib + `requests` + `bs4`/`lxml` (already installed) may be imported. This source needs JS "
    "rendering and/or bypasses simple bot protection, so for the pages that require rendering you MUST use "
    "the Firecrawl scrape HTTP API (an approved rendering service -- NOT an LLM, so it satisfies the "
    "'no LLM calls at runtime' rule) via `requests`, using the helper below. Do NOT import playwright/"
    "selenium. Plain `requests` is still used directly for any page that returns full content without JS."
)
_FIRECRAWL_RULES = """15. RENDERING VIA FIRECRAWL, WITH A JINA READER FALLBACK. Headless browsers get blocked by bot
    protection (e.g. Cloudflare) on some of these sites; Firecrawl's rendering service handles JS + bot
    challenges reliably. Firecrawl occasionally returns an empty render for a given page even though the
    page itself is fine (transient rendering-service issue, not a site problem) -- so ALSO include a second,
    keyless fallback renderer (Jina AI Reader, https://r.jina.ai/, needs no API key for basic use) that is
    tried automatically when Firecrawl comes back empty. Include this helper VERBATIM and use it for any page
    that needs rendering:

    ```python
    import os, requests, time, sys

    def _firecrawl_render_once(url, actions):
        key = os.environ.get("FIRECRAWL_API_KEY")
        if not key:
            return "", []
        for attempt in range(3):
            try:
                r = requests.post(
                    "https://api.firecrawl.dev/v1/scrape",
                    headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
                    json={"url": url, "formats": ["html", "links"], "onlyMainContent": False, "actions": actions},
                    timeout=120,
                )
                data = r.json()
                if data.get("success"):
                    d = data.get("data", {})
                    html = d.get("html", "") or ""
                    if html.strip():
                        return html, d.get("links", []) or []
            except requests.RequestException:
                pass
            time.sleep(2 ** attempt)
        return "", []

    def _jina_render_once(url):
        # Keyless fallback renderer -- returns HTML (not markdown) via the X-Return-Format header, so the
        # same BeautifulSoup/CSS-selector extraction code works on its output unchanged.
        try:
            r = requests.get(
                "https://r.jina.ai/" + url,
                headers={"X-Return-Format": "html",
                         "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                timeout=45,
            )
            if r.status_code == 200 and r.text.strip():
                return r.text, []
        except requests.RequestException:
            pass
        return "", []

    def firecrawl_render(url, scroll_times=6, wait_ms=3500):
        # Renders a JS/bot-protected page and returns (html, links). Requires FIRECRAWL_API_KEY in env.
        # Falls back to Jina Reader (no key needed) if Firecrawl returns nothing usable.
        key = os.environ.get("FIRECRAWL_API_KEY")
        if not key:
            print("FIRECRAWL_API_KEY not set; cannot render via Firecrawl -- trying Jina fallback", file=sys.stderr)
            return _jina_render_once(url)
        # Some SPAs load job data via an async XHR that fires AFTER the initial render settles -- a
        # too-short wait captures only the pre-hydration shell (small HTML). Retry with a longer wait
        # before falling back, since the same URL is known to render fully given enough time.
        best_html, best_links = "", []
        for wait in (wait_ms, wait_ms * 2, wait_ms * 4):
            actions = [{"type": "wait", "milliseconds": wait}]
            for _ in range(scroll_times):
                actions.append({"type": "scroll", "direction": "down"})
                actions.append({"type": "wait", "milliseconds": 1200})
            html, links = _firecrawl_render_once(url, actions)
            if len(html) > len(best_html):
                best_html, best_links = html, links
            if len(html) > 40000:  # rich content, not just an app shell -- good enough, stop retrying
                return html, links
        if best_html.strip():
            return best_html, best_links
        print("Firecrawl render was empty/shell-only after retries; trying Jina Reader fallback", file=sys.stderr)
        return _jina_render_once(url)
    ```
{two_stage_rules}"""

_TWO_STAGE_RULES = """16. TWO-STAGE SCRAPER (source_type=rendered_list_ssr_detail): the job LIST needs rendering, but each
    individual job-DETAIL page is plain server HTML reachable with `requests`. Implement exactly this:
    Stage A (render the list): call `html, links = firecrawl_render(list_url)`. Collect job-detail URLs from
      `links` (and/or by parsing `html` with BeautifulSoup). CRITICAL -- do NOT guess a CSS class like
      `a.job-link`. Instead filter `links` by the HREF SUBSTRING common to the real job_detail_url_samples in
      the evidence (e.g. samples `.../careers/job/<slug>/<id>` share the segment `/careers/job/`): keep links
      whose URL contains that segment. Deduplicate; normalize to absolute with urljoin. If zero such links are
      found, write an empty output file and exit 0 (genuinely empty), never hang.
    Stage B (requests, no rendering): for each detail URL, `requests.get` it (retry/backoff + realistic UA)
      and parse the SSR HTML with BeautifulSoup to extract title, location, description, date, etc. via CSS
      selectors / embedded structured data (JSON-LD). Run resolve_location on the location text and keep only
      India jobs.
      MANDATORY: wrap the ENTIRE per-job extraction body in `try/except Exception as e:` that prints the URL
      and error to stderr and `continue`s to the next job. A `select_one(...)` that finds nothing returns
      None, and `.get_text()` on it raises -- that must NOT abort the whole run. Use a safe helper like
      `def sel_text(soup, css):\n    el = soup.select_one(css)\n    return el.get_text(strip=True) if el else None`
      for every field so missing elements yield None instead of crashing. Avoid the `:contains()` pseudo-class
      (deprecated/fragile); to find a labeled element, iterate candidates and check `.get_text()` in Python.
    PERFORMANCE: use a SHORT per-detail-request timeout (`requests.get(..., timeout=12)`) and at most 1 retry
    on detail pages, so a few slow pages can't blow the total budget. The whole script must finish under ~250s
    even with 30-50 detail pages. Keep the Firecrawl list render to a modest scroll count (the helper default
    is fine). Do not add long fixed sleeps.
17. If source_type=spa_needs_browser (both list and detail need rendering): use firecrawl_render for the list
    to get job-detail links, and firecrawl_render again for each detail page (or parse everything from the
    rendered list html if all fields are present there). Same India filter + schema rules apply.
18. PAGINATION SCHEME MUST MATCH THE ACTUAL CODE -- this is a common bug: if pagination_scheme is
    "load_more" or "infinite_scroll" (a client-side button/scroll trigger, NOT a URL parameter), you MUST NOT
    construct synthetic URLs like `?p=2`, `?page=3`, `&offset=20` and re-fetch/re-render them expecting new
    content -- the server ignores an unrecognized param and returns the SAME page every time, and re-rendering
    the identical URL repeatedly via Firecrawl can even yield slightly different scroll-timing snapshots of the
    SAME underlying jobs, producing near-duplicate "jobs" with different job_ids. Instead: call
    `firecrawl_render(list_url, scroll_times=15, wait_ms=4000)` EXACTLY ONCE with an increased scroll_times to
    load as much content as a single deep-scroll pass surfaces, extract every job card from that ONE render,
    and stop -- do not loop over fabricated page numbers. If job_id is not present as a real HTML attribute on
    the card, derive a stable per-job dedupe key from `(title, location_raw)` and dedupe within that single
    render's card list before writing output -- never treat two fetches/renders of the same URL as two
    different pages of results.
"""

_DETAIL_EXTRACTION_RULES = """18. DETAIL-PAGE FIELD EXTRACTION (use the REAL detail HTML sample + JSON-LD provided to choose selectors).
    JSON-LD comes in MANY shapes (a single dict, a list of dicts, an @graph, and there can be MULTIPLE
    <script type="application/ld+json"> tags per page). Do NOT assume it's a list. Include this helper VERBATIM
    and use it to read JSON-LD fields robustly:
    ```python
    def ldjson_objects(soup):
        objs = []
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(tag.string or "")
            except (json.JSONDecodeError, TypeError):
                continue
            items = data if isinstance(data, list) else [data]
            for it in items:
                if isinstance(it, dict):
                    objs.append(it)
                    if isinstance(it.get("@graph"), list):
                        objs.extend(x for x in it["@graph"] if isinstance(x, dict))
        return objs

    def ldjson_get(soup, *keys):
        for o in ldjson_objects(soup):
            for k in keys:
                if o.get(k):
                    return o[k]
        return None
    ```
    - title: `ldjson_get(soup, "headline", "title", "name")`, else the page's main `h1` via sel_text. NEVER
      select a field LABEL as the title (a value equal to/ending with "Location:", "Posted:", "Apply now" is
      wrong -> fall back to h1). Strip a trailing " | <Company>" suffix if the JSON-LD name includes it.
    - job_id: if there is no explicit id field/attribute, derive it from the detail URL -- the last numeric
      path segment is the stable requisition id (e.g. `.../job/<slug>/1411674133` -> "1411674133"). Use plain
      string ops on the URL (split on '/'), not regex.
    - location: PREFER the JSON-LD JobPosting's structured address when the sample shows one -- it is the most
      reliable source. Include this helper VERBATIM and try it FIRST:
    ```python
    def ldjson_location(soup):
        for o in ldjson_objects(soup):
            if o.get("@type") == "JobPosting" and o.get("jobLocation"):
                locs = o["jobLocation"] if isinstance(o["jobLocation"], list) else [o["jobLocation"]]
                for l in locs:
                    addr = (l or {}).get("address") or {}
                    if isinstance(addr, dict) and (addr.get("addressLocality") or addr.get("addressCountry")):
                        city = addr.get("addressLocality") or None
                        state = addr.get("addressRegion") or None
                        country_raw = str(addr.get("addressCountry") or "").strip()
                        if country_raw.upper() in ("IN", "IND", "INDIA"):
                            return (city, state, "India", "IN")
                        return (city, state, country_raw or None, None)
        return None
    ```
      Only if ldjson_location returns None, do NOT jump straight to a guessed CSS class list (`.location`,
      `.job-location`, etc.) as the primary method -- guessed classes very often don't match the real DOM
      (different ATS templates use different, unpredictable class names) and silently return None, which
      then makes country_code None, which then makes the India filter silently drop every real job with NO
      error printed -- a scraper that "runs clean" but writes zero jobs despite real jobs existing on the
      page. Instead, ALWAYS use this class-agnostic structural fallback FIRST (include it VERBATIM), which
      finds location text by testing candidates against resolve_location itself rather than by CSS class:
    ```python
    def find_structural_location(container):
        if container is None:
            return None
        for el in container.find_all(["span", "div", "p", "li", "td", "h1", "h2", "h3"]):
            text = el.get_text(" ", strip=True)
            if not text or len(text) > 100:
                continue
            candidate = text.split(":", 1)[-1].strip() if ":" in text else text
            _, _, country, _ = resolve_location(candidate)
            if country:
                return candidate
        return None
    ```
      Try `find_structural_location(container_or_soup)` before (or alongside) any guessed-CSS-class attempt;
      only use a guessed class as a last resort if the structural scan also returns None. This applies to
      BOTH list-card location extraction and detail-page location extraction -- anywhere resolve_location is
      called on a piece of extracted text.
    - INDIA FILTER (MANDATORY, even when the list URL is already India-filtered server-side): after resolving
      the location, include this exact guard before appending the job:
      `if country_code != "IN": continue`
      A job whose location could not be resolved (country_code is None) must be SKIPPED, not written with
      nulls -- unverifiable-location jobs are not India jobs.
    - job_description: pick the LARGEST main body text block by iterating the candidate sections/blocks (e.g.
      all `.richtext` / article sections), measuring `len(el.get_text())`, and choosing the max -- explicitly
      SKIP any block whose text starts with a short label like "Location:". Never reuse the location element
      as the description. html.unescape the result. (Watch out: do not shadow the stdlib `html` module with a
      local variable named `html` -- name rendered-HTML variables `page_html`/`list_html` instead.)
    - Always `html.unescape(...)` text fields that may contain entities (titles too, e.g. "R&amp;C" -> "R&C").
    - date/employment_type/etc.: use `ldjson_get(soup, "datePublished", "datePosted")` /
      `ldjson_get(soup, "employmentType")` when present, else a clearly labeled element; null if absent.
"""


_HTTP_TWO_STAGE_RULES = """15. HTTP-ONLY TWO-STAGE SCRAPER (SSR list + SSR detail pages, NO rendering service needed):
    Stage A (requests): GET the verified list/search URL from the evidence (endpoint_url) EXACTLY as given --
      the FIRST list fetch must be that URL with ZERO modifications (no extra path segments, no changed params).
      Collect job-detail links with EXACTLY this helper, included verbatim (do NOT guess CSS classes for the
      links -- this href-pattern collector is what was verified against the real page):

      def collect_job_links(soup, page_url):
          urls = []
          for a in soup.find_all("a", href=True):
              h = a["href"]
              tail = h.rstrip("/").split("/")[-1]
              if any(k in h.lower() for k in ("/job/", "/jobs/", "/position/", "/vacancy/", "/opening/")) \\
                      or (tail.isdigit() and len(tail) >= 6):
                  u = urljoin(page_url, h)
                  if u not in urls:
                      urls.append(u)
          return urls

      PAGINATION: for page N>1, ONLY add/replace a QUERY param on the verified URL (e.g. ?p=2 or &p=2) --
      NEVER append a path segment: the verified URL's path may already end in numeric ids that are NOT page
      numbers (a facet/location id, not a page). MANDATORY termination: stop as soon as a page adds ZERO links
      not already in the running set -- do NOT just check "page returned an empty list", because a site that
      ignores an unrecognized pagination param (or that has no real query-param pagination at all) will keep
      returning the SAME links forever and an emptiness-only check loops until the run times out. Use this
      exact loop shape:
      ```python
      all_urls, page_number = [], 1
      while page_number <= 120:
          page_url = f"{base_url}{'&' if '?' in base_url else '?'}p={page_number}"
          resp = fetch_with_retries(page_url, HEADERS)
          if not resp or resp.status_code != 200:
              break
          links = collect_job_links(parse_html(resp.text), page_url)
          new_links = [u for u in links if u not in all_urls]
          if not new_links:
              break
          all_urls.extend(new_links)
          page_number += 1
      ```
      If evidence/pagination_details says there is NO real pagination (single results page, e.g. a
      already-facet-filtered small results page), skip the loop entirely and just fetch base_url once.
    Stage B (requests): fetch each detail URL, extract fields per the plan + the real detail-HTML sample,
      run resolve_location, keep only India jobs. MANDATORY: wrap each job's extraction in try/except that
      logs to stderr and continues -- one bad page must not abort the run. Use the sel_text helper pattern
      (`el = soup.select_one(css); return el.get_text(strip=True) if el else None`).
    Even if the list URL is already India-filtered server-side, STILL verify each job's location structurally
    (resolve_location) before writing it -- server-side filters can include near-miss matches.
    SCALE GUARD: if the list is NOT India-filtered server-side and holds more than ~60 job links total, do NOT
    fetch every detail page. Prefilter detail URLs whose lowercase path contains an India city slug (build the
    slugs from the _INDIA_CITY_FALLBACK keys: "mumbai", "bengaluru", "bangalore", "new-delhi", "delhi",
    "hyderabad", "pune", "chennai", "kolkata", "gurgaon", "gurugram", "noida", "ahmedabad" -- plain substring
    checks on the URL path, many career sites embed the city as a path segment like /en/job/<city>/...), and
    fetch only those. Log to stderr how many were skipped by this prefilter. Cap pagination at ~120 pages.
"""


def _needs_browser(re_result):
    return bool(re_result.get("requires_js_execution")) or \
        re_result.get("source_type") in ("spa_needs_browser", "rendered_list_ssr_detail")


def _build_system(re_result):
    needs_browser = _needs_browser(re_result)
    imports_rule = _IMPORTS_RULE_BROWSER if needs_browser else _IMPORTS_RULE_HTTP
    if needs_browser:
        render_rules = _FIRECRAWL_RULES.replace("{two_stage_rules}", _TWO_STAGE_RULES) + _DETAIL_EXTRACTION_RULES
    elif re_result.get("source_type") == "html_ssr" and re_result.get("job_detail_url_samples"):
        render_rules = _HTTP_TWO_STAGE_RULES + _DETAIL_EXTRACTION_RULES
    else:
        render_rules = ""
    # NOTE: plain str.replace, not .format() -- OUTPUT_SCHEMA_DOC contains literal JSON braces
    # that .format() would misinterpret as placeholders.
    return _SYSTEM_BASE.replace("{imports_rule}", imports_rule).replace("{playwright_rules}", render_rules)


def _strip_fences(text):
    text = text.strip()
    if text.startswith("```"):
        text = _stdlib_re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = _stdlib_re.sub(r"\n```$", "", text)
    return text


def generate(plan, discovery_result, re_result, domain, llm, trace, out_dir, prior_code_hint=None, repair_context=None):
    trace.stage("codegen", f"Generating scraper for {domain}")
    system = _build_system(re_result)
    # Keep the bulky HTML sample out of the compact re_result dump; present it separately, clearly labeled.
    re_for_prompt = {k: v for k, v in re_result.items()
                     if k not in ("detail_page_html_sample", "detail_page_ldjson")}
    user_parts = [
        f"Target domain: {domain}",
        f"Careers URL: {discovery_result.get('careers_url')}",
        f"Scrape plan:\n{plan}",
        f"Reverse-engineering evidence (for exact endpoint/params/pagination fields):\n{re_for_prompt}",
    ]
    if re_result.get("endpoint_url"):
        user_parts.append(
            f"MANDATORY LIST URL: fetch the job list from EXACTLY this verified URL (add only a pagination "
            f"param like &p=N when paginating):\n{re_result['endpoint_url']}\n"
            "Do NOT modify its query params, do NOT merge it with any URL from a prior-scraper hint, and do "
            "NOT add extra filter params -- it was verified working exactly as given."
        )
    if re_result.get("detail_page_html_sample"):
        user_parts.append(
            "REAL job page HTML sample (cleaned; scripts/styles stripped, tags+classes kept) from "
            f"{re_result.get('detail_page_sample_url')}. Derive your CSS selectors for title / location / "
            "description / date / employment_type / job_id from THIS ACTUAL STRUCTURE -- do NOT guess class "
            "names like `.job-title`/`.job-location`; use the real tags/classes you see here (and prefer "
            "JSON-LD / a specific unique class/tag). If a field is genuinely absent, output null:\n"
            f"```html\n{re_result['detail_page_html_sample']}\n```"
        )
    if re_result.get("detail_page_ldjson"):
        user_parts.append(f"JSON-LD structured data found on that job page:\n{re_result['detail_page_ldjson']}")
    if prior_code_hint:
        user_parts.append(
            "A previously successful scraper for a domain on the SAME platform is provided below as a "
            "STARTING-POINT HINT ONLY. Adapt it to this domain's actual verified endpoint/plan above -- do "
            "not blindly reuse endpoint URLs or IDs from it, they belong to a different company:\n"
            f"```python\n{prior_code_hint}\n```"
        )
    if repair_context:
        user_parts.append(
            "IMPORTANT -- this is a REPAIR pass. The previous version of this script failed validation:\n"
            f"{repair_context}\nFix the root cause, don't just patch symptoms."
        )
    user = "\n\n".join(user_parts)
    code = llm.complete("codegen", system, user, trace=trace, temperature=0.1)
    code = _strip_fences(code)

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "scraper.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(code)
    trace.tool_call("codegen", "write_file", {"path": path}, {"bytes": len(code)})
    return path, code
