# Career Search Dashboard

A local dashboard for full-time data science, applied ML and research roles. It includes experienced roles as well as new-graduate positions, prioritizing Apple, Google, NVIDIA, Meta, Genentech, Johnson & Johnson, AbbVie and Pfizer. The expanded nightly search also includes Amgen, Gilead, Eli Lilly, Medtronic, Illumina, Microsoft, Amazon and Tempus.

## Start locally

Use **Python 3.9+ on macOS or Linux** (Windows users: use WSL). The full-time workflow uses a small dependency set; no Torch or model downloads are needed.

```bash
git clone https://github.com/serendipitYang/job_seeking.git
cd job_seeking
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-fulltime.txt
cp fulltime.example.json fulltime.local.json
```

Add your own `resume.docx` or PDF to this directory, then edit `fulltime.local.json`: set `resume` to its filename and fill in your preferences, dates, keywords and companies. The sample is aimed at PhD-level ML/data/research searches in the US; it is not a worldwide or all-professions search engine. Start with one company to check your configuration:

```bash
python career.py update --company Microsoft
python career.py serve
```

For all configured companies, run `python career.py update`. Direct public collectors work without an API key; companies configured as `search` require the optional AI mode below. Searches can take several minutes and employers may throttle requests.

Open **http://127.0.0.1:7777**. The server only exposes the dashboard and job snapshot, not repository files or your resume. Reload fetches the latest saved results; it does not trigger paid searches. The page refreshes once per minute.

The example resume path is `resume.docx`; no resume is distributed. DOCX/PDF resumes, local preferences, keys and generated results are Git-ignored. For PDF parsing install `PyPDF2` in your Python environment. Personal job descriptions and scores stay under `output/fulltime/`.

`run_job_search.py` also defaults to this full-time update pipeline. The previous internship/Excel workflow is available with `--legacy-internships`; see [LEGACY.md](LEGACY.md). Its YAML settings do not control the new pipeline.

## Configure your search

Edit ignored `fulltime.local.json`:

- `preferences`: graduation date, earliest start, desired locations, remote preference and sponsorship requirement. Null/empty values mean unknown and are not automatic exclusions. `excluded_locations: ["New York"]` hides NY-only roles and skips their AI scoring; mixed-location or NY-restricted remote jobs need review. Preferred locations are scored first within each company. Start dates may be month precision, e.g. `2027-06`. User-reported OPT support, conditional future H1B needs and pending/contemplated immigration pathways are stored only in the ignored local config; pending applications are not treated as authorization.
- `keywords`: title fragments used for inexpensive prefiltering. Titles do not need to say “new graduate”; senior and experienced roles are retained.
- `companies`: searched in priority order. Workday and SmartRecruiters fetch full individual descriptions. Apple, Google, Meta, Amazon and Microsoft use direct public careers collectors. J&J uses AI search on official career domains. J&J's former Workday endpoint returned HTTP 422 during verification.
- `collection`: pagination and job caps. Reaching a cap is displayed as partial coverage. Increase these for broader collection.

Research equivalence is an assessment, not an employer guarantee. The prompt treats relevant doctoral work as 3–5 years, respects alternative PhD requirements, and distinguishes explicit industry/post-PhD requirements. Uncertain requirements go to review. Exclusions require a quote that occurs in the JD; you can display excluded roles in the dashboard.

## Enable OpenAI matching and search

Copy `.env.example` to `.env` and set `OPENAI_API_KEY` locally. Then:

```bash
python career.py update --ai
```

To refresh selected employers without re-searching the rest, use repeated company flags, for example
`python career.py update --ai --company Amgen --company Microsoft`.
Other companies retain their source status and freshness; nightly cron still searches all configured employers.

To score already collected jobs without another collection or paid web search, run
`python career.py match`. This uses the same cache and nightly budget.

This sends the resume text (with email and web links removed) and job descriptions to OpenAI for matching, using `store: false`. The search step sends professional interests rather than the resume. Never paste keys into source files or commit `.env`.

The implementation uses the [Responses API web search tool](https://developers.openai.com/api/docs/guides/tools-web-search) to search and open official pages, with [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs). It does not operate a logged-in browser or bypass CAPTCHA. JS-only, blocked or unindexed listings may be missed. AI-discovered jobs must have an allowed-domain URL present in the search sources; they are labeled as search-grounded and need a live availability check.

Default model: `gpt-5.4-mini`, configurable independently for scoring/search. Account availability must be confirmed with your key. Scores have six weighted dimensions: skills 25%, research 20%, domain 20%, seniority 15%, interests 10%, practical fit 10%. Each result includes strengths, gaps, unknowns and confidence. Scores measure fit, not hiring probability; absent AI results remain **Unscored**.

Cost controls: at most 64 scoring requests and 16 search requests per run; each search allows at most 3 built-in tool calls. Failed requests count toward the cap. Scores are cached by resume, JD, location, preferences, model and prompt version. Scoring proceeds round-robin across companies. Actual token counts appear in the dashboard. **A persistent local cost guard caps estimated API spending at $8 (or a lower configured `nightly_budget_usd`) per noon-to-noon America/Chicago window, shared across reruns.** It reserves a conservative context/output/tool-call allowance before requests and settles using returned token usage. Timeouts and ambiguous failures retain their reservations; explicit HTTP rejections release them. An API rejection stops further AI requests for that run while free collection continues. Pricing is pinned to GPT-5.4 Mini standard rates verified September 19, 2026; other models fail closed until a pricing rule is added. This is not an account-wide billing limit and does not cover other applications, taxes or future price changes. A second run shares the same budget ledger in `output/fulltime/budget.json`; do not delete that ledger during an active window. No paid calls occur without `--ai`.

This standalone client uses API-key billing; it does not consume your Codex/ChatGPT subscription allowance. Codex supports separate subscription and API-key authentication ([official authentication docs](https://learn.chatgpt.com/docs/auth)). API credits on the key's project, if available, can cover API use; account balances are not inspected by this app.

## Nightly update

Generate a cron entry for **02:00 in the machine's local timezone**:

```bash
python career.py cron
# Or enable paid AI calls for scheduled runs:
python career.py cron --ai
```

Paste the generated line into `crontab -e`. This command only prints the entry; it does not replace existing crontab entries. It records the absolute interpreter, script and config paths, loads the repo's `.env`, and appends logs to `output/nightly.log`. The updater works independently of the dashboard process. An overlapping update exits without making requests. A sleeping/offline laptop cannot execute cron; use an always-on machine if nightly execution must be reliable. The timezone can be checked in your operating-system settings.

The dashboard needs a running `career.py serve` process. No background dashboard login service is installed. To install or update the nightly cron entry while preserving unrelated entries, run `python scripts/install_nightly.py`; add `--ai` after a successful `python career.py probe`. The installer verifies the resulting entry and backs up the previous crontab under ignored `output/`.

## Reliability and verification

- Failed sources are visible; old jobs survive and are marked “Not refreshed this run.” Missing jobs are never automatically declared closed.
- Unknown posting dates remain visible; first/last seen dates are local observation times.
- Atomic snapshots keep the dashboard readable during updates.
- Resume/preference changes invalidate cached scores, including scores on older jobs.
- Search is selective and title filtering can miss unusual job titles; coverage is never a guarantee of every opening.

```bash
python -m unittest discover -s tests -v
git diff --check
```

Tests cover experienced/new-PhD inclusion, exclusion evidence, pagination and detail URLs, provenance filtering, cache invalidation, call limits and stale-job preservation. Live AI behavior requires your configured API key.

### Link verification and application tracking

Every update verifies saved employer links before AI scoring. Confirmed closed/missing postings are hidden by default and skipped during scoring. Blocked requests, JavaScript-only pages and other inconclusive checks remain labeled **unverified**; use the availability filter to show only confirmed open jobs. Checks are point-in-time evidence, not a guarantee that a role remains open. Recheck without paid AI using `python career.py verify` (optionally `--company "NVIDIA"`).

Cards show application deadlines only when explicitly supplied by employer job data or deadline text, plus the verification time. No deadline is guessed when one cannot be extracted.

Check **Applied** to save a row in `applications.xlsx`, sheet `Applications`, in this repo directory. The workbook is created on the first change and ignored by Git. It records job ID, employer, title, location, link, score, deadline, applied status and UTC timestamps. Repeated changes update the same row; unchecking preserves the first application timestamp. Records persist across nightly updates, even when jobs disappear. Close the workbook in Excel before changing a checkbox; failed saves show an error and restore the checkbox.

Customize `applications.workbook` and `applications.sheet` in `fulltime.local.json` for another `.xlsx` path or worksheet. Relative paths resolve from this repo. Existing unrelated worksheets and extra columns are preserved; incompatible headers are rejected. Add any custom workbook and its `.lock` file to your Git ignore rules. Restart `career.py serve` after changing configuration or server code.

### US scope and Apple catalog coverage

Apple now uses its public US job catalog directly, with no paid search calls required. Collection traverses catalog pages (up to `collection.apple_max_pages`, default 300), selects the configured title keywords, excludes internships, and retrieves full descriptions/qualifications from Apple's embedded router JSON. Verification requires the requested posting ID and full description; a page title or HTTP 200 alone is insufficient. Apple website language/country prefixes are not job locations. `companies[].seed_urls` can include explicit Apple job links to retain in discovery even if catalog pagination misses them; the example configuration has no personal seed jobs. Seeds still require verification and US eligibility.

The dashboard defaults to **Verified open** and **US locations**. The company selector includes verified-US counts, and search coverage follows the selected company. Explicitly non-US-only roles are removed from the active snapshot on every update and retained for audit in ignored `output/fulltime/excluded_non_us.json`; Excel application history is untouched. Unknown locations are hidden by default but accessible through the location filter. Mixed-location roles remain if there is a US option. New York exclusions still apply.

Apple coverage reports pages checked, unique listings seen, the reported catalog total and whether traversal completed. Completeness applies to the US catalog and configured title keywords at collection time; other company web searches remain selective. Failed/repeated pages and pagination limits must produce partial coverage, never an exhaustive claim. Availability checks can still be inconclusive or become stale between nightly runs.

### Google keyword search and verification

Google now uses direct, paginated Google Careers searches for `PhD New grad`, `AI`, `Data`, `Research Data Scientist`, `PhD`, and `New grad`. Configure these through Google's `queries` list, and set `collection.google_max_pages_per_query` (default 100) to control the traversal limit. Counts and completeness are reported separately per keyword; query totals overlap, while collected jobs are deduplicated by Google posting ID. Google's Careers portal includes YouTube and DeepMind roles, identified on each card.

Discovery keeps US research/data/AI roles and relevant PhD engineering opportunities, including experienced roles. Internship, student-researcher, apprenticeship and part-time titles and unrelated data-center facilities roles are excluded. Previously saved non-full-time Google roles are archived in ignored `output/fulltime/excluded_employment.json`. Generic engineering titles found through AI searches can qualify when the JD explicitly describes machine learning or related work. Direct collection and verification require no paid AI calls. Individual verification checks the selected job's ID, qualifications, description and application link; surrounding search results on a missing-job page cannot verify that job.

The company coverage panel includes per-keyword page/result counts. Match scoring still uses the existing shared nightly budget and call cap; verified roles are scored first, then preferred locations, with data science/research and 2027 PhD titles prioritized within those groups. Broad discovery does not mean every retained technical role is a strong resume match; unscored roles remain clearly marked.

### Personal reach feedback

Each card has an **Over my reach** checkbox beside **Applied**. It saves independently to Git-ignored `over_my_reach.json` in the repo directory, created on the first change. Checked and unchecked changes retain UTC timestamps and snapshots of the job description, employer, location, URL, AI match assessment and availability evidence for future analysis. Repeating the same state does not duplicate history. Unchecking preserves the earlier feedback, and labels survive nightly refreshes and jobs leaving the shortlist. This feedback does not automatically change scores or hide jobs. Failed saves restore the checkbox and show an error.

### Meta catalog discovery

Meta now uses the careers site's public, logged-out catalog search. Its website paginates an all-jobs response locally; the collector retrieves that response and compares unique job IDs against Meta's separate reported count. The coverage panel reports a partial result if these counts differ. Public search operation IDs are discovered from the current website bundles, rather than permanently hardcoded; schema changes fail visibly.

Title keywords cover data science, analytics, research, AI, machine learning, PhD and data engineering roles. Each relevant posting is checked against its canonical job ID and employer JobPosting data, including qualifications, responsibilities, employment type and country. Internships, contract/temporary roles and non-US roles are archived outside the active results; NY-only roles retain the existing exclusion. Experienced roles remain candidates for resume scoring. URL aliases use the same posting ID so existing Applied and Over my reach records stay linked.

No Meta account login or applicant data is accessed; direct discovery and verification have no LLM cost. `career.py update --company Meta --ai` adds scoring within the shared nightly budget and call cap. A blocked request or changed site schema remains an error or inconclusive check, not proof that a job closed. The nightly schedule automatically includes the new collector.

### Amazon and Microsoft discovery

Both employers use their public website search endpoints, with paginated searches for Data Scientist, Applied Scientist, Research Scientist, Machine Learning, PhD, New Graduate, NLP, LLM and AI. Override `queries` per company and `collection.amazon_max_pages_per_query` / `microsoft_max_pages_per_query` (default 250). Per-query totals overlap; stable posting IDs deduplicate results and preserve tracking IDs. Searches run sequentially, with bounded rate-limit retries; incomplete traversal and changing counts are reported as partial. This is keyword coverage, not a claim to cover every potentially relevant job.

Non-US and non-full-time roles are filtered. Amazon verification requires the exact canonical ID, job-specific application link and current description/qualification sections. Microsoft verification requires the exact requested ID and full description from the public detail endpoint. Neither uses applicant accounts. Discovery and verification incur no LLM cost; scoring uses the existing shared nightly cap. These collectors run automatically in nightly updates.

The scoring queue now prioritizes non-senior titles ahead of senior titles, then principal/staff/lead/manager/director titles, within availability and location preferences. This is a queue hint, not an eligibility decision: experienced roles remain available, and the LLM still evaluates explicit PhD alternatives and actual requirements. Applied and Over my reach records are unchanged.

## Sharing and contributing

Fork this repository and configure your own ignored `fulltime.local.json` and `.env`. Never add real resumes, keys, application records, feedback files or generated snapshots to a pull request. The dashboard binds to localhost and is intended for one user; do not expose it directly on the internet. AI mode sends resume text and job descriptions to OpenAI; email/link removal is not full anonymization.

The project is available under the [MIT license](LICENSE). Contributions to employer collectors, verification, tests and documentation are welcome. Include a sanitized fixture and reproduction steps for source failures; do not include private job-search records. Run the Python tests above and `node tests/dashboard_filters.cjs` when changing the dashboard. The original internship workflow and its heavier dependencies remain documented in [LEGACY.md](LEGACY.md).
