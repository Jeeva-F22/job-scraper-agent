# Scraper report -- accenture.com

**Status:** `success`
**Confidence:** 40.5%

- Careers URL: https://www.accenture.com/in-en/careers/jobsearch
- Platform: workday (0.9% confidence)
- Source type: rendered_list_ssr_detail
- Pagination: unknown
- India jobs found: 12
- Repair attempts used: 0

## Evidence
- ✓ Detected 'myworkdayjobs.com' in platform signal hits, which is a strong indicator of Workday usage.
- ✓ Rendered page contains individual job-detail links.
- ✓ Attempts to access Workday API endpoints returned 404 errors.

## Validation
- json_valid: ✓
- output_file_exists: ✓
- schema_complete: ✓
- location_shape_ok: ✓
- all_jobs_india: ✓
- no_duplicates: ✓
- urls_absolute: ✓
- titles_mostly_present: ✓

## How to run the generated scraper standalone (no agent, no LLM)
```bash
# this site needs JS/bot-protection rendering, so set your Firecrawl key first:
set FIRECRAWL_API_KEY=fc-...        # Windows (Linux/Mac: export FIRECRAWL_API_KEY=fc-...)
python generated/accenture.com/scraper.py out.jsonl
```
Produces `out.jsonl` (one India job per line). Runs anywhere with Python + `pip install requests beautifulsoup4 lxml`.

## Cost report
- LLM calls: 17
- Tool calls: 13
- Input tokens: 197015
- Output tokens: 3681
- Repair retries: 0
- Estimated cost: $0.52935
- Wall clock: 371.37s