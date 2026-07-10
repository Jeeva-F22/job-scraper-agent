# Scraper report -- linear.app

**Status:** `success_empty`
**Confidence:** 40.5%

- Careers URL: https://linear.app/careers
- Platform: custom (0.9% confidence)
- Source type: html_ssr
- Pagination: none
- India jobs found: 0
- Repair attempts used: 0

## Evidence
- ✓ No known ATS platform signals detected.
- ✓ No frontend framework signals detected.
- ✓ No hydration JSON blobs found, indicating a lack of common SPA frameworks or known platforms.
- ✓ Job-detail links are present in the raw HTML of the careers page.
- ✓ Individual job-detail pages are server-side rendered with job information in the raw HTML.

## Validation
- json_valid: ✓
- output_file_exists: ✓
- note: zero jobs written

## How to run the generated scraper standalone (no agent, no LLM)
```bash
# no API key needed -- this scraper uses a direct API / plain HTTP
python generated/linear.app/scraper.py out.jsonl
```
Produces `out.jsonl` (one India job per line). Runs anywhere with Python + `pip install requests beautifulsoup4 lxml`.

## Cost report
- LLM calls: 10
- Tool calls: 5
- Input tokens: 53139
- Output tokens: 3159
- Repair retries: 0
- Estimated cost: $0.16444
- Wall clock: 299.53s