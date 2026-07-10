"""Stage 3: Reverse-engineer the actual data source + pagination scheme.

This is the highest-value stage. The LLM works through the same decision chain
a human engineer would: is there embedded JSON already? A discoverable REST/GraphQL
endpoint? Only if nothing else works does it fall back to treating the rendered
HTML itself as the source. All endpoint URLs are *hypotheses the LLM proposes and
then verifies by calling the tool* -- never hardcoded per-domain, and never trusted
without a real HTTP round-trip confirming it returns job data.
"""
import json as _json

from . import tools

TOOLS = [
    {"type": "function", "function": {
        "name": "fetch_rendered",
        "description": "Fetch a URL with JS rendering, returns markdown/html/links/metadata.",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    }},
    {"type": "function", "function": {
        "name": "fetch_raw",
        "description": "Raw GET (no JS), returns response text/status/headers. Use for JS bundle files or suspected API endpoints.",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    }},
    {"type": "function", "function": {
        "name": "fetch_json",
        "description": "GET a URL expecting a JSON response (candidate API endpoint). Optional query params.",
        "parameters": {
            "type": "object",
            "properties": {"url": {"type": "string"}, "params": {"type": "object"}},
            "required": ["url"],
        },
    }},
    {"type": "function", "function": {
        "name": "post_json",
        "description": "POST a JSON body to a URL expecting JSON back (candidate REST/GraphQL endpoint).",
        "parameters": {
            "type": "object",
            "properties": {"url": {"type": "string"}, "body": {"type": "object"}},
            "required": ["url", "body"],
        },
    }},
    {"type": "function", "function": {
        "name": "fetch_rendered_interactive",
        "description": "Fetch a URL with JS rendering PLUS scroll+wait actions, to surface AJAX/XHR-loaded or infinite-scroll content that a plain render misses (e.g. a job search widget whose results load after page load, or a 'load more' page). Slower -- use only when fetch_rendered showed a search/results UI but no actual job rows.",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    }},
    {"type": "function", "function": {
        "name": "extract_hydration_json",
        "description": "Given a URL, fetch it and extract inline JSON blobs: hydration state (__NEXT_DATA__, __NUXT__, __INITIAL_STATE__, __APOLLO_STATE__) AND JSON embedded in hidden <input value=\"...\"> elements (some career boards, e.g. Zoho Recruit-style, ship the ENTIRE job list this way in the raw HTML -- keys look like 'hidden_input:jobs'). If a hidden_input blob contains the job records, that is an embedded_json source: report source_type=embedded_json with the input element's id in pagination_details/evidence.",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    }},
    {"type": "function", "function": {
        "name": "grep_text",
        "description": "Fetch a URL (e.g. a JS bundle) and return up to 5 snippets of text surrounding a given substring, to spot API base URLs / route strings.",
        "parameters": {
            "type": "object",
            "properties": {"url": {"type": "string"}, "substring": {"type": "string"}},
            "required": ["url", "substring"],
        },
    }},
    {"type": "function", "function": {
        "name": "finish",
        "description": "Report the discovered data source and pagination scheme.",
        "parameters": {
            "type": "object",
            "properties": {
                "source_type": {
                    "type": "string",
                    "description": "one of: embedded_json, rest_api, graphql_api, html_ssr (the job LIST page is "
                                    "plain server HTML fetchable with requests -- put the verified list/search URL "
                                    "(ideally the India-filtered one) in endpoint_url with http_method GET; if fields "
                                    "must come from per-job detail pages, also fill job_detail_url_samples + "
                                    "detail_pages_are_ssr), "
                                    "rendered_list_ssr_detail (the LIST of jobs only appears after JS render so a "
                                    "browser is needed to collect the job-detail links, BUT each individual "
                                    "job-detail page is plain server HTML scrapable with requests -- prefer this over "
                                    "spa_needs_browser whenever detail pages are SSR), spa_needs_browser (both the "
                                    "list AND the detail content require a live browser), not_found",
                },
                "endpoint_url": {"type": ["string", "null"]},
                "http_method": {"type": ["string", "null"], "description": "GET or POST"},
                "request_body_template": {"type": ["object", "null"], "description": "JSON body template for POST/GraphQL, with pagination placeholder noted"},
                "request_params_template": {"type": ["object", "null"]},
                "response_job_list_path": {"type": ["string", "null"], "description": "dotted path to the job array in the JSON response, e.g. 'jobPostings' or 'data.jobs.nodes'"},
                "sample_job_record": {"type": ["string", "null"], "description": "one real, verified example job record (as compact JSON text) copied from an actual tool response you received -- so the architect can see the exact field shape (e.g. what the location field actually looks like: bare city name vs 'City, Country' vs structured object)."},
                "job_detail_url_samples": {
                    "type": "array", "items": {"type": "string"},
                    "description": "For html_ssr / rendered_list_ssr_detail sources: 2-4 REAL individual job-detail page URLs you actually saw in a tool result's links (e.g. https://site/careers/job/<slug>/<id>). Empty if the source is a JSON API. Used to derive the list-link pattern and to fetch per-job detail pages.",
                },
                "detail_pages_are_ssr": {
                    "type": "boolean",
                    "description": "True if you fetched one of the job_detail_url_samples with plain fetch_raw (no JS) and confirmed the job title/location/description are present in the raw HTML. This means detail pages can be scraped with requests+bs4 even if the LIST page needed a browser.",
                },
                "pagination_scheme": {
                    "type": "string",
                    "description": "one of: offset, cursor, page_number, infinite_scroll, token, load_more, graphql_cursor, none, unknown",
                },
                "pagination_details": {"type": "string"},
                "requires_js_execution": {
                    "type": "boolean",
                    "description": "true only if you confirmed (via fetch_rendered_interactive) that job data appears "
                                    "solely after client-side JS/AJAX execution, with NO discoverable underlying API "
                                    "-- meaning a plain HTTP scraper cannot reproduce it and a real browser is required "
                                    "at scrape time.",
                },
                "confidence": {"type": "number"},
                "evidence": {"type": "array", "items": {"type": "string"}},
                "reasoning": {"type": "string"},
            },
            "required": ["source_type", "endpoint_url", "http_method", "request_body_template",
                         "request_params_template", "response_job_list_path", "sample_job_record",
                         "job_detail_url_samples", "detail_pages_are_ssr", "pagination_scheme",
                         "pagination_details", "requires_js_execution", "confidence", "evidence", "reasoning"],
        },
    }},
]


def _executor():
    def run(name, args):
        if name == "fetch_rendered":
            return tools.firecrawl_scrape(args.get("url", ""))
        if name == "fetch_rendered_interactive":
            return tools.firecrawl_scrape_interactive(args.get("url", ""))
        if name == "fetch_raw":
            return tools.http_get(args.get("url", ""))
        if name == "fetch_json":
            return tools.http_get_json(args.get("url", ""), params=args.get("params"))
        if name == "post_json":
            return tools.http_post_json(args.get("url", ""), body=args.get("body"))
        if name == "extract_hydration_json":
            r = tools.http_get(args.get("url", ""))
            html = r.get("text", "") if r.get("ok") else ""
            if not html:
                rendered = tools.firecrawl_scrape(args.get("url", ""))
                html = rendered.get("html", "")
            blobs = tools.extract_json_blobs(html)
            return {"blobs_found": list(blobs.keys()), "preview": {k: str(v)[:1500] for k, v in blobs.items()}}
        if name == "grep_text":
            r = tools.http_get(args.get("url", ""))
            text = r.get("text", "") if r.get("ok") else ""
            sub = args.get("substring", "")
            snippets = []
            idx = 0
            while len(snippets) < 5:
                i = text.find(sub, idx)
                if i == -1:
                    break
                snippets.append(text[max(0, i - 100):i + 200])
                idx = i + len(sub)
            return {"snippets": snippets, "match_count_capped_at_5": len(snippets)}
        return {"error": f"unknown tool {name}"}
    return run


def _count_job_links(html):
    """Count distinct job-detail-looking links in raw HTML (generic heuristic, string ops only)."""
    try:
        soup = tools.parse_html(html or "")
    except ImportError:
        return 0
    seen = set()
    for a in soup.find_all("a", href=True):
        h = a["href"].lower()
        if any(k in h for k in ("/job/", "/jobs/", "/position/", "/vacancy/", "/opening/")):
            seen.add(a["href"])
        else:
            tail = a["href"].rstrip("/").split("/")[-1]
            if tail.isdigit() and len(tail) >= 6:
                seen.add(a["href"])
    return len(seen)


# Facet-id query params used by major ATS/career-site platforms for location facets.
# Platform-level conventions (like boards-api URL shapes), verified per-site before use.
_FACET_PARAM_CANDIDATES = ["alrpm", "alp", "facetId", "locationFacet", "location", "country"]


def _probe_india_facet(list_url, trace):
    """If the SSR list page HTML exposes an 'India' facet control, try to activate it server-side and
    VERIFY the filtered page. Returns {'url','evidence'} or None."""
    from urllib.parse import urljoin

    raw = tools.http_get(list_url)
    if not (raw.get("ok") and raw.get("status") == 200):
        return None
    html = raw.get("text", "")
    base_count = _count_job_links(html)
    soup = tools.parse_html(html)

    # find facet controls naming India: <a> links first (self-contained), then inputs w/ data ids
    for a in soup.find_all("a", href=True):
        if a.get_text(strip=True).lower().startswith("india"):
            href = urljoin(list_url, a["href"])
            if href == list_url or "#" in href.split("/")[-1]:
                continue
            check = tools.http_get(href)
            if check.get("ok") and check.get("status") == 200:
                n = _count_job_links(check.get("text", ""))
                if 0 < n < max(base_count, 2):
                    ev = f"India facet link verified: {href} ({n} job links vs {base_count} unfiltered)"
                    trace.decision("reverse_engineer", "india_facet_link", evidence=[ev])
                    return {"url": href, "evidence": ev}

    candidates = []
    for el in soup.find_all(True):
        display = (el.get("data-display") or "").strip().lower()
        text = el.get_text(strip=True).lower() if el.name in ("label", "option") else ""
        if display == "india" or text.startswith("india"):
            fid = el.get("data-id") or el.get("value")
            fcount = el.get("data-count")
            if fid and str(fid).isdigit():
                candidates.append((str(fid), int(fcount) if (fcount or "").isdigit() else None))
    for fid, fcount in candidates[:3]:
        for param in _FACET_PARAM_CANDIDATES:
            sep = "&" if "?" in list_url else "?"
            url = f"{list_url}{sep}{param}={fid}"
            check = tools.http_get(url)
            if not (check.get("ok") and check.get("status") == 200):
                continue
            n = _count_job_links(check.get("text", ""))
            # verified iff it meaningfully narrows results (and matches facet count when known)
            if 0 < n < base_count and (fcount is None or abs(n - fcount) <= 2):
                ev = (f"India facet id {fid} activated via ?{param}= and verified: "
                      f"{n} job links vs {base_count} unfiltered (facet count {fcount})")
                trace.decision("reverse_engineer", "india_facet_param", evidence=[ev])
                return {"url": url, "evidence": ev}
    return None


def reverse_engineer(careers_url, platform_hint, llm, trace):
    trace.stage("reverse_engineer", f"Reverse-engineering data source for {careers_url}")
    system = (
        "You are a reverse-engineering agent. Given a company's careers page URL and a guessed platform, "
        "figure out the ACTUAL underlying data source for job listings and how pagination works, so a "
        "standalone scraper can be written against it. Work through this priority order like an engineer would:\n"
        "0. FIRST, fetch_raw the careers/search URL itself. If the RAW (no-JS) HTML already contains "
        "individual job-detail links, the list is SERVER-SIDE RENDERED -- do NOT classify it as needing a "
        "browser. Many enterprise career sites (e.g. Radancy/TalentBrew-style '/search-jobs' pages) are fully "
        "SSR even though they look like SPAs. In that case:\n"
        "   - Look IN THAT RAW HTML for a location/country FACET: checkboxes or links whose text/data-display "
        "is 'India' (often with data-id/data-count attributes, e.g. <input data-id='1269750' "
        "data-display='India' data-count='5'>). If found, try activating it server-side: follow the facet's "
        "href if it is a link, or try appending its numeric id as a query param on the search URL (try the "
        "param names visible in the page's own links/forms) and verify with fetch_raw that the result count "
        "drops to the facet count and only India-location jobs remain. A verified India-filtered URL is the "
        "IDEAL list source (server-side filtering).\n"
        "   - Also check sitemap.xml (fetch_raw https://<careers-host>/sitemap.xml): many such sites list "
        "every job URL there, and job URLs often embed the CITY as a path segment "
        "(/en/job/<city>/<slug>/<ids>) -- a structural pre-filter for India cities via string ops.\n"
        "   - Determine SSR pagination by checking the raw HTML for a next-page link or trying ?p=2 / ?page=2 "
        "and comparing job links.\n"
        "1. Is there embedded/hydration JSON already on the page with the job list? (extract_hydration_json)\n"
        "2. Is there a discoverable REST or GraphQL API? Inspect JS bundle links (grep_text for 'api', "
        "'graphql', '/jobs', 'endpoint') and try calling candidate endpoints (fetch_json / post_json) to "
        "confirm they actually return job data -- never report an endpoint you have not verified with a "
        "real response.\n"
        "3. If the given URL itself has no embedded data, no API, AND does not visibly list individual job "
        "postings (just marketing copy), check fetch_rendered's `links` for a 'search jobs' / 'view roles' / "
        "'find your role' style link and fetch_rendered THAT page before giving up -- the real job list is "
        "very often one hop deeper than the careers landing page. Many career sites organize listings behind "
        "REGION or COUNTRY facet links (e.g. link text/URLs containing 'APAC', 'EMEA', 'Americas', a specific "
        "country name, or a city like 'Bangalore'/'Mumbai'/'Pune'/'Hyderabad') rather than a single flat search "
        "page -- these are real hrefs, not JS-only interactions, so just fetch_rendered them directly. If you "
        "see an India-relevant or APAC-relevant facet link in the `links` list, prioritize following it -- it "
        "may lead straight to the India job listings or reveal the API call that page makes.\n"
        "4. If that page shows a search/filter widget (keyword box, location box) but the initial render has "
        "no actual job rows, the results likely load via AJAX after page load -- use "
        "fetch_rendered_interactive on it (scrolls + waits) to surface them, then re-check for hydration JSON "
        "or note the job row HTML structure for CSS-selector extraction. This also covers infinite-scroll "
        "listing pages generally.\n"
        "5. Only after exhausting these, fall back to a browser/HTML approach -- but choose the RIGHT one:\n"
        "   - If the rendered LIST page yields many individual job-detail links (e.g. many URLs sharing a "
        "pattern like /careers/job/<slug>/<id>, /job/<id>, /position/<id>), grab 2-4 of those real URLs, then "
        "fetch_raw ONE of them (no JS) and check whether the job title/location/description are present in the "
        "raw HTML. If yes -> source_type=rendered_list_ssr_detail (the scraper will browser-render the list to "
        "collect links, then plain-fetch each SSR detail page -- robust and fast). Set job_detail_url_samples "
        "and detail_pages_are_ssr=true. This is the PREFERRED fallback for custom career sites like this.\n"
        "   - source_type=html_ssr if the whole job list is already in plain server HTML (no JS needed at all).\n"
        "   - source_type=spa_needs_browser ONLY if even the individual job detail content requires a live "
        "browser (detail pages are also JS-rendered) or the site is behind a login/auth wall. Avoid this when "
        "a public SSR path exists.\n"
        "   AVOID choosing a source that is behind a login/authentication redirect (URLs with 'login', "
        "'loginFlowRequired', 'signin') -- if the careers_url you were given is login-walled but you saw a "
        "public job list elsewhere (e.g. a country/India page with SSR job-detail links), reverse-engineer "
        "THAT instead.\n"
        "Known ATS platforms often expose predictable API shapes (e.g. Greenhouse boards-api, Workday wday/cxs "
        "endpoints, Lever postings API) -- if the platform hint suggests one, it's reasonable to *try* the "
        "conventional shape as a hypothesis, but you MUST verify it actually works via a tool call before "
        "reporting it; never report an unverified guess as the answer. To build the hypothesis you need the "
        "company's board/tenant TOKEN, which you extract from a real URL you've already seen (never invent "
        "it): e.g. if a page links to boards.greenhouse.io/<TOKEN>/jobs/... or job-boards.greenhouse.io/<TOKEN>, "
        "that <TOKEN> segment is what goes into "
        "https://boards-api.greenhouse.io/v1/boards/<TOKEN>/jobs -- verify it with fetch_json before reporting. "
        "Similarly for Lever (jobs.lever.co/<TOKEN> -> api.lever.co/v0/postings/<TOKEN>), Ashby "
        "(jobs.ashbyhq.com/<TOKEN> -> api.ashbyhq.com/posting-api/job-board/<TOKEN>), etc. If the careers page "
        "only links to individual job postings (not a board index), the token is still visible in each posting "
        "URL's path -- use it.\n"
        "REQUIRED CHECK before calling finish on any rest_api/graphql_api source: look at the sample job "
        "record you fetched -- does it include a full job description field? If not, you MUST try at least "
        "one generic enrichment query param (e.g. ?content=true, ?detail=true, ?expand=all) via fetch_json on "
        "the same endpoint and check whether the response gains a description field, before you're allowed to "
        "finish. Report whichever verified params give the richest response in request_params_template. Only "
        "skip this if you've already confirmed the endpoint has no such param (e.g. you tried one and it made "
        "no difference).\n"
        "Also determine the pagination scheme by inspecting response metadata (total counts, next cursor/page "
        "fields, 'has_more' flags) or by requesting a second page and comparing. "
        "When you call finish, include sample_job_record: copy one REAL job object you actually saw in a tool "
        "response (verbatim, as compact JSON text) -- this lets the next stage see the exact shape of fields "
        "like location (bare city name? 'City, Country'? structured object with a country key?) instead of "
        "guessing. This matters a lot for correct India-filtering downstream. "
        "If you exhaust reasonable attempts, call finish with source_type=not_found and be honest.\n"
        "IMPORTANT -- do not over-explore: as soon as you have ONE verified working source (a URL/endpoint "
        "you actually fetched and confirmed returns real job data), call finish with it. Do not keep probing "
        "for a 'better' alternative API once you already have a working one -- a confirmed html_ssr or "
        "rendered_list_ssr_detail source is a perfectly good answer and does not need a JSON API replacement."
    )
    user = f"Careers URL: {careers_url}\nPlatform hint (from fingerprinting): {_json.dumps(platform_hint)}"
    result = llm.agentic_loop("reverse_engineer", system, user, TOOLS, _executor(), trace=trace, max_steps=24)
    if result is None:
        result = {
            "source_type": "not_found", "endpoint_url": None, "http_method": None,
            "request_body_template": None, "request_params_template": None,
            "response_job_list_path": None, "sample_job_record": None,
            "job_detail_url_samples": [], "detail_pages_are_ssr": False, "pagination_scheme": "unknown",
            "pagination_details": "", "requires_js_execution": False, "confidence": 0, "evidence": [],
            "reasoning": "agentic loop exhausted without a finish call",
        }
    # Deterministic India-facet probe for HTML list pages. If the RAW (no-JS) search page exposes an India
    # location/country facet control (checkbox/link with a facet id), try known ATS facet-param conventions
    # and adopt the filtered URL ONLY if a real fetch verifies it narrows results to the facet's count.
    # Platform-level convention probing (like Greenhouse boards-api shapes), not per-domain logic: the same
    # probe runs for every domain and self-verifies before being trusted. Runs for BOTH html_ssr and
    # rendered_list_ssr_detail classifications -- the LLM sometimes flip-flops between them for the same
    # site, and if the probe verifies job links + a working facet in RAW html, the list is provably SSR,
    # so we also correct the classification.
    # Deterministic SSR self-check: if the LLM said the list needs JS rendering but a plain raw fetch of
    # the list URL already shows several job links, rendering is provably unnecessary (and rendered pages
    # can even LOSE links a raw fetch has) -- downgrade to html_ssr. Generic, evidence-verified.
    if result.get("source_type") == "rendered_list_ssr_detail":
        try:
            _list_url = result.get("endpoint_url") or careers_url
            _raw = tools.http_get(_list_url)
            if _raw.get("ok") and _raw.get("status") == 200:
                _n = _count_job_links(_raw.get("text", ""))
                if _n >= 3:
                    result["source_type"] = "html_ssr"
                    result["requires_js_execution"] = False
                    result["endpoint_url"] = result.get("endpoint_url") or _list_url
                    if not result.get("job_detail_url_samples"):
                        from urllib.parse import urljoin as _uj
                        _soup = tools.parse_html(_raw.get("text", ""))
                        _samples = []
                        for _a in _soup.find_all("a", href=True):
                            _h = _a["href"]
                            _tail = _h.rstrip("/").split("/")[-1]
                            if any(k in _h.lower() for k in ("/job/", "/jobs/", "/position/", "/vacancy/", "/opening/")) \
                                    or (_tail.isdigit() and len(_tail) >= 6):
                                _u = _uj(_list_url, _h)
                                if _u not in _samples:
                                    _samples.append(_u)
                            if len(_samples) >= 3:
                                break
                        result["job_detail_url_samples"] = _samples
                    result["evidence"].append(
                        f"Corrected source_type to html_ssr: raw no-JS fetch of {_list_url} already "
                        f"contains {_n} job links -- rendering not needed.")
                    trace.decision("reverse_engineer", "ssr_self_check_downgrade",
                                    evidence=[f"{_n} job links in raw HTML of {_list_url}"])
        except Exception as e:
            trace.error("reverse_engineer", f"ssr self-check failed: {e}")

    if result.get("source_type") in ("html_ssr", "rendered_list_ssr_detail"):
        list_url = result.get("endpoint_url") or careers_url
        if list_url and "india" not in list_url.lower():
            try:
                filtered = _probe_india_facet(list_url, trace)
                if filtered:
                    result["endpoint_url"] = filtered["url"]
                    result["evidence"].append(filtered["evidence"])
                    result["pagination_details"] = (result.get("pagination_details") or "") + \
                        " NOTE: endpoint_url is already India-filtered server-side; paginate that URL."
                    if result["source_type"] == "rendered_list_ssr_detail":
                        # probe verified job links exist in raw HTML -> list is SSR, no rendering needed
                        result["source_type"] = "html_ssr"
                        result["requires_js_execution"] = False
                        result["evidence"].append(
                            "Corrected source_type to html_ssr: raw-HTML probe verified job links + a "
                            "working server-side India facet without JS rendering.")
            except Exception as e:
                trace.error("reverse_engineer", f"india facet probe failed: {e}")

    # Deterministically capture a cleaned HTML sample of an actual job page so codegen can write REAL
    # CSS selectors instead of guessing. For html_ssr / rendered_list_ssr_detail we want a job-DETAIL page;
    # for spa_needs_browser we render it. This is generic infrastructure, not per-domain logic.
    result["detail_page_html_sample"] = None
    result["detail_page_sample_url"] = None
    try:
        src = result.get("source_type")
        samples = result.get("job_detail_url_samples") or []
        sample_url = samples[0] if samples else (careers_url if src == "html_ssr" else None)
        if src in ("html_ssr", "rendered_list_ssr_detail") and sample_url:
            raw = tools.http_get(sample_url)
            html = raw.get("text", "") if raw.get("ok") else ""
            if not html or len(html) < 2000:
                rendered = tools.firecrawl_scrape(sample_url)
                html = rendered.get("html", "") if rendered.get("ok") else html
            if html:
                result["detail_page_sample_url"] = sample_url
                result["detail_page_html_sample"] = tools.clean_html_for_llm(html)
                ld = tools.ldjson_blocks(html)
                if ld:
                    result["detail_page_ldjson"] = _json.dumps(ld)[:3000]
                trace.tool_call("reverse_engineer", "capture_detail_sample",
                                {"url": sample_url}, {"html_chars": len(result["detail_page_html_sample"])})
    except Exception as e:  # never let sample capture break the run
        trace.error("reverse_engineer", f"detail sample capture failed: {e}")

    trace.decision("reverse_engineer", result.get("source_type"),
                    evidence=result.get("evidence"), confidence=result.get("confidence"))
    return result
