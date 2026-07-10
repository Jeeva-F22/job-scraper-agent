"""CLI entry point + the software-engineering loop that wires every stage together.

    python -m agent.orchestrator run <domain>

Loop: Discover -> Fingerprint -> Reverse-engineer -> Architect -> Codegen ->
      Sandbox run -> Validate -> [Repair -> Sandbox run -> Validate]* (<=3) ->
      Memory write -> Confidence/Trace/Cost report.

No stage's business decision (careers URL, platform, endpoint, plan, code, patch)
is hardcoded here -- this module only sequences the LLM calls and records evidence.
"""
import argparse
import json
import os
import sys
import time

from dotenv import load_dotenv

from . import discovery, fingerprint, reverse_engineer, architect, codegen, sandbox, validator, repair, memory
from . import linkedin_jobs
from .trace import Trace
from .llm import LLM, CostTracker

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _guess_company_name(domain, fp):
    """Best-effort company display name for the LinkedIn query -- generic for every domain, never a
    per-domain lookup table. Prefers the page title captured during fingerprinting (real signal), falls
    back to a deterministic domain->name transform (strip TLD, title-case)."""
    _NOISE_WORDS = ("careers", "career", "jobs", "job", "hiring", "join us", "welcome to")

    def _strip_noise(text):
        words = text.split()
        while words and words[-1].lower() in _NOISE_WORDS:
            words.pop()
        return " ".join(words).strip()

    preview = ((fp or {}).get("_raw_signals") or {}).get("markdown_preview") or ""
    first_line = preview.strip().split("\n", 1)[0].strip()
    for sep in (" | ", " - ", " — "):
        if sep in first_line:
            candidate = _strip_noise(first_line.split(sep)[0].strip())
            if 2 <= len(candidate) <= 60:
                return candidate
    base = domain.split(".")[0]
    return " ".join(w.capitalize() for w in base.replace("-", " ").replace("_", " ").split())


def _try_linkedin_enrichment(domain, fp, out_dir, trace):
    """Bonus cross-platform layer: this company's India job postings as they appear on LinkedIn
    (via SerpAPI's Google Jobs index, no LinkedIn scraping). Deterministic, no LLM calls. Wrapped so
    any failure here (SerpAPI down, no key, no matches) never breaks the core scraper deliverable."""
    company = _guess_company_name(domain, fp)
    try:
        records = linkedin_jobs.fetch(company)
        linkedin_jobs.write_jsonl(os.path.join(out_dir, "linkedin_jobs.jsonl"), records)
        trace.decision("linkedin_enrichment", f"{len(records)} India LinkedIn job(s) for '{company}'",
                        evidence=[f"query company name guess: {company}"])
        return len(records), company
    except Exception as e:
        trace.error("linkedin_enrichment", f"skipped: {e}")
        return None, company


def run_domain(domain, out_root=None):
    load_dotenv(os.path.join(ROOT, ".env"))
    out_dir = out_root or os.path.join(ROOT, "generated", domain.replace("/", "_"))
    os.makedirs(out_dir, exist_ok=True)

    trace = Trace(os.path.join(out_dir, "trace.jsonl"))
    cost = CostTracker()
    llm = LLM(cost_tracker=cost)

    trace.stage("run_start", f"Domain: {domain}")

    # 1. Discover
    disc = discovery.discover(domain, llm, trace)
    if not disc.get("careers_url_found"):
        return _finish_no_script(domain, out_dir, trace, cost, disc,
                                  reason="No careers page could be found for this domain.")

    careers_url = disc["careers_url"]

    # 2. Fingerprint
    fp = fingerprint.fingerprint(careers_url, llm, trace)

    # 3. Reverse-engineer
    re_result = reverse_engineer.reverse_engineer(careers_url, fp, llm, trace)

    # Deterministic guard: if discovery verified a country-scoped India listing page, reverse-engineering
    # must not silently swap the scrape target to a GLOBAL unfiltered list (URL-slug prefilters and facet
    # probes can both legitimately fail on global lists, silently yielding zero India jobs). Only overrides
    # after re-verifying the India page still shows job links right now. Generic -- runs for every domain.
    if disc.get("india_page_preferred") and re_result.get("source_type") in ("html_ssr", "rendered_list_ssr_detail"):
        _epu = (re_result.get("endpoint_url") or "").lower()
        if "india" not in _epu:
            from . import tools as _tools
            _raw = _tools.http_get(careers_url)
            _n = reverse_engineer._count_job_links(_raw.get("text", "")) if _raw.get("ok") else 0
            if _n >= 3:
                re_result["endpoint_url"] = careers_url
                re_result["source_type"] = "html_ssr"
                re_result["requires_js_execution"] = False
                re_result.setdefault("evidence", []).append(
                    f"Endpoint overridden back to discovery's verified India page {careers_url} "
                    f"({_n} job links in raw HTML) -- reverse-engineering had drifted to a global list.")
                trace.decision("reverse_engineer", "india_endpoint_guard",
                                evidence=[f"{_n} job links on {careers_url}; global endpoint replaced"])
            else:
                _rendered = _tools.firecrawl_scrape_interactive(careers_url, scroll_times=3)
                _links = [l for l in (_rendered.get("links") or []) if "/job" in l.lower()]
                if len(_links) >= 3:
                    re_result["endpoint_url"] = careers_url
                    re_result["source_type"] = "rendered_list_ssr_detail"
                    re_result["requires_js_execution"] = True
                    re_result.setdefault("evidence", []).append(
                        f"Endpoint overridden back to discovery's verified India page {careers_url} "
                        f"({len(_links)} job links after rendering) -- reverse-engineering had drifted to a global list.")
                    trace.decision("reverse_engineer", "india_endpoint_guard",
                                    evidence=[f"{len(_links)} rendered job links on {careers_url}; global endpoint replaced"])

    if re_result.get("source_type") == "not_found":
        return _finish_no_script(domain, out_dir, trace, cost, disc, fingerprint_result=fp, re_result=re_result,
                                  reason="Careers page found but no extractable job data source could be identified.")

    # 4. Memory hint (agent's own past successes for this platform)
    plan_hint, code_hint = memory.get_hint(fp.get("platform"))
    if plan_hint:
        trace.decision("memory", f"reusing hint for platform={fp.get('platform')}",
                        evidence=[f"prior success count context available"])

    # 5. Architect
    plan = architect.architect(disc, fp, re_result, llm, trace, memory_hint=plan_hint)

    # 6. Codegen
    script_path, code = codegen.generate(plan, disc, re_result, domain, llm, trace, out_dir,
                                          prior_code_hint=code_hint)

    # 7. Sandbox + Validate, with repair loop
    attempt = 0
    sandbox_result = sandbox.run(script_path, out_dir)
    validate_result = validator.validate(sandbox_result, trace)

    while validate_result["outcome"] == "failure" and attempt < repair.MAX_ATTEMPTS:
        attempt += 1
        cost.add_retry()
        trace.reasoning("repair", f"Attempt {attempt}/{repair.MAX_ATTEMPTS} -- validator reported failure, repairing.")
        script_path, code = repair.repair(plan, disc, re_result, domain, llm, trace, out_dir,
                                           sandbox_result, validate_result, code)
        sandbox_result = sandbox.run(script_path, out_dir)
        validate_result = validator.validate(sandbox_result, trace)

    # 8. Memory write -- ONLY on genuine success with jobs found. A success_empty scraper is a valid
    # run result but NOT a proven extraction pattern: caching it would poison future same-platform runs
    # with code that extracts nothing.
    if validate_result["outcome"] == "success" and validate_result["job_count"] > 0:
        memory.record_success(fp.get("platform"), domain, plan, code, validate_result, cost.as_dict())

    # 9. LinkedIn cross-platform enrichment (bonus, never blocks the core deliverable)
    linkedin_count, linkedin_company = _try_linkedin_enrichment(domain, fp, out_dir, trace)

    report = _write_report(domain, out_dir, disc, fp, re_result, plan, validate_result, cost, attempt,
                            linkedin_count=linkedin_count, linkedin_company=linkedin_company)
    trace.stage("run_end", report["overall_status"])
    trace.close()
    return report


def _finish_no_script(domain, out_dir, trace, cost, disc, fingerprint_result=None, re_result=None, reason=""):
    trace.decision("run", "no_script_generated", evidence=[reason])
    report = {
        "domain": domain,
        "overall_status": "no_script_generated",
        "reason": reason,
        "discovery": disc,
        "fingerprint": fingerprint_result,
        "reverse_engineer": re_result,
        "cost_report": cost.as_dict(),
    }
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    _write_report_md(out_dir, report)
    trace.close()
    return report


def _write_report(domain, out_dir, disc, fp, re_result, plan, validate_result, cost, repair_attempts,
                   linkedin_count=None, linkedin_company=None):
    status = validate_result["outcome"]  # success | success_empty | failure
    confidence = round(
        (fp.get("confidence", 0) * 0.3 + re_result.get("confidence", 0) * 0.3 + validate_result["score"] * 100 * 0.4), 1
    )
    report = {
        "domain": domain,
        "overall_status": status,
        "confidence_pct": confidence,
        "careers_url": disc.get("careers_url"),
        "platform": fp.get("platform"),
        "platform_confidence_pct": fp.get("confidence"),
        "platform_evidence": fp.get("evidence"),
        "source_type": re_result.get("source_type"),
        "pagination_scheme": re_result.get("pagination_scheme"),
        "needs_firecrawl_key": bool(re_result.get("requires_js_execution")) or
            re_result.get("source_type") in ("spa_needs_browser", "rendered_list_ssr_detail"),
        "reverse_engineer_evidence": re_result.get("evidence"),
        "job_count": validate_result["job_count"],
        "validation_checks": validate_result["checks"],
        "validation_reasons": validate_result["reasons"],
        "repair_attempts_used": repair_attempts,
        "linkedin_company_guess": linkedin_company,
        "linkedin_job_count": linkedin_count,
        "cost_report": cost.as_dict(),
    }
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    _write_report_md(out_dir, report)
    return report


def _write_report_md(out_dir, report):
    lines = [
        f"# Scraper report -- {report['domain']}",
        "",
        f"**Status:** `{report['overall_status']}`",
        f"**Confidence:** {report.get('confidence_pct', 'n/a')}%",
        "",
    ]
    if report["overall_status"] == "no_script_generated":
        lines += [f"**Reason:** {report['reason']}", ""]
    else:
        lines += [
            f"- Careers URL: {report.get('careers_url')}",
            f"- Platform: {report.get('platform')} ({report.get('platform_confidence_pct')}% confidence)",
            f"- Source type: {report.get('source_type')}",
            f"- Pagination: {report.get('pagination_scheme')}",
            f"- India jobs found: {report.get('job_count')}",
            f"- Repair attempts used: {report.get('repair_attempts_used')}",
            "",
            "## Evidence",
            *[f"- ✓ {e}" for e in (report.get("platform_evidence") or [])],
            *[f"- ✓ {e}" for e in (report.get("reverse_engineer_evidence") or [])],
            "",
            "## Validation",
            *[f"- {k}: {'✓' if v else '✗'}" for k, v in (report.get("validation_checks") or {}).items()],
            *([f"- note: {r}" for r in report.get("validation_reasons", [])]),
            "",
            "## How to run the generated scraper standalone (no agent, no LLM)",
            "```bash",
            *(["# this site needs JS/bot-protection rendering, so set your Firecrawl key first:",
               "set FIRECRAWL_API_KEY=fc-...        # Windows (Linux/Mac: export FIRECRAWL_API_KEY=fc-...)"]
              if report.get("needs_firecrawl_key") else
              ["# no API key needed -- this scraper uses a direct API / plain HTTP"]),
            f"python generated/{report['domain']}/scraper.py out.jsonl",
            "```",
            "Produces `out.jsonl` (one India job per line). Runs anywhere with Python + "
            "`pip install requests beautifulsoup4 lxml`.",
            "",
            "## Cross-platform: LinkedIn (bonus)",
        ]
        if report.get("linkedin_job_count") is not None:
            lines += [
                f"- Company name used for query: {report.get('linkedin_company_guess')}",
                f"- India job postings found on LinkedIn: {report.get('linkedin_job_count')}",
                f"- See `linkedin_jobs.jsonl`. Sourced via SerpAPI's Google Jobs index -- "
                "never scrapes linkedin.com directly. Deterministic, no LLM calls.",
                f"- Rerun standalone: `python -m agent.linkedin_jobs \"{report.get('linkedin_company_guess')}\" "
                "linkedin_jobs.jsonl`",
            ]
        else:
            lines += ["- Skipped (SerpAPI unavailable or no key) -- see trace.jsonl for details."]
    cr = report["cost_report"]
    lines += [
        "",
        "## Cost report",
        f"- LLM calls: {cr['llm_calls']}",
        f"- Tool calls: {cr['tool_calls']}",
        f"- Input tokens: {cr['input_tokens']}",
        f"- Output tokens: {cr['output_tokens']}",
        f"- Repair retries: {cr['repair_retries']}",
        f"- Estimated cost: ${cr['cost_usd']}",
        f"- Wall clock: {cr['wall_clock_sec']}s",
    ]
    with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description="AI agent that writes job-scraper scripts")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run_p = sub.add_parser("run", help="Run the agent for a single domain")
    run_p.add_argument("domain")
    args = parser.parse_args()

    if args.cmd == "run":
        t0 = time.time()
        report = run_domain(args.domain)
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        print(f"\nDone in {time.time() - t0:.1f}s -- status: {report['overall_status']}", file=sys.stderr)


if __name__ == "__main__":
    main()
