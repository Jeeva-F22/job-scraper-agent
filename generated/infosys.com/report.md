# Scraper report -- infosys.com

**Status:** `success_empty`
**Confidence:** 40.6%

- Careers URL: https://career.infosys.com/joblist?companyhiringtype=BPM&countrycode=IN
- Platform: custom (0.98% confidence)
- Source type: html_ssr
- Pagination: page_number
- India jobs found: 0
- Repair attempts used: 0

## Evidence
- ✓ Domain and branding are Infosys-specific: career.infosys.com, Infosys logo, and job content references Infosys BPM Limited.
- ✓ No known ATS substring hits were reported in platform_signal_hits.
- ✓ The page exposes Angular via ng-version, indicating a custom Angular frontend rather than a recognizable ATS template.
- ✓ Sample links are first-party app routes (/login, /register, /offerValidation) instead of standard ATS-hosted job/apply URLs.
- ✓ Markdown preview shows a bespoke job listing experience with filters, location chips, and inline job cards, consistent with a custom careers portal.
- ✓ Raw HTML for the careers URL contains job card text directly, including titles and locations.
- ✓ fetch_rendered shows the same job cards without needing interactive JS.
- ✓ No hydration JSON blobs were found.
- ✓ No verified API endpoint was discovered.
- ✓ The page is a custom Angular frontend, but the job list content is present in server HTML, so browser execution is not required for scraping the list.

## Validation
- json_valid: ✓
- output_file_exists: ✓
- note: zero jobs written

## How to run the generated scraper standalone (no agent, no LLM)
```bash
# no API key needed -- this scraper uses a direct API / plain HTTP
python generated/infosys.com/scraper.py out.jsonl
```
Produces `out.jsonl` (one India job per line). Runs anywhere with Python + `pip install requests beautifulsoup4 lxml`.

## Cross-platform: LinkedIn (bonus)
- Company name used for query: Infosys
- India job postings found on LinkedIn: 2
- See `linkedin_jobs.jsonl`. Sourced via SerpAPI's Google Jobs index -- never scrapes linkedin.com directly. Deterministic, no LLM calls.
- Rerun standalone: `python -m agent.linkedin_jobs "Infosys" linkedin_jobs.jsonl`

## Cost report
- LLM calls: 16
- Tool calls: 14
- Input tokens: 84659
- Output tokens: 3975
- Repair retries: 0
- Estimated cost: $0.2514
- Wall clock: 80.27s