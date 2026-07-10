"""Cross-platform enrichment: a company's India job postings as they appear on LinkedIn,
sourced via SerpAPI's Google Jobs engine (Google's own public job index -- never scrapes
linkedin.com directly, so it doesn't touch LinkedIn's anti-scraping defenses or ToS).

Deterministic, no LLM calls -- same guarantee as the main generated scrapers. Works for any
company by construction (the SerpAPI query is parameterized by name, not per-company code),
so this isn't the "per-domain hardcoded logic" the problem statement forbids.

Run:  python -m agent.linkedin_jobs "<Company Name>" [output.jsonl]
"""
import json
import os
import sys
from datetime import date, timedelta

import requests

SERPAPI_URL = "https://serpapi.com/search"

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
    first_segment = location_raw.split(";")[0].strip()
    parts = [p.strip() for p in first_segment.split(",")]
    if len(parts) >= 2:
        city = parts[0] or None
        state = parts[1] if len(parts) >= 3 else None
        country_raw = parts[-1]
        if country_raw.lower() in ("india", "in"):
            return (city, state, "India", "IN")
        return (city, state, country_raw or None, None)
    bare = first_segment.lower()
    if bare in _INDIA_CITY_FALLBACK:
        return (_INDIA_CITY_FALLBACK[bare], None, "India", "IN")
    return (None, None, None, None)


def parse_relative_date(text):
    """Typed parsing of SerpAPI's relative date extension (e.g. '6 days ago', '2 weeks ago',
    '1 month ago') into an absolute ISO date -- plain string ops, no regex. Returns None for
    any shape it doesn't recognize (never guesses)."""
    if not text:
        return None
    parts = text.lower().strip().split()
    if len(parts) != 3 or parts[-1] != "ago" or not parts[0].isdigit():
        return None
    n = int(parts[0])
    unit = parts[1].rstrip("s")
    days_per_unit = {"hour": 0, "day": 1, "week": 7, "month": 30, "year": 365}
    if unit not in days_per_unit:
        return None
    delta_days = n * days_per_unit[unit]
    return (date.today() - timedelta(days=delta_days)).isoformat()


def job_id_from_url(url):
    """The stable LinkedIn posting id is the trailing numeric path segment of the job URL
    (e.g. '.../jobs/view/engineer-at-acme-4435787778' -> '4435787778'). Plain string ops."""
    if not url:
        return None
    path = url.split("?", 1)[0].rstrip("/")
    tail = path.split("/")[-1]
    last_dash_segment = tail.split("-")[-1]
    return last_dash_segment if last_dash_segment.isdigit() else None


def _best_linkedin_link(job):
    src = job.get("source_link") or ""
    if "linkedin.com" in src:
        return src
    for opt in job.get("apply_options") or []:
        link = opt.get("link") or ""
        if "linkedin.com" in link:
            return link
    return None


def fetch(company_name, api_key=None, query_suffix="jobs India"):
    """Query SerpAPI Google Jobs for `<company_name> <query_suffix>`, keep only LinkedIn-sourced
    postings, structurally verify India location, return records matching the standard schema."""
    api_key = api_key or os.environ.get("SERPAPI_KEY")
    if not api_key:
        raise RuntimeError("SERPAPI_KEY not set")

    records = []
    seen_ids = set()
    start = 0
    for _ in range(3):  # SerpAPI paginates Google Jobs results in pages of ~10
        resp = requests.get(SERPAPI_URL, params={
            "engine": "google_jobs",
            "q": f"{company_name} {query_suffix}",
            "api_key": api_key,
            "start": start,
        }, timeout=20)
        if resp.status_code != 200:
            break
        data = resp.json()
        jobs = data.get("jobs_results") or []
        if not jobs:
            break

        for job in jobs:
            link = _best_linkedin_link(job)
            if not link:
                continue  # not a LinkedIn-sourced posting -- out of scope for this module

            city, state, country, country_code = resolve_location(job.get("location"))
            if country_code != "IN":
                continue  # structural India filter, same rule as the main scrapers

            jid = job_id_from_url(link)
            dedupe_key = jid or link
            if dedupe_key in seen_ids:
                continue
            seen_ids.add(dedupe_key)

            ext = job.get("detected_extensions") or {}
            posted_text = ext.get("posted_at")

            records.append({
                "title": job.get("title"),
                "job_id": jid,
                "location": {"city": city, "state": state, "country": country, "country_code": country_code},
                "url": link,
                "apply_url": link,
                "date_posted": parse_relative_date(posted_text),
                "date_posted_text": posted_text,
                "job_description": job.get("description"),
                "employment_type": ext.get("schedule_type"),
                "work_type": "Remote" if ext.get("work_from_home") else None,
                "salary_range": ext.get("salary"),
                "source": "linkedin",
            })

        start += 10
        if len(jobs) < 10:
            break

    return records


def write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m agent.linkedin_jobs \"<Company Name>\" [output.jsonl]", file=sys.stderr)
        return 1
    company = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else "linkedin_jobs.jsonl"
    try:
        records = fetch(company)
    except Exception as e:
        print(f"Error fetching LinkedIn jobs: {e}", file=sys.stderr)
        write_jsonl(out_path, [])
        return 1
    write_jsonl(out_path, records)
    print(f"Wrote {len(records)} India LinkedIn job(s) for '{company}' to {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
    sys.exit(main())
