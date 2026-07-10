# Scraper report -- swissre.com

**Status:** `success`
**Confidence:** 91.0%

- Careers URL: https://www.swissre.com/careers/india.html
- Platform: custom (0.8% confidence)
- Source type: rendered_list_ssr_detail
- Pagination: none
- India jobs found: 32
- Repair attempts used: 0

## Evidence
- ✓ SuccessFactors-backed custom careers site; public India listing page is server-rendered
- ✓ India careers page lists individual job-detail links; each detail page is plain server HTML
- ✓ Two-stage scrape: render the list once to collect job links, then plain-requests fetch each SSR detail page

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
python generated/swissre.com/scraper.py out.jsonl
```
Produces `out.jsonl` (one India job per line). Runs anywhere with Python + `pip install requests beautifulsoup4 lxml`.

## Cross-platform: LinkedIn (bonus)
- Skipped (SerpAPI unavailable or no key) -- see trace.jsonl for details.

## Cost report
- LLM calls: 12
- Tool calls: 10
- Input tokens: 0
- Output tokens: 0
- Repair retries: 0
- Estimated cost: $0.0
- Wall clock: 0s