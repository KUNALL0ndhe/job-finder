#!/usr/bin/env python3
"""Pick a row from jobs.csv and print it ready to hand to the apply side.

The discovery scraper (scrape_jobs.py) writes a ranked jobs.csv. This prints
one chosen posting's title + URL so you can paste it into career-ops:

    python pick.py            # show the top 10 ranked rows
    python pick.py 0          # print row 0's URL to paste into /career-ops
    python pick.py 3 --jd     # also dump the full job description

Nothing here applies to anything. It just reads the CSV.
"""
import argparse
import pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("row", nargs="?", type=int, help="row index to print (omit to list)")
ap.add_argument("--csv", default="jobs.csv")
ap.add_argument("--jd", action="store_true", help="also print the full description")
args = ap.parse_args()

d = pd.read_csv(args.csv).reset_index(drop=True)

if args.row is None:
    print(d[["fit_score", "region", "title", "company", "location"]].head(10).to_string())
    print("\nRun:  python pick.py <row>   then paste the URL into  /career-ops <url>")
else:
    r = d.iloc[args.row]
    print(f"{r['title']} — {r['company']} ({r.get('location','')})")
    print(f"fit_score={r['fit_score']}  visa_note={r.get('visa_note','') or '-'}")
    print(f"\nPaste into career-ops:\n  /career-ops {r['job_url']}")
    if args.jd:
        print("\n--- job description ---\n")
        print(r.get("description", "(none captured)"))
