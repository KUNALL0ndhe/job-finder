# Deploy the finder to the cloud (a phone link, independent of Claude + your laptop)

This puts the job finder on **GitHub Actions**: it runs twice a day on GitHub's
servers and publishes a **mobile page** at a URL you open on your phone and tap
**Apply**. It does **not** use Claude at all once deployed — the "brain" is the
Python keyword search in `scrape_jobs.py`. It keeps running if your Claude plan
is exhausted and if your laptop is off.

It still does **not** apply for you or touch your logins — you tap Apply and
submit yourself. That part is not automatable safely on any host.

## One-time setup (~10 minutes)

### 1. Create a GitHub repo
- Go to <https://github.com/new>.
- Name it e.g. `job-finder`. **Public** (free Pages) is fine — the page only
  contains public job listings, no personal data. (Private also works but uses
  Actions minutes from your free quota.)
- Create it empty (no README).

### 2. Push this folder
From `C:\Claude Folder\job-search`:

```bash
git init
git add scrape_jobs.py daily_run.py pick.py README.md .gitignore .github
git commit -m "Job finder: twice-daily discovery to a mobile page"
git branch -M main
git remote add origin https://github.com/<your-username>/job-finder.git
git push -u origin main
```

> `.gitignore` already keeps `.venv/`, `jobs.csv` and `digest.html` out of the
> commit — the cloud run regenerates those itself.

### 3. Turn on Pages + let Actions write state
- Repo **Settings -> Pages -> Build and deployment -> Source: GitHub Actions**.
- Repo **Settings -> Actions -> General -> Workflow permissions ->
  Read and write permissions** (so the run can save the "new since last time"
  state). Save.

### 4. First run
- Repo **Actions** tab -> **Job discovery** -> **Run workflow**.
- When it finishes (~5 min), your page is live at:

  **`https://<your-username>.github.io/job-finder/`**

### 5. Put it on your phone
- Open that URL on your phone -> browser menu -> **Add to Home Screen**.
- Now it's a one-tap icon. It refreshes itself at **08:00 and 20:00 IST**; you
  just open it and tap **Apply** on what's new (use the **New** filter).

## Change the times
Edit the two `cron:` lines in `.github/workflows/discovery.yml` (times are in
**UTC** — subtract 5h30m from IST), commit, push.

## Honest limitations
- **Cloud IPs get blocked more.** GitHub's servers are datacenter IPs, so
  **LinkedIn will mostly return nothing** from the cloud; **Indeed, Glassdoor
  and Naukri** are the reliable sources there. (Your *local* twice-daily task
  still runs LinkedIn better from your home IP — you can keep both.)
- **No applying.** The page links out to the real posting; you apply yourself.
- **Free quota.** Public repo = unlimited Actions minutes. Two ~5-min runs/day
  is tiny either way.

## You now have two finders (keep whichever you like)
| | Local task (`JobSearch-Discovery`) | Cloud (GitHub Actions) |
|---|---|---|
| Runs when laptop off | No | **Yes** |
| Needs Claude | No | No |
| LinkedIn results | Better (home IP) | Weak (datacenter IP) |
| Where you read it | `digest.html` on this PC | phone link (Pages URL) |
