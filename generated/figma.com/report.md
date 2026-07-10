# Scraper report -- figma.com

**Status:** `success`
**Confidence:** 40.5%

- Careers URL: https://www.figma.com/careers/
- Platform: greenhouse (0.9% confidence)
- Source type: rest_api
- Pagination: none
- India jobs found: 2
- Repair attempts used: 0

## Evidence
- ✓ The platform signal hits include 'greenhouse.io' and 'boards.greenhouse.io', which are strong indicators of the Greenhouse platform.
- ✓ The careers page uses the Greenhouse platform, confirmed by the presence of 'boards-api.greenhouse.io' in the raw HTML.

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
# no API key needed -- this scraper uses a direct API / plain HTTP
python generated/figma.com/scraper.py out.jsonl
```
Produces `out.jsonl` (one India job per line). Runs anywhere with Python + `pip install requests beautifulsoup4 lxml`.

## Cost report
- LLM calls: 11
- Tool calls: 5
- Input tokens: 60596
- Output tokens: 2686
- Repair retries: 0
- Estimated cost: $0.17835
- Wall clock: 123.22s