# Scraper report -- razorpay.com

**Status:** `success`
**Confidence:** 40.6%

- Careers URL: https://job-boards.greenhouse.io/razorpaysoftwareprivatelimited
- Platform: greenhouse (0.95% confidence)
- Source type: rest_api
- Pagination: none
- India jobs found: 14
- Repair attempts used: 0

## Evidence
- ✓ The URL structure is 'job-boards.greenhouse.io', which is a known pattern for Greenhouse-hosted job boards.
- ✓ The platform signal hits include 'greenhouse.io' and 'boards.greenhouse.io', both of which are associated with Greenhouse.
- ✓ Sample links contain 'job-boards.greenhouse.io', indicating the use of Greenhouse.
- ✓ The URL structure is 'job-boards.greenhouse.io', which is a known pattern for Greenhouse-hosted job boards.
- ✓ The platform signal hits include 'greenhouse.io' and 'boards.greenhouse.io', both of which are associated with Greenhouse.
- ✓ Sample links contain 'job-boards.greenhouse.io', indicating the use of Greenhouse.

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
python generated/razorpay.com/scraper.py out.jsonl
```
Produces `out.jsonl` (one India job per line). Runs anywhere with Python + `pip install requests beautifulsoup4 lxml`.

## Cost report
- LLM calls: 9
- Tool calls: 7
- Input tokens: 41378
- Output tokens: 2445
- Repair retries: 0
- Estimated cost: $0.1279
- Wall clock: 58.06s