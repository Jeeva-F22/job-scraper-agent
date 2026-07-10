# Scraper report -- f22labs.com

**Status:** `success_empty`
**Confidence:** 40.6%

- Careers URL: https://f22labs.com/careers/india
- Platform: zoho_recruit (0.99% confidence)
- Source type: html_ssr
- Pagination: none
- India jobs found: 0
- Repair attempts used: 0

## Evidence
- ✓ Job links point to the company’s Zoho Recruit subdomain: https://f22labs.zohorecruit.in/jobs/Careers/...
- ✓ Markdown preview includes a visible “Powered by” link to https://www.zoho.in/recruit
- ✓ Company logo and career assets are loaded from f22labs.zohorecruit.in/recruit/viewCareerImage.do
- ✓ Zoho Recruit-style template placeholders are present, such as {{getI18n(...)}} and {{record.Posting_Title}}
- ✓ The page structure includes Zoho Recruit career-site paths like /jobs/Careers and /jobs/Careers#top
- ✓ Raw GET of https://f22labs.com/careers/india returned 200 after redirecting to https://f22labs.zohorecruit.in/jobs/Careers, confirming the actual underlying list host/path.
- ✓ The no-JS careers HTML/markdown contains individual Zoho Recruit job-detail links, including /jobs/Careers/65449000002129032/Senior-Project-Manager?source=CareerSite and /jobs/Careers/65449000000416161/Product-Management-Intern?source=CareerSite, so the list is server-side scrapeable and should not be classified as browser-only.
- ✓ Raw GET of the Senior Project Manager detail URL returned 200 with title/meta content: <title>F22Labs - Senior Project Manager in Chennai</title> and description text beginning 'F22Labs Who we are: F22 Labs was started in 2014...', confirming detail pages are also SSR/plain HTML.
- ✓ Raw GET of the Product Management Intern detail URL returned 200 with title/meta content: <title>F22Labs - Product Management Intern in Chennai</title>, again confirming SSR job details.
- ✓ https://f22labs.zohorecruit.in/sitemap.xml redirected to Zoho Accounts sign-in/IAM security error, so sitemap is not a public listing source here.

## Validation
- json_valid: ✓
- output_file_exists: ✓
- note: zero jobs written

## How to run the generated scraper standalone (no agent, no LLM)
```bash
# no API key needed -- this scraper uses a direct API / plain HTTP
python generated/f22labs.com/scraper.py out.jsonl
```
Produces `out.jsonl` (one India job per line). Runs anywhere with Python + `pip install requests beautifulsoup4 lxml`.

## Cost report
- LLM calls: 10
- Tool calls: 14
- Input tokens: 68725
- Output tokens: 15383
- Repair retries: 0
- Estimated cost: $0.32564
- Wall clock: 530.76s