"""One-time rebuild of monthly mod counts per game, back to each game's first mod.

For the first day of each month it asks Nexus how many of the game's mods were created before that day.
Mods that have since been deleted or hidden aren't counted, so older figures run slightly low.
Writes data/modcounts.csv (date, domain, name, mods). The daily snapshot then adds today's count.

Usage: python -I backfill_mods.py [--games 20] [--only starfield,fallout4]
"""
import argparse
import calendar
import csv
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # python -I leaves the script folder off the path
import nexus  # noqa: E402

CSV_PATH = os.path.join(HERE, "data", "modcounts.csv")
FIELDS = ["date", "domain", "name", "mods"]
SKIP = {"site"}  # "Modding Tools" is not a game
PER_REQUEST = 12

OLDEST_Q = """query($d: String!) {
  mods(filter: {gameDomainName: [{value: $d, op: EQUALS}]}, sort: [{createdAt: {direction: ASC}}], count: 1) {
    nodes { createdAt }
  }
}"""


def month_starts(first, last):
    """First day of every month after `first`'s month, up to and including `last`'s month."""
    y, m = first.year, first.month
    out = []
    while True:
        m += 1
        if m > 12:
            y, m = y + 1, 1
        d = datetime.date(y, m, 1)
        if d > last:
            return out
        out.append(d)


def counts_before(domain, dates):
    parts = []
    for i, d in enumerate(dates):
        ts = calendar.timegm(d.timetuple())
        parts.append(f'c{i}: mods(filter: {{gameDomainName: [{{value: "{domain}", op: EQUALS}}], '
                     f'createdAt: [{{value: "{ts}", op: LT}}]}}, count: 0) {{ totalCount }}')
    data = nexus.query("{ " + " ".join(parts) + " }")
    return [data[f"c{i}"]["totalCount"] for i in range(len(dates))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=20, help="backfill the top N games by downloads")
    ap.add_argument("--only", default="", help="comma-separated domains to (re)do; others are kept")
    args = ap.parse_args()

    games = [g for g in nexus.top_games(args.games + len(SKIP)) if g["domainName"] not in SKIP][:args.games]
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    if only:
        games = [g for g in games if g["domainName"] in only]

    rows = []
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            redo = {g["domainName"] for g in games}
            rows = [r for r in csv.DictReader(f) if r["domain"] not in redo]

    today = datetime.datetime.now(datetime.timezone.utc).date()
    for g in games:
        dom = g["domainName"]
        nodes = nexus.query(OLDEST_Q, {"d": dom})["mods"]["nodes"]
        if not nodes:
            print(f"  {dom}: no mods, skipped")
            continue
        first = datetime.date.fromisoformat(nodes[0]["createdAt"][:10])
        dates = month_starts(first, today)
        counts = []
        for i in range(0, len(dates), PER_REQUEST):
            counts += counts_before(dom, dates[i:i + PER_REQUEST])
        rows += [{"date": d.isoformat(), "domain": dom, "name": g["name"], "mods": c} for d, c in zip(dates, counts)]
        last = counts[-1] if counts else 0
        print(f"  {dom:30} first mod {first}  {len(dates):3} months  {last:>7} mods at {dates[-1] if dates else '-'}"
              f"  (live total {g['modCount']})")

    rows.sort(key=lambda r: (r["domain"], r["date"]))
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"backfill_mods: {len(rows)} rows in {CSV_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
