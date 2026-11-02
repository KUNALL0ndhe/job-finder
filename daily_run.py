#!/usr/bin/env python3
"""Twice-daily job discovery: scrape, flag NEW postings, write a digest.

Run by Windows Task Scheduler morning and night. It:
  1. runs scrape_jobs.py for the configured regions -> jobs.csv
  2. diffs against postings seen on previous runs (.state/seen_urls.txt)
  3. writes digest.html -- a ranked dashboard with NEW roles first and
     one-click Apply links to the real posting.

DISCOVERY ONLY. It never applies, never logs in, handles no credentials.
You open digest.html, decide what's worth it, and apply yourself (with
career-ops drafting the CV / cover letter / answers for you).

    python daily_run.py                 # scrape all regions, then build digest
    python daily_run.py --no-scrape     # just rebuild the digest from jobs.csv
    python daily_run.py --regions NL,DE  # limit regions
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import subprocess
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
# Use the interpreter running this file: the local venv python when the Windows
# task invokes it, or the plain runner python in GitHub Actions. Portable either way.
PY = sys.executable
JOBS_CSV = HERE / "jobs.csv"
STATE = HERE / ".state"
SEEN = STATE / "seen_urls.txt"
DIGEST = HERE / "digest.html"


def run_scrape(regions: str, hours_old: int) -> None:
    cmd = [str(PY), str(HERE / "scrape_jobs.py"),
           "--regions", regions, "--hours-old", str(hours_old),
           "--out", str(JOBS_CSV)]
    print("Scraping:", " ".join(cmd))
    # Don't abort the digest if one run comes back empty (rate limits happen).
    subprocess.run(cmd, cwd=HERE, check=False)


def load_seen() -> set[str]:
    if SEEN.exists():
        return {ln.strip() for ln in SEEN.read_text(encoding="utf-8").splitlines() if ln.strip()}
    return set()


def save_seen(urls: set[str]) -> None:
    STATE.mkdir(exist_ok=True)
    SEEN.write_text("\n".join(sorted(urls)), encoding="utf-8")


def render(df: pd.DataFrame, new_urls: set[str]) -> str:
    now = dt.datetime.now().strftime("%a %d %b %Y, %H:%M")
    today = dt.date.today()
    n_new = len(new_urls & set(df["job_url"].astype(str)))
    cards = []
    for _, r in df.iterrows():
        url = str(r.get("job_url", ""))
        is_new = url in new_urls
        visa = str(r.get("visa_note", "") or "").strip()
        visa = "" if visa in ("nan", "") else visa
        title = html.escape(str(r.get("title", "")))
        company = html.escape(str(r.get("company", "")))
        loc = html.escape(str(r.get("location", "") or ""))
        region = html.escape(str(r.get("region", "")))
        score = int(r.get("fit_score", 0)) if pd.notna(r.get("fit_score")) else 0
        remote = str(r.get("is_remote", "")).lower() in ("true", "1", "1.0")
        # Freshness from date_posted (not every board reports it). is_fresh = <=3 days.
        age = None
        dp = r.get("date_posted")
        if pd.notna(dp):
            try:
                age = (today - pd.to_datetime(dp).date()).days
            except Exception:
                age = None
        if age is None:
            fresh_cls, fresh_txt, is_fresh = "unk", "date n/a", False
        elif age <= 0:
            fresh_cls, fresh_txt, is_fresh = "hot", "Today", True
        elif age == 1:
            fresh_cls, fresh_txt, is_fresh = "hot", "1d ago", True
        elif age <= 3:
            fresh_cls, fresh_txt, is_fresh = "warm", f"{age}d ago", True
        elif age <= 7:
            fresh_cls, fresh_txt, is_fresh = "cool", f"{age}d ago", False
        else:
            fresh_cls, fresh_txt, is_fresh = "old", f"{age}d ago", False
        badges = [f'<span class="b fr {fresh_cls}">{fresh_txt}</span>']
        if is_new:
            badges.append('<span class="b new">NEW</span>')
        badges.append(f'<span class="b reg">{region}</span>')
        if remote:
            badges.append('<span class="b rem">Remote</span>')
        if visa:
            badges.append(f'<span class="b visa">{html.escape(visa)}</span>')
        apply = (f'<a class="apply" href="{html.escape(url)}" target="_blank" rel="noopener">Apply &#8599;</a>'
                 if url and url != "nan" else '<span class="apply off">No link</span>')
        cards.append(f"""
      <article class="card{' isnew' if is_new else ''}" data-new="{'1' if is_new else '0'}" data-fresh="{'1' if is_fresh else '0'}" data-url="{html.escape(url)}">
        <div class="fit">{score}</div>
        <div class="body">
          <div class="title">{title}</div>
          <div class="co">{company} &middot; <span class="loc">{loc}</span></div>
          <div class="badges">{''.join(badges)}</div>
        </div>
        <div class="actions">
          {apply}
          <button class="mark" onclick="toggleApplied(this)">Mark applied</button>
        </div>
      </article>""")

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0f1115">
<link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Jobs">
<title>My job shortlist</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ font: 16px/1.5 -apple-system, system-ui, sans-serif; margin: 0;
         background: #0f1115; color: #e8eaed; -webkit-text-size-adjust: 100%; }}
  header {{ position: sticky; top: 0; background: #0f1115ee; backdrop-filter: blur(8px);
           padding: 16px 16px 12px; border-bottom: 1px solid #242a33; z-index: 5; }}
  h1 {{ margin: 0 0 2px; font-size: 19px; }}
  .meta {{ color: #9aa0ab; font-size: 13px; }}
  .filters {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }}
  .filters button {{ flex: 1 1 calc(50% - 4px); padding: 9px; font-size: 13px; border-radius: 8px;
    border: 1px solid #2a3340; background: #171b22; color: #cfd4dc; font-weight: 600; }}
  .filters button.on {{ background: #2d6cdf; border-color: #2d6cdf; color: #fff; }}
  main {{ padding: 12px 16px calc(32px + env(safe-area-inset-bottom)); max-width: 640px; margin: 0 auto; }}
  .card {{ display: flex; align-items: center; gap: 12px; padding: 14px;
    border: 1px solid #222832; border-radius: 14px; margin-bottom: 10px; background: #141820; }}
  .card.isnew {{ border-color: #2a5a35; background: #121a14; }}
  .fit {{ flex: 0 0 auto; width: 40px; height: 40px; border-radius: 10px; background: #0e2a16;
    color: #7ee081; font-weight: 800; font-size: 18px; display: flex; align-items: center; justify-content: center; }}
  .body {{ flex: 1 1 auto; min-width: 0; }}
  .title {{ font-weight: 700; font-size: 15px; line-height: 1.3; }}
  .co {{ color: #9aa0ab; font-size: 13px; margin-top: 2px; }}
  .loc {{ color: #9aa0ab; }}
  .badges {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 7px; }}
  .b {{ font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 20px; }}
  .b.new {{ background: #1f7a33; color: #d7ffd9; }}
  .b.reg {{ background: #263040; color: #bcd0ff; }}
  .b.rem {{ background: #3a2b50; color: #e2caff; }}
  .b.visa {{ background: #4a3a1f; color: #ffe6b0; }}
  .actions {{ flex: 0 0 auto; display: flex; flex-direction: column; gap: 6px; align-items: stretch; }}
  .apply {{ background: #2d6cdf; color: #fff; text-decoration: none; text-align: center;
    padding: 11px 14px; border-radius: 10px; font-weight: 700; font-size: 14px; white-space: nowrap; }}
  .apply.off {{ background: #2a2f38; color: #8a909b; }}
  .mark {{ background: #16221a; color: #8fe0a0; border: 1px solid #27452f; border-radius: 10px;
    padding: 8px; font-size: 12px; font-weight: 700; white-space: nowrap; cursor: pointer; }}
  .card.isapplied {{ opacity: .55; }}
  .card.isapplied .mark {{ background: #2a1b1b; color: #f0a0a0; border-color: #4a2a2a; }}
  .b.fr.hot {{ background: #1f7a33; color: #d7ffd9; }}
  .b.fr.warm {{ background: #3f5a1f; color: #e4ffb0; }}
  .b.fr.cool {{ background: #2a3340; color: #9fb4d8; }}
  .b.fr.old {{ background: #33281f; color: #d8b89a; }}
  .b.fr.unk {{ background: #22262e; color: #7a808b; }}
  @media (hover: hover) {{ .apply:hover {{ background: #3f7cf0; }} }}
</style></head><body>
<header>
  <h1>My job shortlist</h1>
  <div class="meta">{len(df)} roles &middot; <b>{n_new} new</b> &middot; {now}<br>you review &amp; apply &mdash; nothing is submitted for you</div>
  <div class="filters">
    <button data-m="all" class="on" onclick="flt('all')">All (<span id="c-all">{len(df)}</span>)</button>
    <button data-m="new" onclick="flt('new')">New (<span id="c-new">{n_new}</span>)</button>
    <button data-m="fresh" onclick="flt('fresh')">Fresh &le;3d (<span id="c-fresh">0</span>)</button>
    <button data-m="applied" onclick="flt('applied')">Applied (<span id="c-applied">0</span>)</button>
  </div>
</header>
<main id="list">{''.join(cards)}</main>
<script>
  var KEY = 'appliedJobs', mode = 'all';
  function getApplied() {{ try {{ return new Set(JSON.parse(localStorage.getItem(KEY) || '[]')); }} catch (e) {{ return new Set(); }} }}
  function saveApplied(s) {{ try {{ localStorage.setItem(KEY, JSON.stringify([].slice.call(s))); }} catch (e) {{}} }}
  function toggleApplied(btn) {{
    var card = btn.closest('.card'), s = getApplied(), u = card.dataset.url;
    if (s.has(u)) s.delete(u); else s.add(u);
    saveApplied(s); refresh();
  }}
  function refresh() {{
    var s = getApplied(), cards = [].slice.call(document.querySelectorAll('.card'));
    cards.forEach(function (c) {{
      var applied = s.has(c.dataset.url);
      c.classList.toggle('isapplied', applied);
      var mk = c.querySelector('.mark'); if (mk) mk.textContent = applied ? 'Undo' : 'Mark applied';
      var show;
      if (mode === 'applied') show = applied;
      else if (mode === 'new') show = !applied && c.dataset.new === '1';
      else if (mode === 'fresh') show = !applied && c.dataset.fresh === '1';
      else show = !applied;
      c.style.display = show ? '' : 'none';
    }});
    var live = cards.filter(function (c) {{ return !s.has(c.dataset.url); }});
    setCount('all', live.length);
    setCount('new', live.filter(function (c) {{ return c.dataset.new === '1'; }}).length);
    setCount('fresh', live.filter(function (c) {{ return c.dataset.fresh === '1'; }}).length);
    setCount('applied', cards.length - live.length);
  }}
  function setCount(m, n) {{ var el = document.getElementById('c-' + m); if (el) el.textContent = n; }}
  function flt(m) {{
    mode = m;
    [].slice.call(document.querySelectorAll('.filters button')).forEach(function (b) {{ b.classList.toggle('on', b.dataset.m === m); }});
    refresh();
  }}
  window.addEventListener('load', refresh);
  if ('serviceWorker' in navigator) {{
    window.addEventListener('load', function () {{ navigator.serviceWorker.register('sw.js').catch(function () {{}}); }});
  }}
</script>
</body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regions", default="NL,DE,IE,IN")
    ap.add_argument("--hours-old", type=int, default=336)
    ap.add_argument("--no-scrape", action="store_true", help="rebuild digest from existing jobs.csv")
    args = ap.parse_args()

    if not args.no_scrape:
        run_scrape(args.regions, args.hours_old)

    if not JOBS_CSV.exists():
        print("No jobs.csv yet; run a scrape first.")
        return 1

    df = pd.read_csv(JOBS_CSV)
    df["job_url"] = df["job_url"].astype(str)
    df = df.sort_values("fit_score", ascending=False)

    seen = load_seen()
    current = set(df["job_url"])
    new_urls = current - seen
    save_seen(seen | current)

    DIGEST.write_text(render(df, new_urls), encoding="utf-8")
    print(f"Digest written: {DIGEST}")
    print(f"{len(new_urls)} new roles since last run, {len(df)} total.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
