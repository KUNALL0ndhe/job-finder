# Job search stack — discovery + assisted apply

An **assisted** PM job-search setup for associate/junior roles in the
Netherlands, Germany, Ireland (visa sponsorship wanted) and India
(B2B retail commerce). Two halves, joined by one CSV:

```
 DISCOVERY  ───────────────▶  jobs.csv  ──────────▶  APPLY (you press submit)
 scrape_jobs.py (JobSpy)        pick.py              career-ops  (separate install)
```

The discovery half **never applies** — it reads public aggregators and writes a
CSV. The apply half (career-ops) **drafts** a CV + cover letter and **never
submits**; you always make the final call. That boundary is deliberate — don't
wire auto-submission into either half.

---

## What's already set up here

| Piece | Status | Notes |
|-------|--------|-------|
| Python venv (`.venv`) | ✅ installed | Python 3.13 |
| `python-jobspy` | ✅ installed | keyless aggregator scraper |
| `scrape_jobs.py` | ✅ tested | discovery → `jobs.csv` |
| `daily_run.py` | ✅ tested | scrape + flag NEW roles + build `digest.html` |
| `digest.html` | ✅ generated | **your dashboard — open this in a browser** |
| `pick.py` | ✅ tested | hands one row to career-ops |
| Scheduled task `JobSearch-Discovery` | ✅ registered | runs `daily_run.py` at 08:00 & 20:00 daily |
| `jobs.csv` | ✅ 75 roles | NL/DE live run (IE/India widen `--hours-old`) |
| career-ops | ⚠️ you install | one command, below (external code — run it yourself) |

Prereqs already on this machine: Python 3.13, Node 24, Git. (`gh`/`bun` not
needed by this stack.)

---

## 1. Discovery — find postings

Activate the venv, then run the scraper:

```powershell
.\.venv\Scripts\Activate.ps1
python scrape_jobs.py                 # all regions (NL, DE, IE, India)
python scrape_jobs.py --regions NL,DE # one geography at a time
python scrape_jobs.py --limit 10 --debug   # small run while testing
python scrape_jobs.py --hours-old 168      # only postings < 7 days old (weekly re-run)
```

It pulls from Indeed + Glassdoor + LinkedIn (and **Naukri** for India), de-dupes,
keeps only real product roles, scores each for junior/associate fit, surfaces any
visa/relocation language, and writes a ranked **`jobs.csv`** (highest `fit_score`
first).

**LinkedIn will rate-limit (HTTP 429)** without a proxy — that's expected and
handled; Indeed is the most reliable source. For heavier LinkedIn use, pass a
proxy list in `scrape_jobs.py` (`proxies=` on `scrape_jobs`).

## 2. Handoff — pick one

```powershell
python pick.py          # list the top 10 ranked rows
python pick.py 0        # print row 0's title + URL to paste into career-ops
python pick.py 3 --jd   # also dump the full job description
```

## 3. Apply — career-ops (install once, then drive from Claude Code)

career-ops is a **separate** tool. Install it yourself (it downloads code, so it
wasn't auto-installed here):

```bash
npx @santifer/career-ops init
cd career-ops
claude
```

Or add it as a Claude Code plugin instead:

```text
/plugin marketplace add career-ops-hq/career-ops
/plugin install career-ops@career-ops
```

Then, per application, paste a URL from `pick.py`:

```text
/career-ops https://www.linkedin.com/jobs/view/...
```

It evaluates fit, tailors a CV + cover letter (PDF needs Playwright Chromium:
`npx playwright install chromium`), preps interview answers, and logs the
application to its tracker. **You** review and submit.

---

## 4. Daily automation — where to look

A Windows scheduled task **`JobSearch-Discovery`** runs `daily_run.py` at
**08:00 and 20:00** every day. Each run scrapes, flags postings that are **new
since the last run**, and rewrites **`digest.html`**.

**👉 Your dashboard is `digest.html`** — open it in a browser
(`C:\Claude Folder\job-search\digest.html`). New roles are tagged **NEW** and
sorted to the top with a green fit score and an **Apply ↗** link straight to the
posting. That's where you decide what to apply to.

Run it on demand, or change / disable the schedule:

```powershell
# run now without waiting for the next slot
Start-ScheduledTask -TaskName "JobSearch-Discovery"

# change the times (example: 09:00 and 21:00)
$t = New-ScheduledTaskTrigger -Daily -At 9:00am
$u = New-ScheduledTaskTrigger -Daily -At 9:00pm
Set-ScheduledTask -TaskName "JobSearch-Discovery" -Trigger $t,$u

# turn it off / back on
Disable-ScheduledTask -TaskName "JobSearch-Discovery"
Enable-ScheduledTask  -TaskName "JobSearch-Discovery"
```

Note: the task runs only while your machine is **on and you're logged in** — it
is not a cloud service. If the laptop is asleep at 08:00, it runs at the next
wake (`-StartWhenAvailable` is set).

## Caveats worth remembering

- **career-ops runs on your Claude plan** — it uses the coding agent (this
  Claude) to think, so it needs your Pro/Max/Team subscription or API credits.
  JobSpy itself is free and keyless.
- **Personal data stays local.** career-ops stores your CV/profile in
  `~/career-ops-data` by default. If you ever fork its repo, keep that fork
  **private** — profiles contain personal info.
- **Shipped portals lean US/EU.** For India, Naukri (in `scrape_jobs.py`) is the
  local board; career-ops' own scanner is Ashby/Greenhouse/Lever/Wellfound-heavy.
- **Read every draft before sending.** The fit score is a crude heuristic, and
  career-ops' own fact-check can't catch every reworded claim.
- **Review, don't automate submission.** That's the line your main project draws
  on purpose; this stack keeps a human in the loop at the apply step.
