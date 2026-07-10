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
from .trace import Trace
from .llm import LLM, CostTracker

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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

    report = _write_report(domain, out_dir, disc, fp, re_result, plan, validate_result, cost, attempt)
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


def _write_report(domain, out_dir, disc, fp, re_result, plan, validate_result, cost, repair_attempts):
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
        ]
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
