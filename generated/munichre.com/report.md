# Scraper report -- munichre.com

**Status:** `success`
**Confidence:** 40.5%

- Careers URL: https://careers.munichre.com/en/munichre-search-results
- Platform: radancy (0.9% confidence)
- Source type: html_ssr
- Pagination: page_number
- India jobs found: 4
- Repair attempts used: 0

## Evidence
- ✓ The platform signal hits include 'radancy' with specific substrings like 'search-jobs' and 'search-filters__'.
- ✓ The markdown preview contains a logo URL that includes 'radancy' in its path: 'https://cdn.radancy.eu/company/3167/v1_0/logos/munichre-logo.webp'.
- ✓ The job detail pages contain the job title, location, and description in raw HTML, confirming SSR.
- ✓ The list page requires rendering to access job-detail links.
- ✓ Corrected source_type to html_ssr: raw no-JS fetch of https://careers.munichre.com/en/munichre-search-results already contains 15 job links -- rendering not needed.
- ✓ India facet id 1269750 activated via ?alrpm= and verified: 5 job links vs 15 unfiltered (facet count 5)

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
python generated/munichre.com/scraper.py out.jsonl
```
Produces `out.jsonl` (one India job per line). Runs anywhere with Python + `pip install requests beautifulsoup4 lxml`.

## Cost report
- LLM calls: 16
- Tool calls: 16
- Input tokens: 140567
- Output tokens: 4526
- Repair retries: 0
- Estimated cost: $0.39668
- Wall clock: 143.89s