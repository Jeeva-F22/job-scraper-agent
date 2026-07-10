"""Stage 4: Scraper Architect. Turns discovery+fingerprint+reverse-engineering evidence
into a concrete, structured scrape plan the code generator will implement literally.
"""
import json as _json

_SCHEMA = {
    "type": "object",
    "properties": {
        "source_type": {"type": "string"},
        "request_plan": {"type": "string", "description": "Plain-English description of exactly how to fetch each page: method, URL, params/body, headers if needed."},
        "pagination_plan": {"type": "string", "description": "Exact loop logic: starting value, increment/cursor field, stop condition."},
        "field_extraction_plan": {
            "type": "object",
            "description": "For each output field, where it comes from: a JSON path (e.g. 'title' or 'location.city') or a CSS selector (e.g. '.job-title'). Use null if the source has no such field.",
            "properties": {
                "title": {"type": ["string", "null"]},
                "job_id": {"type": ["string", "null"]},
                "location_raw": {"type": ["string", "null"], "description": "path/selector to the raw location field/text before splitting into city/state/country"},
                "url": {"type": ["string", "null"]},
                "date_posted_raw": {"type": ["string", "null"]},
                "job_description": {"type": ["string", "null"]},
                "employment_type": {"type": ["string", "null"]},
                "work_type": {"type": ["string", "null"], "description": "remote/hybrid/onsite field if structurally present"},
                "salary_range": {"type": ["string", "null"]},
            },
            "required": ["title", "job_id", "location_raw", "url", "date_posted_raw", "job_description",
                         "employment_type", "work_type", "salary_range"],
            "additionalProperties": False,
        },
        "india_filter_strategy": {
            "type": "string",
            "description": "How to determine a job is India-based using STRUCTURAL fields only (country field == 'India'/'IN', or a location object's country_code, or a dedicated country facet in the API/query params for server-side filtering). Must not rely on free-text regex matching of the description.",
        },
        "server_side_india_filter_possible": {"type": "boolean"},
        "dedupe_key": {"type": "string", "description": "job_id or url -- whichever is stable"},
        "notes_for_codegen": {"type": "string"},
    },
    "required": ["source_type", "request_plan", "pagination_plan", "field_extraction_plan",
                 "india_filter_strategy", "server_side_india_filter_possible", "dedupe_key",
                 "notes_for_codegen"],
    "additionalProperties": False,
}


def architect(discovery_result, fingerprint_result, re_result, llm, trace, memory_hint=None):
    trace.stage("architect", "Planning scraper implementation")
    system = (
        "You are the Scraper Architect. Given verified evidence about a company's job data source "
        "(from discovery, platform fingerprinting, and reverse engineering), produce a precise, "
        "unambiguous implementation plan for a Python scraper. Rules the generated code MUST follow "
        "(bake these into your plan so codegen can't miss them):\n"
        "- Field extraction only via JSON paths or CSS selectors -- never regex.\n"
        "- Any field not structurally present becomes null in output -- never inferred or hallucinated.\n"
        "- India filtering must use structural location fields (country/country_code) or a server-side "
        "API filter param, not text pattern matching of descriptions.\n"
        "- CRITICAL -- look closely at the actual sample location value(s) in the reverse-engineering "
        "evidence. Many ATS platforms (Greenhouse included) put ONLY a bare city name in the location field "
        "(e.g. 'Bengaluru', not 'Bengaluru, India') with no separate country field at all. A naive substring "
        "check for the literal word 'India' or 'IN' in that string WILL WRONGLY DROP those jobs -- 'IN' as a "
        "2-letter substring match is unreliable anyway. If the sample location value has no explicit country "
        "token, your india_filter_strategy MUST explicitly instruct codegen to resolve country from city name "
        "using a small generic (non-company-specific) static city->country lookup table it authors itself, "
        "covering major India cities (Bengaluru/Bangalore, Mumbai, Delhi/New Delhi, Gurugram/Gurgaon, Noida, "
        "Hyderabad, Chennai, Pune, Kolkata, Ahmedabad), falling back to null if the city isn't recognized. "
        "Spell this out concretely in india_filter_strategy -- don't leave it implicit.\n"
        "- Pagination must be complete -- the plan must specify an exact, correct stop condition.\n"
        "- Prefer filtering India jobs server-side (via API params) if the source supports it; otherwise "
        "plan for client-side structural filtering after fetching all pages.\n"
        "- If source_type is 'rendered_list_ssr_detail', your field_extraction_plan CSS selectors should "
        "target the individual job-DETAIL page HTML (not the list), since the two-stage scraper collects "
        "detail URLs from the rendered list then fetches each SSR detail page. In request_plan describe both "
        "stages: (A) browser-render the list URL and the selector for job-detail anchor links; (B) plain "
        "requests-fetch each detail URL. Use the job_detail_url_samples in the evidence to identify the "
        "detail-link pattern/selector."
    )
    user = (
        f"Discovery:\n{_json.dumps(discovery_result, ensure_ascii=False)[:4000]}\n\n"
        f"Fingerprint:\n{_json.dumps({k: v for k, v in fingerprint_result.items() if k != '_raw_signals'}, ensure_ascii=False)[:4000]}\n\n"
        f"Reverse engineering:\n{_json.dumps(re_result, ensure_ascii=False)[:6000]}\n\n"
        + (f"Prior successful plan for this same platform (from agent's own memory -- treat as a hint to "
           f"verify/adapt, NOT to blindly trust):\n{_json.dumps(memory_hint, ensure_ascii=False)[:3000]}\n\n"
           if memory_hint else "")
        + "Produce the scrape plan."
    )
    plan = llm.complete("architect", system, user, trace=trace, response_schema=_SCHEMA)
    trace.decision("architect", plan["source_type"], evidence=[plan["request_plan"], plan["pagination_plan"]])
    return plan
