#!/usr/bin/env python3
"""Discovery scraper for associate/junior PM roles via JobSpy.

Targets the geographies from CLAUDE.md: Netherlands, Germany, Ireland
(visa sponsorship wanted) and India (B2B retail commerce). Pulls from the
job aggregators JobSpy supports, de-dupes, applies a light junior/associate
fit score, and writes a ranked ``jobs.csv``.

This is DISCOVERY ONLY. It reads public aggregator results and writes a CSV.
It never applies. Hand a chosen row to the apply side (career-ops) yourself.

Usage:
    python scrape_jobs.py                      # all regions, default limits
    python scrape_jobs.py --regions NL,DE      # one or more geographies
    python scrape_jobs.py --limit 10 --debug   # small run while testing
    python scrape_jobs.py --hours-old 168      # only postings < 7 days old
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd
from jobspy import scrape_jobs

# --- search ---------------------------------------------------------------
# Terms are broad on purpose; the fit score below re-ranks for junior/associate.
SEARCH_TERMS = [
    "associate product manager",
    "junior product manager",
    "product manager",
    "product analyst",
    "business analyst",
    "product management intern",
]

# Signals that a posting is actually junior/associate (positive) vs senior (negative).
JUNIOR_HINTS = ("associate", "junior", "apm", "entry level", "entry-level", "graduate",
                "early career", "intern", "internship", "trainee", "working student")
SENIOR_HINTS = ("senior", "lead", "principal", "head of", "director", "staff", "vp", "chief")
# A row must look like one of the role families we want (keeps out unrelated jobs).
# Product management is primary; business/product analyst roles share much of the JD.
PRODUCT_HINTS = ("product manager", "product owner", "product analyst", "product management",
                 "business analyst", "apm", "associate product", "product intern")
VISA_HINTS = ("visa", "sponsor", "relocation", "work permit", "blue card", "ind sponsorship")

# --- regions --------------------------------------------------------------
# Per region: which sites, the location string, and (for Indeed/Glassdoor)
# the country. Indeed is the most reliable; LinkedIn is global but rate-limits.
REGIONS: dict[str, dict] = {
    "NL": {"location": "Netherlands",  "country_indeed": "Netherlands",
           "sites": ["indeed", "linkedin", "glassdoor"]},
    "DE": {"location": "Germany",      "country_indeed": "Germany",
           "sites": ["indeed", "linkedin", "glassdoor"]},
    "IE": {"location": "Ireland",      "country_indeed": "Ireland",
           "sites": ["indeed", "linkedin", "glassdoor"]},
    # India: Naukri is the local board; LinkedIn adds remote/global postings.
    "IN": {"location": "India",        "country_indeed": "India",
           "sites": ["naukri", "linkedin", "indeed"]},
}


def is_product_role(row: pd.Series) -> bool:
    """True if the TITLE looks like a product role (not just any junior job)."""
    title = str(row.get("title", "")).lower()
    return any(h in title for h in PRODUCT_HINTS)


def fit_score(row: pd.Series) -> int:
    """Cheap heuristic rank: higher = more likely a junior/associate PM fit.

    Seniority is judged from the TITLE (reliable); the job description is only
    read for visa/relocation language, which matters for NL/DE/IE.
    """
    title = str(row.get("title", "")).lower()
    desc = str(row.get("description", "")).lower()
    score = 1  # baseline: it already passed the role-family filter
    if any(h in title for h in JUNIOR_HINTS):
        score += 3
    if any(h in title for h in SENIOR_HINTS):
        score -= 4  # a senior title is not a junior fit, whatever the JD says
    if any(h in title for h in ("product manager", "product owner", "apm")):
        score += 1  # PM is the primary target; nudge it above analyst/BA
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
    for term in SEARCH_TERMS:
        try:
            df = scrape_jobs(
                site_name=cfg["sites"],
                search_term=term,
                location=cfg["location"],
                country_indeed=cfg["country_indeed"],
                results_wanted=limit,
                hours_old=hours_old,
                fetch_description=True,   # needed so the fit score can read the JD
            )
        except Exception as exc:  # one board 429-ing shouldn't kill the run
            print(f"  ! {code}/{term!r} failed: {exc}", file=sys.stderr)
            continue
        if df is not None and len(df):
            df["region"] = code
            df["search_term"] = term
            frames.append(df)
        if debug:
            print(f"  {code}/{term!r}: {0 if df is None else len(df)} rows")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def main() -> int:
    ap = argparse.ArgumentParser(description="Scrape associate/junior PM roles.")
    ap.add_argument("--regions", default="NL,DE,IE,IN",
                    help="comma list from NL,DE,IE,IN (default: all)")
    ap.add_argument("--limit", type=int, default=25,
                    help="results per site per search term (default: 25)")
    ap.add_argument("--hours-old", type=int, default=336,
                    help="only postings newer than this many hours (default: 336 = 14d)")
    ap.add_argument("--out", default="jobs.csv", help="output CSV path")
    ap.add_argument("--debug", action="store_true", help="verbose per-query counts")
    args = ap.parse_args()

    regions = [r.strip().upper() for r in args.regions.split(",") if r.strip()]
    bad = [r for r in regions if r not in REGIONS]
    if bad:
        ap.error(f"unknown region(s): {bad}. choose from {list(REGIONS)}")

    all_frames = []
    for code in regions:
        print(f"Scraping {code} ...")
        df = scrape_region(code, args.limit, args.hours_old, args.debug)
        if len(df):
            all_frames.append(df)

    if not all_frames:
        print("No jobs found. Try a wider --hours-old or fewer regions (LinkedIn may be rate-limiting).")
        return 1

    jobs = pd.concat(all_frames, ignore_index=True)

    # De-dupe on the job URL, then on (title, company) as a fallback.
    jobs = jobs.drop_duplicates(subset=["job_url"]).copy()
    jobs = jobs.drop_duplicates(subset=["title", "company"]).copy()

    # Keep only actual product roles (drops "Junior Software Developer" etc.).
    before = len(jobs)
    jobs = jobs[jobs.apply(is_product_role, axis=1)].copy()
    print(f"Filtered to {len(jobs)} product roles (from {before} raw postings).")
    if not len(jobs):
        print("No product roles matched. Widen --hours-old or check search terms.")
        return 1

    jobs["fit_score"] = jobs.apply(fit_score, axis=1)
    jobs["visa_note"] = jobs.apply(visa_note, axis=1)
    jobs = jobs.sort_values(["fit_score", "date_posted"], ascending=[False, False])

    cols = [c for c in ["fit_score", "region", "title", "company", "location",
                        "date_posted", "visa_note", "job_url", "site",
                        "min_amount", "max_amount", "is_remote", "description"]
            if c in jobs.columns]
    jobs[cols].to_csv(args.out, index=False)
    print(f"\nWrote {len(jobs)} unique jobs to {args.out} "
          f"(top fit_score = {jobs['fit_score'].max()}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
