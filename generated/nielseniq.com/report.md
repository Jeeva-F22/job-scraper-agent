# Scraper report -- nielseniq.com

**Status:** `success`
**Confidence:** 97.0%

- Careers URL: https://nielseniq.com/global/en/jobs/?s=&market=global&language=en&orderby=&order=&post_type=career_job&job_locations=india&job_teams=&job_types=
- Platform: custom (0.91% confidence)
- Source type: rest_api
- Pagination: page_number
- India jobs found: 48
- Repair attempts used: 0

## Evidence
- ✓ The careers URL is on nielseniq.com and the sample links are all NIQ corporate site pages, not a hosted ATS domain.
- ✓ The only ATS-related signal is a substring hit for "smartrecruiters.com", but no actual SmartRecruiters careers/apply links or embedded SmartRecruiters widgets are shown in the sample links or markdown preview.
- ✓ No hydration blobs or frontend framework signals indicate a known ATS frontend.
- ✓ The page content preview looks like a WordPress-style corporate careers page with internal navigation, suggesting the careers listing may be custom-rendered or proxying jobs data rather than being a direct ATS-hosted careers site.
- ✓ Raw HTML contained SSR job cards with individual job-detail links and hidden filter inputs for job_locations=india.
- ✓ WordPress VIP headers and Link header exposed wp-json endpoint for job_locations term 14549.
- ✓ Verified India term JSON: https://nielseniq.com/wp-json/wp/v2/job_locations/14549 returns count 48 and link https://nielseniq.com/global/en/jobs/india/.
- ✓ Verified job list API: https://nielseniq.com/wp-json/wp/v2/career_job?job_locations=14549&per_page=1&page=1 returns real job records with full content.description in content.rendered.
- ✓ Verified pagination via X-WP-TotalPages=48 and next Link header to page=2.
- ✓ Verified SSR detail pages at https://nielseniq.com/global/en/jobs/research-analyst-2/ and https://nielseniq.com/global/en/jobs/research-associate/.

## Validation
- json_valid: ✓
- output_file_exists: ✓
- schema_complete: ✓
- all_jobs_india: ✓
- no_duplicates: ✓
- urls_absolute: ✓
- titles_present: ✓

## How to run the generated scraper standalone (no agent, no LLM)
```bash
# no API key needed -- this scraper uses a direct API / plain HTTP
python generated/nielseniq.com/scraper.py out.jsonl
```
Produces `out.jsonl` (one India job per line). Runs anywhere with Python + `pip install requests beautifulsoup4 lxml`.

## Cross-platform: LinkedIn (bonus)
- Company name used for query: Nielseniq
- India job postings found on LinkedIn: 0
- See `linkedin_jobs.jsonl`. Sourced via SerpAPI's Google Jobs index -- never scrapes linkedin.com directly. Deterministic, no LLM calls.
- Rerun standalone: `python -m agent.linkedin_jobs "Nielseniq" linkedin_jobs.jsonl`

## Cost report
- LLM calls: 20
- Tool calls: 16
- Input tokens: 179422
- Output tokens: 6048
- Repair retries: 0
- Estimated cost: $0.50904
- Wall clock: 163.31s