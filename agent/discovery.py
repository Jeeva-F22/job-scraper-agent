"""Stage 1: Discovery. Given only a domain, find the real careers page / job listing source.

LLM drives an agentic tool loop (search, robots.txt, sitemap.xml, direct fetch)
and decides when it has enough evidence to name a careers URL -- or to honestly
report none exists. No hardcoded per-domain URL guesses beyond generic,
domain-agnostic conventions (e.g. trying /careers is generic infra, not a branch
on which company we're looking at).
"""
from . import tools

_COMMON_PATHS = [
    "/careers", "/jobs", "/careers/", "/company/careers", "/about/careers", "/en/careers",
    # India / region-specific careers pages: since our target is India jobs, a country-scoped
    # careers page (when one exists) is usually the cleanest, already-India-filtered source.
    "/careers/india", "/careers/india.html", "/careers/in", "/india/careers",
    "/careers/asia-pacific", "/careers/apac-careers.html", "/en-in/careers",
]

TOOLS = [
    {"type": "function", "function": {
        "name": "web_search",
        "description": "Search the web for the company's careers page.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "fetch_url",
        "description": "Raw HTTP GET of a URL (no JS rendering). Good for robots.txt, sitemap.xml, static HTML, JSON APIs.",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    }},
    {"type": "function", "function": {
        "name": "fetch_rendered",
        "description": "Fetch a URL with JS rendering (headless browser) via Firecrawl. Use for SPA pages that need JS to show content.",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    }},
    {"type": "function", "function": {
        "name": "try_common_paths",
        "description": "Try a batch of generic, non-domain-specific careers path conventions (e.g. /careers, /jobs) against the domain and report which resolve (HTTP 200).",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "finish",
        "description": "Report final discovery result.",
        "parameters": {
            "type": "object",
            "properties": {
                "careers_url_found": {"type": "boolean"},
                "careers_url": {"type": ["string", "null"]},
                "confidence": {"type": "number", "description": "0-100"},
                "evidence": {"type": "array", "items": {"type": "string"}},
                "reasoning": {"type": "string"},
            },
            "required": ["careers_url_found", "careers_url", "confidence", "evidence", "reasoning"],
        },
    }},
]


def _executor(domain):
    def run(name, args):
        if name == "web_search":
            q = args.get("query", "")
            res = tools.serpapi_search(q)
            if not res.get("results"):
                res = tools.firecrawl_search(q)
            return res
        if name == "fetch_url":
            return tools.http_get(args.get("url", ""))
        if name == "fetch_rendered":
            return tools.firecrawl_scrape(args.get("url", ""))
        if name == "try_common_paths":
            out = []
            for p in _COMMON_PATHS:
                r = tools.http_get(f"https://{domain}{p}")
                out.append({"path": p, "status": r.get("status"), "ok": r.get("ok")})
            return {"attempts": out}
        return {"error": f"unknown tool {name}"}
    return run


def discover(domain, llm, trace):
    trace.stage("discovery", f"Discovering careers page for {domain}")
    system = (
        "You are a discovery agent for a job-scraper-generating system. "
        "Your only job: find the page that actually LISTS individual job postings (titles + links you can "
        "click into), or its underlying job API -- given nothing but a domain. Use the tools available -- "
        "search, robots.txt/sitemap inspection, direct fetch, rendered fetch, and generic path conventions.\n\n"
        "IMPORTANT -- a generic 'Careers' / 'Life at <company>' marketing landing page is NOT the answer if "
        "it doesn't itself show a searchable list of open roles. Many companies' /careers page is just a "
        "landing page with a 'Search jobs' / 'View open roles' / 'Find your role' button that links to the "
        "REAL job listing page (often on a different path or subdomain, e.g. jobs.<domain>, "
        "<domain>/careers/search, or a third-party ATS board). When you fetch_rendered a candidate page, "
        "check its links for that kind of CTA and follow it before concluding. Only call finish once you have "
        "fetched a page and can point to evidence of actual individual job postings on it (job titles, "
        "requisition links, or a job search results structure) -- not just careers-themed marketing copy.\n\n"
        "OUR TARGET IS INDIA JOBS SPECIFICALLY. So actively prefer, in this priority order:\n"
        "  (a) a country-specific INDIA careers page (URL or link text containing 'india', 'in', or an "
        "India city) -- these are already India-scoped and usually the cleanest source; try try_common_paths "
        "and follow region navigation (Careers -> Asia Pacific -> India -> 'View roles in India') to find it;\n"
        "  (b) an APAC/Asia-Pacific regional careers page that can be filtered to India;\n"
        "  (c) a global job-search page/API that supports an India location filter.\n"
        "Between two candidates that both list jobs, PREFER the one whose job postings render as normal server "
        "HTML (individual job-detail links you can open) over one that sits behind a login wall, an "
        "authentication redirect (URLs containing 'login', 'loginFlowRequired', 'signin'), or a heavy "
        "third-party ATS SPA -- those are much harder to scrape and often gated. If the official ATS is "
        "login-walled but the company also has a public custom careers/India page listing the same jobs, "
        "choose the public custom page.\n\n"
        "Never fabricate a URL you have not actually fetched and confirmed -- and never CONSTRUCT one either "
        "(e.g. guessing a '#anchor' hash fragment, or appending a path you assume exists). Only follow URLs "
        "that appear verbatim in a tool result's `links` array or search results. If fetch_rendered shows a "
        "'See open positions' / 'Search jobs' style link, find its EXACT href string in that same result's "
        "`links` list and fetch that -- do not invent a same-page anchor for it.\n"
        "If robots.txt or sitemap.xml "
        "reveal a careers/jobs sitemap entry, prefer that -- it's strong evidence. If you cannot find a real "
        "job-listing page after reasonable effort (including following one layer of 'search jobs' links), "
        "call finish with careers_url_found=false and careers_url=null. Do not guess."
    )
    user = f"Domain: {domain}\nFind the careers/job-listings page for this company."
    result = llm.agentic_loop("discovery", system, user, TOOLS, _executor(domain), trace=trace, max_steps=14)
    if result is None:
        result = {
            "careers_url_found": False, "careers_url": None, "confidence": 0,
            "evidence": [], "reasoning": "agentic loop exhausted without a finish call",
        }

    # Deterministic India-page preference. Our target is India jobs, so if a country-specific India careers
    # page exists AND actually lists individual jobs, prefer it over whatever the LLM picked (which is often a
    # global/all-jobs board that is harder to scrape or not India-scoped). This is generic to the task, not a
    # per-domain branch: the same India-path probe runs for every domain and only wins when it truly lists jobs.
    india_url = _find_india_listing_page(domain, result.get("careers_url"), trace)
    if india_url and india_url != result.get("careers_url"):
        result.setdefault("evidence", []).append(
            f"Overrode careers_url to India-specific listing page {india_url} (country-scoped, lists jobs)."
        )
        result["careers_url"] = india_url
        result["careers_url_found"] = True
        result["india_page_preferred"] = True

    # Deterministic verify-or-follow-CTA gate. The LLM's own prompt instructs it not to settle for a bare
    # marketing landing page, but that's a prose rule and gets ignored under agentic pressure. Verify the
    # final candidate actually shows job-like links; if it's a landing page with a "search jobs" style CTA
    # (generic keyword match on link text, not a per-domain guess), follow it one hop and re-check. Runs
    # for every domain identically.
    if result.get("careers_url_found") and result.get("careers_url"):
        verified_url, verified = _verify_or_follow_listing(domain, result["careers_url"], trace)
        if verified_url != result["careers_url"]:
            result.setdefault("evidence", []).append(
                f"Followed 'search jobs' CTA from landing page to {verified_url} (job links verified there)."
            )
            result["careers_url"] = verified_url
        if not verified:
            result.setdefault("evidence", []).append(
                f"WARNING: {result['careers_url']} shows fewer than 3 job-like links even after rendering "
                "and following one CTA hop -- may be a landing page, not the real job listing source."
            )

    trace.decision("discovery", result.get("careers_url") or "NOT FOUND",
                    evidence=result.get("evidence"), confidence=result.get("confidence"))
    return result


def _looks_like_job_link(url):
    """Generic heuristic: does this URL look like an individual job posting? (not per-domain)"""
    ul = url.lower()
    if any(k in ul for k in ("/job/", "/jobs/", "/job-", "/position/", "/vacancy/", "/opening/",
                              "/careers/job", "jobid=", "requisition")):
        return True
    tail = url.rstrip("/").split("/")[-1]
    return tail.isdigit() and len(tail) >= 6  # trailing requisition-id-like segment


_INDIA_PATHS = ["/careers/india", "/careers/india.html", "/careers/in", "/india/careers",
                "/en-in/careers", "/careers/locations/india", "/careers/asia-pacific/india"]


def _find_india_listing_page(domain, current_url, trace):
    """Probe generic India-specific careers paths; return the first that renders with >=3 job-like links.
    Returns None if none qualify (then we keep the LLM's choice). Generic infra, runs for every domain."""
    # If the LLM already chose an India-specific page that lists jobs, keep it.
    if current_url and "india" in current_url.lower():
        return None
    for path in _INDIA_PATHS:
        url = f"https://{domain}{path}"
        r = tools.http_get(url)
        if not (r.get("ok") and r.get("status") == 200):
            continue
        # count job-like links: try plain HTML first (cheap), then a rendered pass if needed.
        links = _collect_links(r.get("text", ""), url)
        job_like = [l for l in links if _looks_like_job_link(l)]
        if len(job_like) < 3:
            rendered = tools.firecrawl_scrape_interactive(url, scroll_times=3)
            if rendered.get("ok"):
                job_like = [l for l in rendered.get("links", []) if _looks_like_job_link(l)]
        if len(job_like) >= 3:
            trace.decision("discovery", f"India-page override candidate: {url}",
                            evidence=[f"{len(job_like)} job-like links found on India page"])
            return url
    return None


_CTA_KEYWORDS = ("search job", "view job", "browse job", "find job", "open position", "open positions",
                  "current opening", "current openings", "job search", "explore opportunities",
                  "view opportunities", "see all jobs", "all jobs", "job openings", "view all roles",
                  "view roles", "find your role")


def _find_job_search_cta(render_result, base_url):
    """Generic keyword match on link text for a 'search jobs' style CTA -- not a per-domain guess,
    the same keyword set is checked for every domain."""
    from urllib.parse import urljoin
    try:
        soup = tools.parse_html(render_result.get("html") or "")
    except ImportError:
        return None
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True).lower()
        if any(k in text for k in _CTA_KEYWORDS):
            return urljoin(base_url, a["href"])
    return None


def _verify_or_follow_listing(domain, careers_url, trace):
    """Deterministic check: does careers_url actually show >=3 job-like links (rendered)? If not, look for
    a generic 'search jobs' CTA and follow it one hop, re-checking. Runs for every domain identically."""
    rendered = tools.firecrawl_scrape(careers_url)
    if not rendered.get("ok"):
        raw = tools.http_get(careers_url)
        links = _collect_links(raw.get("text", ""), careers_url) if raw.get("ok") else []
        job_like = [l for l in links if _looks_like_job_link(l)]
        return careers_url, len(job_like) >= 3

    job_like = [l for l in (rendered.get("links") or []) if _looks_like_job_link(l)]
    if len(job_like) >= 3:
        return careers_url, True

    cta = _find_job_search_cta(rendered, careers_url)
    if cta and cta != careers_url:
        rendered2 = tools.firecrawl_scrape(cta)
        if rendered2.get("ok"):
            job_like2 = [l for l in (rendered2.get("links") or []) if _looks_like_job_link(l)]
            if len(job_like2) >= 3:
                return cta, True
    return careers_url, False


def _collect_links(html, base_url):
    from urllib.parse import urljoin
    try:
        soup = tools.parse_html(html or "")
    except ImportError:
        return []
    return [urljoin(base_url, a.get("href")) for a in soup.find_all("a", href=True)]
