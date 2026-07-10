# Scraper report -- cognizant.com

**Status:** `success`
**Confidence:** 40.6%

- Careers URL: https://careers.cognizant.com/india-en/jobs/
- Platform: custom (0.96% confidence)
- Source type: html_ssr
- Pagination: page_number
- India jobs found: 5
- Repair attempts used: 1

## Evidence
- ✓ No known ATS substring hits were detected in the page signals.
- ✓ No frontend framework hits were detected.
- ✓ No hydration blobs were found, suggesting this is not a typical SPA/ATS widget shell.
- ✓ The URL structure and content are branded as Cognizant Careers with many localized paths under careers.cognizant.com, indicating a company-owned careers site rather than a third-party ATS domain.
- ✓ Sample links include internal job detail pages and paginated results on the same domain (e.g. /india-en/jobs/00069634682/... and /india-en/jobs/?page=2#results), which is consistent with a custom careers implementation.
- ✓ fetch_raw https://careers.cognizant.com/india-en/jobs/ returned full HTML with job-detail links in the raw page source, including /india-en/jobs/00069634682/uipath-engineer-agentic/ and /india-en/jobs/?page=2#results
- ✓ fetch_raw https://careers.cognizant.com/india-en/jobs/?page=2#results returned a server-rendered page shell with page-specific title '... - Page 2'
- ✓ sitemap.xml exists and includes the India jobs landing page plus other regional jobs landing pages
- ✓ The site is a custom Cognizant careers portal on the company domain, not a known ATS, and no JS hydration/API was needed to see job links

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
python generated/cognizant.com/scraper.py out.jsonl
```
Produces `out.jsonl` (one India job per line). Runs anywhere with Python + `pip install requests beautifulsoup4 lxml`.

## Cross-platform: LinkedIn (bonus)
- Company name used for query: Cognizant
- India job postings found on LinkedIn: 3
- See `linkedin_jobs.jsonl`. Sourced via SerpAPI's Google Jobs index -- never scrapes linkedin.com directly. Deterministic, no LLM calls.
- Rerun standalone: `python -m agent.linkedin_jobs "Cognizant" linkedin_jobs.jsonl`

## Cost report
- LLM calls: 14
- Tool calls: 15
- Input tokens: 138036
- Output tokens: 8298
- Repair retries: 1
- Estimated cost: $0.42807
- Wall clock: 416.98s