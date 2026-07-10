"""Stage 6b: Validation. Runs assertions against the sandbox result and classifies
the outcome into three distinct buckets (§ brainstorm doc's most-missed edge case):

  success        -- one or more valid India jobs written
  success_empty  -- ran fine, zero jobs written, and that's a legitimate result
                     (no jobs on site at all, or jobs exist but none in India)
  failure        -- script crashed / hung / produced garbage / source unreachable

Getting this 3-way split right is the difference between "0 jobs" meaning
"nothing to report" vs "something is broken" -- most naive validators conflate them.
"""
import json

REQUIRED_KEYS = {
    "title", "job_id", "location", "url", "apply_url", "date_posted",
    "date_posted_text", "job_description", "employment_type", "work_type", "salary_range",
}
LOCATION_KEYS = {"city", "state", "country", "country_code"}


def _load_jobs(output_path):
    jobs = []
    errors = []
    try:
        with open(output_path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    jobs.append(json.loads(line))
                except json.JSONDecodeError as e:
                    errors.append(f"line {i}: invalid JSON ({e})")
    except FileNotFoundError:
        errors.append("output file does not exist")
    return jobs, errors


def validate(sandbox_result, trace):
    trace.stage("validate", "Validating generated scraper output")
    checks = {}
    reasons = []

    if sandbox_result["timed_out"]:
        outcome = "failure"
        reasons.append("script timed out (possible hang / infinite loop / stuck on bot protection)")
        result = {"outcome": outcome, "reasons": reasons, "checks": checks, "job_count": 0, "score": 0.0}
        trace.decision("validate", outcome, evidence=reasons)
        return result

    jobs, parse_errors = _load_jobs(sandbox_result["output_path"])
    checks["json_valid"] = len(parse_errors) == 0
    checks["output_file_exists"] = sandbox_result["output_exists"]

    if not sandbox_result["output_exists"]:
        outcome = "failure"
        reasons.append("script did not produce an output file")
        if sandbox_result["exit_code"] not in (0, None):
            reasons.append(f"non-zero exit code {sandbox_result['exit_code']}")
        if sandbox_result["stderr"]:
            reasons.append(f"stderr: {sandbox_result['stderr'][-500:]}")
        result = {"outcome": outcome, "reasons": reasons, "checks": checks, "job_count": 0, "score": 0.0}
        trace.decision("validate", outcome, evidence=reasons)
        return result

    if parse_errors:
        outcome = "failure"
        reasons.append("output file contains invalid JSON lines")
        reasons.extend(parse_errors[:5])
        result = {"outcome": outcome, "reasons": reasons, "checks": checks,
                   "job_count": len(jobs), "score": 0.0}
        trace.decision("validate", outcome, evidence=reasons)
        return result

    if sandbox_result["exit_code"] not in (0, None) and not jobs:
        outcome = "failure"
        reasons.append(f"script exited non-zero ({sandbox_result['exit_code']}) with no output -- likely blocked/broken")
        if sandbox_result["stderr"]:
            reasons.append(f"stderr: {sandbox_result['stderr'][-500:]}")
        result = {"outcome": outcome, "reasons": reasons, "checks": checks, "job_count": 0, "score": 0.0}
        trace.decision("validate", outcome, evidence=reasons)
        return result

    if len(jobs) == 0:
        stderr = sandbox_result.get("stderr", "")
        looks_crashed = "Traceback (most recent call last)" in stderr or "Error" in stderr[-500:]
        if looks_crashed:
            outcome = "failure"
            reasons.append(f"zero jobs AND stderr looks like an unhandled crash, not a clean empty result: {stderr[-500:]}")
            result = {"outcome": outcome, "reasons": reasons, "checks": checks, "job_count": 0, "score": 0.0}
            trace.decision("validate", outcome, evidence=reasons)
            return result
        outcome = "success_empty"
        reason = "zero jobs written"
        if "india" in stderr.lower():
            reason = "site has jobs but none located in India (per script's own reporting)"
        elif stderr:
            reason = f"zero jobs written; script stderr: {stderr[-300:]}"
        reasons.append(reason)
        result = {"outcome": outcome, "reasons": reasons, "checks": checks, "job_count": 0, "score": 1.0}
        trace.decision("validate", outcome, evidence=reasons)
        return result

    schema_ok = all(REQUIRED_KEYS.issubset(j.keys()) for j in jobs)
    checks["schema_complete"] = schema_ok
    if not schema_ok:
        missing_examples = []
        for j in jobs:
            missing = REQUIRED_KEYS - set(j.keys())
            if missing:
                missing_examples.append(sorted(missing))
                break
        reasons.append(f"some jobs missing required keys, e.g. {missing_examples}")

    location_ok = all(isinstance(j.get("location"), dict) and LOCATION_KEYS.issubset(j["location"].keys())
                       for j in jobs)
    checks["location_shape_ok"] = location_ok
    if not location_ok:
        reasons.append("location field missing or malformed on at least one job")

    india_ok = True
    for j in jobs:
        loc = j.get("location") or {}
        cc = (loc.get("country_code") or "").upper()
        country = (loc.get("country") or "").lower()
        # a job counts as India ONLY if it positively resolves to India; a fully-null
        # location is NOT verifiable as India and must not be shipped as an India job
        if cc == "IN" or "india" in country:
            continue
        india_ok = False
    checks["all_jobs_india"] = india_ok
    if not india_ok:
        reasons.append("at least one job's location does not structurally resolve to India "
                       "(non-India or null country) -- the scraper must filter these out")

    # Dedupe key: job_id, else url, else (title, city) -- for sites with no stable id/url per job
    # (e.g. client-rendered SPA cards with no individual job page), falling back to a bare `None` key
    # would collapse every DISTINCT job into one false "duplicate". Only records that share a real,
    # non-empty key count as duplicates; unverifiable (fully-null-key) records are never flagged.
    def _dupe_key(j):
        if j.get("job_id"):
            return ("id", j["job_id"])
        if j.get("url"):
            return ("url", j["url"])
        loc = j.get("location") or {}
        if j.get("title") and loc.get("city"):
            return ("title_city", j["title"], loc.get("city"))
        return None

    keys = [_dupe_key(j) for j in jobs]
    verifiable = [k for k in keys if k is not None]
    dupes = len(verifiable) - len(set(verifiable))
    checks["no_duplicates"] = dupes == 0
    if dupes:
        reasons.append(f"{dupes} duplicate job(s) by job_id/url/title+city")

    urls_ok = all((j.get("url") or "").startswith("http") for j in jobs if j.get("url"))
    checks["urls_absolute"] = urls_ok
    if not urls_ok:
        reasons.append("at least one job URL is not absolute")

    titles_ok = sum(1 for j in jobs if j.get("title")) / len(jobs) >= 0.8
    checks["titles_mostly_present"] = titles_ok
    if not titles_ok:
        reasons.append("fewer than 80% of jobs have a non-null title -- extraction likely broken")

    passed = sum(1 for v in checks.values() if v)
    score = passed / len(checks) if checks else 0.0

    if not titles_ok or not schema_ok or dupes or not india_ok:
        outcome = "failure"
    else:
        outcome = "success"
        if reasons:
            pass  # non-fatal issues (e.g. location shape) still noted but don't block success

    result = {"outcome": outcome, "reasons": reasons, "checks": checks, "job_count": len(jobs), "score": round(score, 2)}
    trace.decision("validate", outcome, evidence=reasons, confidence=round(score * 100, 1))
    return result
