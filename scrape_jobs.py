#!/usr/bin/env python3
"""Discovery scraper via JobSpy, with switchable profiles.

Two independent role profiles share the same regions and plumbing:
  * ``pm``      - associate/junior Product Manager + product/business analyst.
  * ``finance`` - Corporate Actions / Securities Operations / Reference Data /
                  Asset Servicing / Equity Research / Financial Analyst.

The two never mix: each profile is scraped on its own run into its own CSV.

This is DISCOVERY ONLY. It reads public aggregator results and writes a CSV.
It never applies.

Usage:
    python scrape_jobs.py --profile pm       --out jobs.csv
    python scrape_jobs.py --profile finance  --out jobs_finance.csv
    python scrape_jobs.py --profile finance --regions IN --limit 8 --debug
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd
from jobspy import scrape_jobs

# --- shared signals -------------------------------------------------------
# Entry/early-career (positive) vs senior (negative), judged from the TITLE.
JUNIOR_HINTS = ("associate", "junior", "apm", "entry level", "entry-level", "graduate",
                "early career", "intern", "internship", "trainee", "working student")
SENIOR_HINTS = ("senior", "lead", "principal", "head of", "director", "staff", "vp", "chief")
VISA_HINTS = ("visa", "sponsor", "relocation", "work permit", "blue card", "ind sponsorship")

# --- profiles -------------------------------------------------------------
# role_hints:   the TITLE must contain one of these (keeps out unrelated jobs).
# primary_hints: core target words that earn a small fit bonus.
PROFILES: dict[str, dict] = {
    "pm": {
        "search_terms": [
            "associate product manager", "junior product manager", "product manager",
            "product analyst", "business analyst", "product management intern",
        ],
        "role_hints": ("product manager", "product owner", "product analyst",
                       "product management", "business analyst", "apm",
                       "associate product", "product intern"),
        "primary_hints": ("product manager", "product owner", "apm"),
    },
    "finance": {
        # Built from the candidate's resume: corporate actions / securities ops /
        # equity reference data / asset servicing / equity research analyst.
        "search_terms": [
            "corporate actions analyst", "securities operations", "reference data analyst",
            "asset servicing", "equity research analyst", "financial analyst",
        ],
        "role_hints": ("corporate action", "securities", "reference data", "asset servicing",
                       "equity research", "financial analyst", "fund", "custody",
                       "settlement", "investment oper", "trade support", "analyst"),
        "primary_hints": ("corporate action", "securities", "reference data",
                          "asset servicing", "equity research", "custody", "settlement"),
    },
}

# These are set per-run from the chosen profile by set_profile().
SEARCH_TERMS: list[str] = []
ROLE_HINTS: tuple = ()
PRIMARY_HINTS: tuple = ()


def set_profile(name: str) -> None:
    global SEARCH_TERMS, ROLE_HINTS, PRIMARY_HINTS
    p = PROFILES[name]
    SEARCH_TERMS = p["search_terms"]
    ROLE_HINTS = p["role_hints"]
    PRIMARY_HINTS = p["primary_hints"]


# --- regions --------------------------------------------------------------
REGIONS: dict[str, dict] = {
    # LinkedIn dropped on purpose: from cloud IPs it 429s every description
    # fetch and dominates runtime while returning little. Indeed is the reliable,
    # rate-limit-free workhorse, so each scrape finishes in a few minutes.
    "NL": {"location": "Netherlands",  "country_indeed": "Netherlands",
           "sites": ["indeed"]},
    "DE": {"location": "Germany",      "country_indeed": "Germany",
           "sites": ["indeed"]},
    "IE": {"location": "Ireland",      "country_indeed": "Ireland",
           "sites": ["indeed"]},
    # India: Naukri takes a city, so fan out across the metros (+ a national pass).
    "IN": {"location": "India",        "country_indeed": "India",
           "sites": ["naukri", "indeed"],
           "cities": ["Bengaluru", "Mumbai", "Gurgaon", "Pune", "Hyderabad",
                      "Delhi", "India"]},
}


def is_target_role(row: pd.Series) -> bool:
    """True if the TITLE matches the active profile's role family."""
    title = str(row.get("title", "")).lower()
    return any(h in title for h in ROLE_HINTS)


def fit_score(row: pd.Series) -> int:
    """Higher = more likely an entry/associate-level fit for the active profile."""
    title = str(row.get("title", "")).lower()
    desc = str(row.get("description", "")).lower()
    score = 1  # baseline: already passed the role-family filter
    if any(h in title for h in JUNIOR_HINTS):
        score += 3
    if any(h in title for h in SENIOR_HINTS):
        score -= 4  # a senior title is not an entry/associate fit
    if any(h in title for h in PRIMARY_HINTS):
        score += 1  # core target role, nudge it up
    if any(h in desc for h in VISA_HINTS):
        score += 2  # visa/relocation mention is valuable for NL/DE/IE
    return score


def visa_note(row: pd.Series) -> str:
    text = f"{row.get('title', '')} {row.get('description', '')}".lower()
    hits = [h.strip() for h in VISA_HINTS if h in text]
    return ", ".join(sorted(set(hits))) if hits else ""


def scrape_region(code: str, limit: int, hours_old: int, debug: bool) -> pd.DataFrame:
    cfg = REGIONS[code]
    frames: list[pd.DataFrame] = []
    locations = cfg.get("cities") or [cfg["location"]]
    for loc in locations:
        for term in SEARCH_TERMS:
            try:
                df = scrape_jobs(
                    site_name=cfg["sites"],
                    search_term=term,
                    location=loc,
                    country_indeed=cfg["country_indeed"],
                    results_wanted=limit,
                    hours_old=hours_old,
                    fetch_description=True,
                )
            except Exception as exc:  # one board 429-ing shouldn't kill the run
                print(f"  ! {code}/{loc}/{term!r} failed: {exc}", file=sys.stderr)
                continue
            if df is not None and len(df):
                df["region"] = code
                df["search_term"] = term
                frames.append(df)
            if debug:
                print(f"  {code}/{loc}/{term!r}: {0 if df is None else len(df)} rows")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def main() -> int:
    ap = argparse.ArgumentParser(description="Scrape roles for a profile.")
    ap.add_argument("--profile", default="pm", choices=list(PROFILES),
                    help="which role profile to scrape (default: pm)")
    ap.add_argument("--regions", default="NL,DE,IE,IN",
                    help="comma list from NL,DE,IE,IN (default: all)")
    ap.add_argument("--limit", type=int, default=25,
                    help="results per site per search term (default: 25)")
    ap.add_argument("--hours-old", type=int, default=336,
                    help="only postings newer than this many hours (default: 336 = 14d)")
    ap.add_argument("--out", default="jobs.csv", help="output CSV path")
    ap.add_argument("--debug", action="store_true", help="verbose per-query counts")
    args = ap.parse_args()

    set_profile(args.profile)

    regions = [r.strip().upper() for r in args.regions.split(",") if r.strip()]
    bad = [r for r in regions if r not in REGIONS]
    if bad:
        ap.error(f"unknown region(s): {bad}. choose from {list(REGIONS)}")

    all_frames = []
    for code in regions:
        print(f"[{args.profile}] Scraping {code} ...")
        df = scrape_region(code, args.limit, args.hours_old, args.debug)
        if len(df):
            all_frames.append(df)

    if not all_frames:
        print("No jobs found. Try a wider --hours-old or fewer regions (LinkedIn may be rate-limiting).")
        return 1

    jobs = pd.concat(all_frames, ignore_index=True)
    jobs = jobs.drop_duplicates(subset=["job_url"]).copy()
    jobs = jobs.drop_duplicates(subset=["title", "company"]).copy()

    before = len(jobs)
    jobs = jobs[jobs.apply(is_target_role, axis=1)].copy()
    print(f"[{args.profile}] Filtered to {len(jobs)} target roles (from {before} raw postings).")
    if not len(jobs):
        print("No target roles matched. Widen --hours-old or check search terms.")
        return 1

    jobs["fit_score"] = jobs.apply(fit_score, axis=1)
    jobs["visa_note"] = jobs.apply(visa_note, axis=1)
    jobs = jobs.sort_values(["fit_score", "date_posted"], ascending=[False, False])

    cols = [c for c in ["fit_score", "region", "title", "company", "location",
                        "date_posted", "visa_note", "job_url", "site",
                        "min_amount", "max_amount", "is_remote", "description"]
            if c in jobs.columns]
    jobs[cols].to_csv(args.out, index=False)
    print(f"\n[{args.profile}] Wrote {len(jobs)} unique jobs to {args.out} "
          f"(top fit_score = {jobs['fit_score'].max()}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
