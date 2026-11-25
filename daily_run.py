#!/usr/bin/env python3
"""Build a mobile job dashboard for one profile (pm or finance).

Scrapes (via scrape_jobs.py), flags postings, and writes a self-contained page.
The two profiles are fully independent -- separate CSV, separate "seen" state,
separate page and separate push payload -- so their job lists never mix. A
"Switch" button in each page's header links to the other profile's page.

    python daily_run.py --profile pm                 # scrape + build index page
    python daily_run.py --profile finance            # scrape + build finance page
    python daily_run.py --profile finance --no-scrape # rebuild page from its CSV
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
PY = sys.executable
STATE = HERE / ".state"

# Everything that differs between the two portals lives here.
PROFILE_CFG: dict[str, dict] = {
    "pm": {
        "h1": "My job shortlist",
        "csv": "jobs.csv",
        "page": "digest.html",            # workflow publishes this as index.html
        "seen": "seen_pm.txt",
        "push": "push_pm.json",
        "push_word": "PM/analyst",
        "manifest": "manifest.webmanifest",
        "switch_label": "\U0001F4BC Finance",     # 💼 -> go to finance page
        "switch_href": "finance.html",
    },
    "finance": {
        "h1": "Finance shortlist",
        "csv": "jobs_finance.csv",
        "page": "finance.html",
        "seen": "seen_finance.txt",
        "push": "push_finance.json",
        "push_word": "finance/analyst",
        "manifest": "manifest.finance.webmanifest",
        "switch_label": "\U0001F9ED Product",      # 🧭 -> go back to product page
        "switch_href": "./",
    },
}


def run_scrape(profile: str, out_csv: Path, regions: str, hours_old: int) -> None:
    cmd = [str(PY), str(HERE / "scrape_jobs.py"), "--profile", profile,
           "--regions", regions, "--hours-old", str(hours_old), "--out", str(out_csv)]
    print("Scraping:", " ".join(cmd))
    subprocess.run(cmd, cwd=HERE, check=False)  # empty result shouldn't abort the page


def load_seen(path: Path) -> set[str]:
    if path.exists():
        return {ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()}
    return set()


def save_seen(path: Path, urls: set[str]) -> None:
    STATE.mkdir(exist_ok=True)
    path.write_text("\n".join(sorted(urls)), encoding="utf-8")


def render(df: pd.DataFrame, new_urls: set[str], cfg: dict) -> str:
    ist = dt.datetime.now(dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=5, minutes=30)))
    now = ist.strftime("%a %d %b %Y, %H:%M") + " IST"
    today = ist.date()
    cards = []
    for _, r in df.iterrows():
        url = str(r.get("job_url", ""))
        visa = str(r.get("visa_note", "") or "").strip()
        visa = "" if visa in ("nan", "") else visa
        title = html.escape(str(r.get("title", "")))
        company = html.escape(str(r.get("company", "")))
        loc = html.escape(str(r.get("location", "") or ""))
        region = html.escape(str(r.get("region", "")))
        score = int(r.get("fit_score", 0)) if pd.notna(r.get("fit_score")) else 0
        remote = str(r.get("is_remote", "")).lower() in ("true", "1", "1.0")
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
        is_24h = age is not None and age <= 1
        badges = [f'<span class="b fr {fresh_cls}">{fresh_txt}</span>']
        if is_24h:
            badges.append('<span class="b new">NEW</span>')
        badges.append(f'<span class="b reg">{region}</span>')
        if remote:
            badges.append('<span class="b rem">Remote</span>')
        if visa:
            badges.append(f'<span class="b visa">{html.escape(visa)}</span>')
        apply = (f'<a class="apply" href="{html.escape(url)}" target="_blank" rel="noopener">Apply &#8599;</a>'
                 if url and url != "nan" else '<span class="apply off">No link</span>')
        cards.append(f"""
      <article class="card{' isnew' if is_24h else ''}" data-new="{'1' if is_24h else '0'}" data-fresh="{'1' if is_fresh else '0'}" data-url="{html.escape(url)}">
        <div class="fit">{score}</div>
        <div class="body">
          <div class="title">{title}</div>
          <div class="co">{company} &middot; <span class="loc">{loc}</span></div>
          <div class="badges">{''.join(badges)}</div>
        </div>
        <div class="actions">
          {apply}
          <button class="mark" onclick="markDone(this)">Done</button>
        </div>
      </article>""")

    h1 = html.escape(cfg["h1"])
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0f1115">
<link rel="manifest" href="{cfg['manifest']}">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Jobs">
<title>{h1}</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ font: 16px/1.5 -apple-system, system-ui, sans-serif; margin: 0;
         background: #0f1115; color: #e8eaed; -webkit-text-size-adjust: 100%; }}
  header {{ position: sticky; top: 0; background: #0f1115ee; backdrop-filter: blur(8px);
           padding: 16px 16px 12px; border-bottom: 1px solid #242a33; z-index: 5; }}
  h1 {{ margin: 0; font-size: 19px; }}
  .hbtns {{ display: flex; gap: 8px; margin-top: 10px; }}
  .switch, .refresh, .alerts {{ flex: 1; text-align: center; text-decoration: none;
    background: #1f2a3a; color: #cfe0ff; border: 1px solid #2d6cdf; border-radius: 9px;
    padding: 9px 10px; font-weight: 700; font-size: 13px; cursor: pointer; white-space: nowrap; }}
  .switch {{ background: #2a2340; color: #d8c8ff; border-color: #6a4ec2; }}
  .alerts {{ background: #1f2a1f; color: #bff0c4; border-color: #2a7a38; }}
  .alerts.on {{ background: #1f7a33; color: #fff; }}
  @media (hover: hover) {{ .refresh:hover {{ background: #26344a; }} .alerts:hover {{ background: #24381f; }} .switch:hover {{ background: #332a4d; }} }}
  #subbox {{ display: none; margin-top: 12px; padding: 12px; border: 1px solid #2a7a38;
    border-radius: 10px; background: #111a12; }}
  .subhint {{ font-size: 13px; color: #cfe0cf; margin-bottom: 8px; }}
  #subjson {{ width: 100%; height: 72px; font: 11px monospace; background: #0b0f0b; color: #9fe0a8;
    border: 1px solid #27452f; border-radius: 8px; padding: 8px; resize: vertical; }}
  .subcopy {{ margin-top: 8px; background: #1f7a33; color: #fff; border: 0; border-radius: 8px;
    padding: 9px 16px; font-weight: 700; cursor: pointer; }}
  .meta {{ color: #9aa0ab; font-size: 13px; margin-top: 10px; }}
  .meta .note {{ color: #70757f; font-size: 11px; }}
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
  .b.fr.hot {{ background: #1f7a33; color: #d7ffd9; }}
  .b.fr.warm {{ background: #3f5a1f; color: #e4ffb0; }}
  .b.fr.cool {{ background: #2a3340; color: #9fb4d8; }}
  .b.fr.old {{ background: #33281f; color: #d8b89a; }}
  .b.fr.unk {{ background: #22262e; color: #7a808b; }}
  @media (hover: hover) {{ .apply:hover {{ background: #3f7cf0; }} }}
</style></head><body>
<header>
  <h1>{h1}</h1>
  <div class="hbtns">
    <a class="switch" href="{cfg['switch_href']}">{cfg['switch_label']}</a>
    <button class="alerts" id="alertsBtn" onclick="enableAlerts()">&#128276; Alerts</button>
    <button class="refresh" onclick="location.href=location.pathname+'?r='+Date.now()">&#8635; Refresh</button>
  </div>
  <div id="subbox">
    <div class="subhint">&#9989; Alerts enabled on this device. <b>Copy the text below and send it once</b> so pushes can reach you:</div>
    <textarea id="subjson" readonly onclick="this.select()"></textarea>
    <button class="subcopy" onclick="navigator.clipboard.writeText(document.getElementById('subjson').value)">Copy</button>
  </div>
  <div class="meta">{len(df)} roles<br>&#127760; Jobs last pulled from the web: <b>{now}</b><br><span class="note">Refresh just reloads this page &mdash; new jobs appear only when the scraper runs.</span></div>
  <div class="filters">
    <button data-m="new" onclick="flt('new')">New &le;24h (<span id="c-new">0</span>)</button>
    <button data-m="fresh" class="on" onclick="flt('fresh')">Fresh &le;3d (<span id="c-fresh">0</span>)</button>
  </div>
</header>
<main id="list">{''.join(cards)}</main>
<script>
  var KEY = 'doneJobs_{cfg['page']}', mode = 'fresh';
  var doneSet = (function () {{ try {{ return new Set(JSON.parse(localStorage.getItem(KEY) || '[]')); }} catch (e) {{ return new Set(); }} }})();
  function persistDone() {{ try {{ localStorage.setItem(KEY, JSON.stringify([].slice.call(doneSet))); }} catch (e) {{}} }}
  function markDone(btn) {{
    var card = btn.closest('.card');
    var title = (card.querySelector('.title') || {{}}).textContent || 'this job';
    if (!confirm('Remove from your list?\\n\\n' + title.trim())) return;
    doneSet.add(card.dataset.url); persistDone(); refresh();
  }}
  function refresh() {{
    var cards = [].slice.call(document.querySelectorAll('.card'));
    var nNew = 0, nFresh = 0;
    cards.forEach(function (c) {{
      if (doneSet.has(c.dataset.url)) {{ c.style.display = 'none'; return; }}
      var isNew = c.dataset.new === '1', isFresh = c.dataset.fresh === '1';
      if (isNew) nNew++;
      if (isFresh) nFresh++;
      c.style.display = (mode === 'new' ? isNew : isFresh) ? '' : 'none';
    }});
    setCount('new', nNew); setCount('fresh', nFresh);
  }}
  function setCount(m, n) {{ var el = document.getElementById('c-' + m); if (el) el.textContent = n; }}
  function flt(m) {{
    mode = m;
    [].slice.call(document.querySelectorAll('.filters button')).forEach(function (b) {{ b.classList.toggle('on', b.dataset.m === m); }});
    refresh();
  }}
  var VAPID_PUBLIC = 'BAprSCdgAdperHrxO7tPheyDW-GVDotxn4pQ_ApyJtfgxRrUkAbzzufUO0Ko04cmZyJRrIk3HBcPHTsizLUlPvI';
  function urlB64ToUint8(s) {{
    var pad = '='.repeat((4 - s.length % 4) % 4);
    var b = (s + pad).replace(/-/g, '+').replace(/_/g, '/');
    var raw = atob(b), arr = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
    return arr;
  }}
  function markOn() {{ var b = document.getElementById('alertsBtn'); if (b) {{ b.classList.add('on'); b.textContent = 'Alerts on'; }} }}
  function showSub(json) {{
    var box = document.getElementById('subbox'); box.style.display = 'block';
    var ta = document.getElementById('subjson'); ta.value = json; ta.focus(); ta.select();
    try {{ navigator.clipboard.writeText(json); }} catch (e) {{}}
    markOn();
  }}
  async function enableAlerts() {{
    try {{
      if (!('serviceWorker' in navigator) || !('PushManager' in window)) {{
        alert('Push needs the installed app. Add this page to your Home screen in Chrome, open that icon, then tap Alerts.'); return;
      }}
      var perm = await Notification.requestPermission();
      if (perm !== 'granted') {{ alert('Notifications are blocked. Tap the lock icon in the address bar, allow Notifications, then try again.'); return; }}
      var reg = await navigator.serviceWorker.ready;
      var sub = await reg.pushManager.getSubscription();
      if (!sub) sub = await reg.pushManager.subscribe({{ userVisibleOnly: true, applicationServerKey: urlB64ToUint8(VAPID_PUBLIC) }});
      showSub(JSON.stringify(sub));
    }} catch (e) {{ alert('Could not enable alerts: ' + (e && e.message ? e.message : e)); }}
  }}
  (function () {{
    if ('serviceWorker' in navigator && 'PushManager' in window && window.Notification && Notification.permission === 'granted') {{
      navigator.serviceWorker.ready.then(function (reg) {{ return reg.pushManager.getSubscription(); }})
        .then(function (sub) {{ if (sub) markOn(); }}).catch(function () {{}});
    }}
  }})();
  window.addEventListener('load', refresh);
  if ('serviceWorker' in navigator) {{
    window.addEventListener('load', function () {{ navigator.serviceWorker.register('sw.js').catch(function () {{}}); }});
  }}
</script>
</body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="pm", choices=list(PROFILE_CFG))
    ap.add_argument("--regions", default="NL,DE,IE,IN")
    ap.add_argument("--hours-old", type=int, default=336)
    ap.add_argument("--no-scrape", action="store_true", help="rebuild page from existing CSV")
    args = ap.parse_args()

    cfg = PROFILE_CFG[args.profile]
    csv_path = HERE / cfg["csv"]
    seen_path = STATE / cfg["seen"]
    page_path = HERE / cfg["page"]

    if not args.no_scrape:
        run_scrape(args.profile, csv_path, args.regions, args.hours_old)

    if not csv_path.exists():
        print(f"No {cfg['csv']} yet; run a scrape first.")
        return 1

    df = pd.read_csv(csv_path)
    df["job_url"] = df["job_url"].astype(str)
    df = df.sort_values("fit_score", ascending=False)

    seen = load_seen(seen_path)
    current = set(df["job_url"])
    new_urls = current - seen
    save_seen(seen_path, seen | current)

    page_path.write_text(render(df, new_urls, cfg), encoding="utf-8")

    # Push payload (workflow sends only when count > 0, to this profile's subscription).
    new_df = df[df["job_url"].isin(new_urls)]
    top = new_df.iloc[0] if len(new_df) else None
    n = len(new_urls)
    push = {
        "count": n,
        "title": f"{n} new {cfg['push_word']} job" + ("" if n == 1 else "s"),
        "body": (f"Top: {top['title']} — {top['company']}" if top is not None else ""),
    }
    (HERE / cfg["push"]).write_text(json.dumps(push), encoding="utf-8")

    print(f"[{args.profile}] Page: {page_path}  |  {n} new, {len(df)} total.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
