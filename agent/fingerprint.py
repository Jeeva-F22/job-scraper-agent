"""Stage 2: Platform fingerprinting.

Collects generic, platform-level signals (never company-specific) from the
careers page, then has the LLM make the actual classification call with
evidence + confidence -- so "Workday vs custom" is always an LLM decision,
not a hardcoded if/else on the domain.

The signal dictionary below is a list of *known ATS platforms* (industry-standard
detection, same category as browser user-agent sniffing) -- not a per-company
branch. It never contains a company name or company-specific selector.
"""
import json as _json

from . import tools

_PLATFORM_SIGNALS = {
    "workday": ["myworkdayjobs.com", "wd1.myworkday", "wd3.myworkday", "workday.com"],
    "greenhouse": ["greenhouse.io", "boards.greenhouse.io", "grnh.se"],
    "lever": ["lever.co", "jobs.lever.co"],
    "ashby": ["ashbyhq.com", "jobs.ashbyhq.com"],
    "successfactors": ["successfactors.com", "career.sap.com", "jobs.sap"],
    "eightfold": ["eightfold.ai"],
    "smartrecruiters": ["smartrecruiters.com"],
    "teamtailor": ["teamtailor.com"],
    "icims": ["icims.com"],
    "taleo": ["taleo.net"],
    "workable": ["workable.com"],
    "bamboohr": ["bamboohr.com"],
    "jobvite": ["jobvite.com"],
    "recruitee": ["recruitee.com"],
    "personio": ["personio.de", "personio.com"],
    "phenom": ["phenompeople.com", "phenom.com", "ddoKey", "refineSearch"],
    "radancy": ["search-jobs", "search-filters__", "talentbrew", "tmp.js"],
    "zoho_recruit": ["zohorecruit.in", "zohorecruit.com", "zoho.in/recruit", "zoho.com/recruit"],
}

_FRAMEWORK_SIGNALS = {
    "nextjs": ["__NEXT_DATA__", "_next/static"],
    "nuxt": ["__NUXT__", "_nuxt/"],
    "astro": ["astro-island"],
    "react": ["data-reactroot", "react-dom"],
    "angular": ["ng-version"],
    "vue": ["data-v-", "__vue__"],
    "wordpress": ["wp-content", "wp-json"],
}


def _collect_signals(url):
    page = tools.firecrawl_scrape(url)
    html = page.get("html", "") if page.get("ok") else ""
    links = page.get("links", []) if page.get("ok") else []
    blobs = tools.extract_json_blobs(html) if html else {}

    haystack = html + " " + " ".join(links) + " " + url
    platform_hits = {name: [m for m in markers if m in haystack] for name, markers in _PLATFORM_SIGNALS.items()}
    platform_hits = {k: v for k, v in platform_hits.items() if v}
    framework_hits = {name: [m for m in markers if m in html] for name, markers in _FRAMEWORK_SIGNALS.items()}
    framework_hits = {k: v for k, v in framework_hits.items() if v}

    return {
        "fetch_ok": page.get("ok", False),
        "platform_signal_hits": platform_hits,
        "framework_signal_hits": framework_hits,
        "hydration_blobs_found": list(blobs.keys()),
        "hydration_blob_preview": {k: str(v)[:800] for k, v in blobs.items()},
        "sample_links": links[:60],
        "markdown_preview": (page.get("markdown", "") or "")[:3000],
        "html_bytes": len(html),
    }


_SCHEMA = {
    "type": "object",
    "properties": {
        "platform": {"type": "string", "description": "e.g. workday, greenhouse, lever, ashby, custom, unknown"},
        "confidence": {"type": "number"},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "frontend_framework": {"type": ["string", "null"]},
        "likely_needs_js_rendering": {"type": "boolean"},
        "reasoning": {"type": "string"},
    },
    "required": ["platform", "confidence", "evidence", "frontend_framework",
                 "likely_needs_js_rendering", "reasoning"],
    "additionalProperties": False,
}


def fingerprint(careers_url, llm, trace):
    trace.stage("fingerprint", f"Fingerprinting platform for {careers_url}")
    signals = _collect_signals(careers_url)
    trace.tool_call("fingerprint", "collect_signals", {"url": careers_url}, signals)

    system = (
        "You are a platform fingerprinting agent. Given raw signals collected from a careers page "
        "(known-ATS substring hits, frontend framework hits, hydration JSON blob names, sample links, "
        "a markdown preview), classify which job platform this site runs on and how confident you are. "
        "Only claim a known platform if the evidence actually supports it -- otherwise say 'custom' or "
        "'unknown'. List the concrete evidence bullets that justify your call."
    )
    user = f"Careers URL: {careers_url}\n\nSignals:\n{_json.dumps(signals, ensure_ascii=False)[:12000]}"
    result = llm.complete("fingerprint", system, user, trace=trace, response_schema=_SCHEMA)
    trace.decision("fingerprint", result["platform"], evidence=result["evidence"], confidence=result["confidence"])
    result["_raw_signals"] = signals
    return result
