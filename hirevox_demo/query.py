"""Hirevox tie-in demo.

Hirevox is the user's product: AI voice agents that call/screen candidates for
companies. The missing piece for a voice agent doing outbound "we're hiring for X"
calls is knowing, right now, which companies actually have open India roles --
that's exactly what generated/<domain>/output.jsonl files are. This script is a
tiny illustration of that reuse path: it loads every domain's generated output
and answers "is <company> hiring in India for <role>?" without any new scraping.

Usage:
    python hirevox_demo/query.py "is swissre hiring in India for a software engineer"
    python hirevox_demo/query.py --company swissre.com --role engineer
"""
import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATED_DIR = os.path.join(ROOT, "generated")


def load_all():
    """Load {domain: {report, jobs}} for every domain the agent has generated a scraper for."""
    out = {}
    if not os.path.isdir(GENERATED_DIR):
        return out
    for domain in os.listdir(GENERATED_DIR):
        d = os.path.join(GENERATED_DIR, domain)
        report_path = os.path.join(d, "report.json")
        jobs_path = os.path.join(d, "output.jsonl")
        if not os.path.exists(report_path):
            continue
        with open(report_path, "r", encoding="utf-8") as f:
            report = json.load(f)
        jobs = []
        if os.path.exists(jobs_path):
            with open(jobs_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        jobs.append(json.loads(line))
        out[domain] = {"report": report, "jobs": jobs}
    return out


def find_company(all_data, company_query):
    company_query = company_query.lower()
    matches = [d for d in all_data if company_query in d.lower()]
    return matches


def query(company_query, role_query=None):
    all_data = load_all()
    matches = find_company(all_data, company_query)
    if not matches:
        known = ", ".join(sorted(all_data.keys())) or "(none generated yet)"
        return {
            "answer": f"No generated scraper found for a company matching '{company_query}'. "
                      f"Known domains: {known}",
            "matched_domain": None,
            "jobs": [],
        }
    domain = matches[0]
    entry = all_data[domain]
    report = entry["report"]
    jobs = entry["jobs"]

    if report.get("overall_status") == "no_script_generated":
        return {"answer": f"{domain}: {report.get('reason')}", "matched_domain": domain, "jobs": []}

    if role_query:
        rq = role_query.lower()
        jobs = [j for j in jobs if j.get("title") and rq in j["title"].lower()]

    if not jobs:
        reason = "no India-based roles" if not role_query else f"no India-based '{role_query}' roles"
        return {
            "answer": f"{domain} is not currently hiring for {reason} "
                      f"(scraper status: {report.get('overall_status')}, "
                      f"confidence {report.get('confidence_pct')}%).",
            "matched_domain": domain,
            "jobs": [],
        }

    titles = "; ".join(j.get("title") or "untitled" for j in jobs[:5])
    return {
        "answer": f"Yes -- {domain} has {len(jobs)} matching India role(s): {titles}"
                  + (" ..." if len(jobs) > 5 else ""),
        "matched_domain": domain,
        "jobs": jobs,
    }


def main():
    parser = argparse.ArgumentParser(description="Query generated scraper outputs (Hirevox tie-in demo)")
    parser.add_argument("freeform", nargs="?", help='e.g. "is swissre hiring in India for a software engineer"')
    parser.add_argument("--company", help="company/domain substring")
    parser.add_argument("--role", help="role/title substring")
    args = parser.parse_args()

    company, role = args.company, args.role
    if args.freeform and not company:
        # Extremely light heuristic parse for the demo CLI, not the agent's extraction logic.
        words = args.freeform.lower().replace("?", "").split()
        if "is" in words:
            company = words[words.index("is") + 1]
        if "for" in words:
            role = " ".join(words[words.index("for") + 1:])

    if not company:
        parser.error("Provide a freeform query or --company")

    result = query(company, role)
    print(result["answer"])
    if result["jobs"]:
        print(json.dumps(result["jobs"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
