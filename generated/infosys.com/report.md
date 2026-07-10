# Scraper report -- infosys.com

**Status:** `success_empty`
**Confidence:** 40.4%

- Careers URL: https://career.infosys.com/joblist?countrycode=IN&companyhiringtype=IL
- Platform: custom (0.82% confidence)
- Source type: spa_needs_browser
- Pagination: load_more
- India jobs found: 0
- Repair attempts used: 1

## Evidence
- ✓ No known ATS/platform substring hits were detected in the collected signals.
- ✓ Careers site is hosted on Infosys-owned domain/path: career.infosys.com/joblist, with first-party routes such as /login, /register, and /offerValidation rather than Greenhouse/Lever/Workday/Ashby-style URLs.
- ✓ Frontend framework signal shows Angular via ng-version.
- ✓ No recognizable ATS hydration blobs were found.
- ✓ Markdown preview shows a branded Infosys job search/listing experience with custom UI labels such as 'Validate and Accept Offer', 'Get a head start by uploading your resume', and 'Hot Jobs in All Locations'.
- ✓ Actual job listings appear in the fetched preview, but the structure does not match common hosted ATS patterns.
- ✓ Raw GET of https://career.infosys.com/joblist?countrycode=IN&companyhiringtype=IL returned the Angular application shell with scripts (runtime.js/scripts.js/main.js) and no usable individual job-detail links in the raw HTML.
- ✓ Rendered fetch of the same URL produced actual job rows in the page markdown, e.g. location/company 'BANGALORE, Infosys Limited', title 'Senior Technologist MEAN/MERN- Q2 FY 26', experience 'Work Experience of 9 Years to 15 Years', and full description text; another rendered row was 'Workday FI Consultant'.
- ✓ Hydration extraction found no __NEXT_DATA__/__NUXT__/initial state blobs.
- ✓ The environment config was verified at https://career.infosys.com/assets/environments/environment.json and exposes JobsUnAuthUrl = https://intapgateway.infosysapps.com/careersci/search/intapjbsrch/, but guessed candidate endpoints getJobList, getHotJobs, jobs, and getAllJobs all returned 404 JSON errors, so no verified REST job-list endpoint was identified within the budget.
- ✓ Rendered page links list did not expose job-detail URLs, only login/register/offerValidation/fraud-alert/# and javascript void links.

## Validation
- json_valid: ✓
- output_file_exists: ✓
- note: zero jobs written; script stderr: Warning: Firecrawl returned no rendered Infosys job-list HTML; direct page is reachable but contains only the Angular shell. Writing empty output.


## How to run the generated scraper standalone (no agent, no LLM)
```bash
# this site needs JS/bot-protection rendering, so set your Firecrawl key first:
set FIRECRAWL_API_KEY=fc-...        # Windows (Linux/Mac: export FIRECRAWL_API_KEY=fc-...)
python generated/infosys.com/scraper.py out.jsonl
```
Produces `out.jsonl` (one India job per line). Runs anywhere with Python + `pip install requests beautifulsoup4 lxml`.

## Cost report
- LLM calls: 33
- Tool calls: 60
- Input tokens: 421896
- Output tokens: 27688
- Repair retries: 1
- Estimated cost: $1.33162
- Wall clock: 1410.2s