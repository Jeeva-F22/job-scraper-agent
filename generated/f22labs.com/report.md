# Scraper report -- f22labs.com

**Status:** `success`
**Confidence:** 40.6%

- Careers URL: https://f22labs.com/careers/india
- Platform: zoho_recruit (0.99% confidence)
- Source type: embedded_json
- Pagination: page_number
- India jobs found: 2
- Repair attempts used: 0

## Evidence
- ✓ Direct ATS domain links point to f22labs.zohorecruit.in/jobs/Careers/...
- ✓ Page includes explicit Zoho Recruit branding: 'Powered by' -> https://www.zoho.in/recruit
- ✓ Known Zoho Recruit substrings were detected: 'zohorecruit.in' and 'zoho.in/recruit'
- ✓ Markdown preview shows Zoho Recruit job detail and application template variables like {{record.Posting_Title}}, {{candidate.Email}}, and {{topMessage}}
- ✓ Company logo is served from a Zoho Recruit asset path: /recruit/viewCareerImage.do?page_id=...
- ✓ Sample links include Zoho Recruit careers endpoints and share/apply-related Zoho-generated URLs
- ✓ fetch_raw https://f22labs.zohorecruit.in/jobs/Careers returned server HTML with job-detail links and embedded hidden_input:jobs JSON
- ✓ extract_hydration_json found hidden_input:jobs and hidden_input:meta blobs
- ✓ sample job record includes full Job_Description and City=Chennai
- ✓ job detail URLs are direct Zoho Recruit links and are SSR

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
python generated/f22labs.com/scraper.py out.jsonl
```
Produces `out.jsonl` (one India job per line). Runs anywhere with Python + `pip install requests beautifulsoup4 lxml`.

## Cross-platform: LinkedIn (bonus)
- Company name used for query: F22labs
- India job postings found on LinkedIn: 1
- See `linkedin_jobs.jsonl`. Sourced via SerpAPI's Google Jobs index -- never scrapes linkedin.com directly. Deterministic, no LLM calls.
- Rerun standalone: `python -m agent.linkedin_jobs "F22labs" linkedin_jobs.jsonl`

## Cost report
- LLM calls: 11
- Tool calls: 11
- Input tokens: 66291
- Output tokens: 4987
- Repair retries: 0
- Estimated cost: $0.2156
- Wall clock: 119.3s