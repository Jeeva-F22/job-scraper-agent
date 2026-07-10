# Scraper report -- swissre.com

**Status:** `failure`
**Confidence:** 0.5%

- Careers URL: https://www.swissre.com/careers/india.html
- Platform: custom (0.8% confidence)
- Source type: html_ssr
- Pagination: unknown
- India jobs found: 0
- Repair attempts used: 3

## Evidence
- ✓ No known ATS platform signals detected.
- ✓ No frontend framework signals detected.
- ✓ No hydration JSON blobs found.
- ✓ Job detail pages contain job title, location, and description in raw HTML.
- ✓ Job listings are accessible via a separate job search page.
- ✓ Corrected source_type to html_ssr: raw no-JS fetch of https://www.swissre.com/careers/jobSearch.html already contains 32 job links -- rendering not needed.

## Validation
- note: script timed out (possible hang / infinite loop / stuck on bot protection)

## How to run the generated scraper standalone (no agent, no LLM)
```bash
# no API key needed -- this scraper uses a direct API / plain HTTP
python generated/swissre.com/scraper.py out.jsonl
```
Produces `out.jsonl` (one India job per line). Runs anywhere with Python + `pip install requests beautifulsoup4 lxml`.

## Cost report
- LLM calls: 18
- Tool calls: 10
- Input tokens: 165009
- Output tokens: 8078
- Repair retries: 3
- Estimated cost: $0.4933
- Wall clock: 1387.97s