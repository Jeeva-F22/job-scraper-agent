# AI Agent That Writes Job-Scraper Scripts

Given only a company domain, this agent investigates the site and generates a
standalone Python scraper that extracts that company's India-based job listings —
zero human intervention, zero per-domain hardcoded logic.

## What makes this different from "search → LLM writes scraper → done"

1. **Real software-engineering loop, not a fixed pipeline.** `agent/orchestrator.py`
   sequences Discover → Fingerprint → Reverse-engineer → Architect → Codegen →
   Sandbox run → Validate → Repair (≤3 attempts) → Memory write → Report. Discovery
   and reverse-engineering are *agentic tool loops* (`llm.agentic_loop` in
   `agent/llm.py`) — the LLM itself picks which tool to call next (search, fetch,
   render, grep a JS bundle, probe a candidate API) and decides when it has enough
   evidence, based on what it's seen so far. Nothing here is `if domain == "x"`.

2. **Agent-authored platform memory (`agent/memory.py`).** After a successful run,
   the agent writes its own fingerprint signature + verified plan + scraper code to
   `platform_memory.json`. A later domain on the same platform gets that as a
   *starting-point hint* — still independently re-verified against the new site,
   never blindly reused. This is the efficiency story: token/cost/latency drop on
   repeat platforms, entirely self-taught, no human-written per-domain branch. Check
   `report.md`'s cost section on a second same-platform run to see it in action.

3. **Three-way validator (`agent/validator.py`), not pass/fail.** Distinguishes
   `success` (India jobs found), `success_empty` (ran fine, legitimately zero
   results — no jobs at all, or jobs exist but none in India), and `failure`
   (broken/blocked/malformed). This is the case most naive submissions get wrong.

4. **Confidence + evidence at every stage**, not silent guesses — see
   `report.md` per domain.

5. **Cost/trace report per domain** — tokens, LLM calls, tool calls, retries, wall
   clock, estimated $.

6. **Handles hard, multi-hop, bot-protected career sites** (e.g. `swissre.com`).
   Discovery follows region/country navigation (Careers → Asia Pacific → India →
   "View roles") to reach the India-specific listing, and prefers a public SSR page
   over a login-walled ATS SPA. Reverse-engineering recognizes when the job *list*
   only appears after JS/AJAX rendering but each job *detail* page is plain server
   HTML, and emits a **two-stage scraper**: render the list (via the Firecrawl API,
   which also bypasses Cloudflare bot-challenges that block a raw headless browser)
   to collect job-detail links, then plain-`requests`-fetch each SSR detail page. It
   feeds the codegen a cleaned sample of the *real* detail HTML + JSON-LD so the
   generated selectors match the actual DOM instead of being guessed.

7. **Hirevox tie-in (`hirevox_demo/query.py`).** A voice hiring agent's first
   question is "is this company even hiring in India right now?" — that's exactly
   what `generated/<domain>/output.jsonl` answers. This script demos querying
   across every domain the agent has scraped, no new scraping involved.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# fill in .env:
#   OPENAI_API_KEY=...
#   SERPAPI_KEY=...        (serper.dev also fine, wrapper falls back to Firecrawl search)
#   FIRECRAWL_API_KEY=...
```

## Run — Web UI (recommended for demos)

```bash
python ui/app.py
# open http://localhost:5000
```

Type any company domain (just `swissre` works — it's normalized to `swissre.com`) and hit **Run agent**.
You watch the agent live: every pipeline stage, every decision it makes with its evidence and confidence,
every tool call — streamed from the run's trace as it happens. When it finishes you get the India-jobs
table, run stats (LLM calls, tokens, $ cost, wall clock), and download buttons for `scraper.py`,
`output.jsonl`, `trace.jsonl`, and the report.

The outcome banner is honest three-way: green = jobs extracted, amber = valid scraper but zero India
jobs on the site right now, red = failure with the reason (no fabricated results, ever).

## Run — CLI

```bash
python -m agent.orchestrator run swissre.com
```

Outputs land in `generated/<domain>/`:
- `scraper.py` — the standalone generated scraper (no LLM calls at runtime)
- `output.jsonl` — one India job per line, per the required schema (§5)
- `trace.jsonl` — full reasoning/tool-call trace of the agent's run
- `report.json` / `report.md` — status, confidence, evidence, validation checks, cost.
  `report.md` prints the exact standalone run command for that scraper.

## Running a generated scraper on its own (no agent, no LLM)

This is the deliverable the graded run produces — anyone can run it anywhere with just
Python + `pip install requests beautifulsoup4 lxml`:

```bash
# Clean ATS sites (e.g. Greenhouse — razorpay, figma): no key needed, hits a JSON API
python generated/razorpay.com/scraper.py out.jsonl

# JS / bot-protected sites (e.g. swissre): the scraper renders the listing via Firecrawl,
# so set your Firecrawl key first (it is a rendering service, NOT an LLM):
set FIRECRAWL_API_KEY=fc-...          # Windows  (Linux/Mac: export FIRECRAWL_API_KEY=fc-...)
python generated/swissre.com/scraper.py out.jsonl
```

Each line of `out.jsonl` is one India-based job matching the schema below. An empty file
is a valid result (the company has no open India roles).

## Output schema

```json
{
  "title": "...", "job_id": "...",
  "location": {"city": null, "state": null, "country": "India", "country_code": "IN"},
  "url": "...", "apply_url": "...",
  "date_posted": "2026-01-15", "date_posted_text": "Posted 3 days ago",
  "job_description": "...",
  "employment_type": null, "work_type": null, "salary_range": null
}
```
Missing fields are always `null` — never inferred, never guessed.

## Edge cases this is built to handle

See the table in the plan / `agent/validator.py` docstring: no careers page, zero
jobs total, jobs but none in India, multi-page pagination, GraphQL backends,
infinite scroll/SPA-only sources, bot protection (honest failure, not a hang),
missing fields, duplicate jobs, relative URLs, unparseable dates, rate limiting,
and post-generation script failure (repair loop).

## Repo layout

```
agent/            the agent itself
generated/<domain>/  one folder per domain the agent has run against
platform_memory.json  agent's own cross-run platform pattern cache
hirevox_demo/query.py stretch: cross-domain query demo
```
