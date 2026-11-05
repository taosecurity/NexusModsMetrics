"""Daily snapshot: append today's totals for the top games to data/downloads.csv.

Run once a day (GitHub Actions does this). Running it again on the same UTC day changes nothing.
Usage: python collect.py [--count 40]
"""
import argparse
import csv
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # python -I leaves the script folder off the path
import nexus  # noqa: E402
CSV_PATH = os.path.join(HERE, "data", "downloads.csv")
FIELDS = ["date", "time_utc", "domain", "name", "downloads", "unique_downloads", "mods", "collections", "source"]


def existing_dates(path):
    if not os.path.exists(path):
        return set()
    with open(path, newline="", encoding="utf-8") as f:
        return {r["date"] for r in csv.DictReader(f) if r["source"] == "api"}


ISSUES = os.path.join(HERE, "data", "issues.csv")
ISSUE_FIELDS = ["date", "what", "detail"]
# Sanity limits per day since the last snapshot. Totals only grow slowly: Starfield adds about 0.13% a day.
MAX_DROP = 0.01        # a total falling more than 1% is a glitch (small dips can follow mass deletions)
MAX_RISE_PER_DAY = 0.03  # rising more than 3% a day is a glitch or a counting change
FOCUS = "starfield"


def last_snapshot(path):
    """{domain: row} for the newest API date already recorded, and that date."""
    if not os.path.exists(path):
        return None, {}
    with open(path, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["source"] == "api"]
    if not rows:
        return None, {}
    last = max(r["date"] for r in rows)
    return last, {r["domain"]: r for r in rows if r["date"] == last}


def log_issue(today, what, detail):
    new_file = not os.path.exists(ISSUES)
    with open(ISSUES, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=ISSUE_FIELDS, lineterminator="\n")
        if new_file:
            w.writeheader()
        w.writerow({"date": today, "what": what, "detail": detail})
    print(f"collect: ISSUE {what}: {detail}", file=sys.stderr)


def check(games, prev_date, prev, today):
    """Return (games to keep, problems). Drops games whose numbers look broken; problems are (what, detail)."""
    problems, keep = [], []
    days = max(1, (datetime.date.fromisoformat(today) - datetime.date.fromisoformat(prev_date)).days) if prev_date else 1
    for g in games:
        p = prev.get(g["domainName"])
        bad = []
        if p:
            for key, field in (("downloads", "downloadCount"), ("mods", "modCount")):
                old, new = int(p[key] or 0), int(g[field] or 0)
                if old <= 0:
                    continue
                change = (new - old) / old
                if change < -MAX_DROP:
                    bad.append(f"{key} fell {-change * 100:.1f}% ({old:,} to {new:,})")
                elif change / days > MAX_RISE_PER_DAY:
                    bad.append(f"{key} rose {change * 100:.1f}% in {days} day(s) ({old:,} to {new:,})")
        if bad:
            problems.append((f"skipped {g['name']}", "; ".join(bad)))
        else:
            keep.append(g)
    return keep, problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=40, help="how many games to record (top N by downloads)")
    args = ap.parse_args()

    now = datetime.datetime.now(datetime.timezone.utc)
    today = now.strftime("%Y-%m-%d")
    if today in existing_dates(CSV_PATH):
        print(f"collect: {today} already recorded, nothing to do")
        return 0

    games = nexus.top_games(args.count)
    if len(games) < 16 or not any(g["domainName"] == FOCUS for g in games):
        log_issue(today, "skipped the whole snapshot", f"the API returned {len(games)} games"
                  + ("" if any(g["domainName"] == FOCUS for g in games) else ", without Starfield"))
        return 0
    prev_date, prev = last_snapshot(CSV_PATH)
    games, problems = check(games, prev_date, prev, today)
    if any(g["domainName"] == FOCUS for g in games) is False or len(problems) >= 3:
        for what, detail in problems:
            log_issue(today, what, detail)
        log_issue(today, "skipped the whole snapshot", "Starfield's numbers or too many games looked wrong")
        return 0
    for what, detail in problems:
        log_issue(today, what, detail)

    new_file = not os.path.exists(CSV_PATH)
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        if new_file:
            w.writeheader()
        for g in games:
            w.writerow({
                "date": today,
                "time_utc": now.strftime("%H:%M"),
                "domain": g["domainName"],
                "name": g["name"],
                "downloads": int(g["downloadCount"]),
                "unique_downloads": int(g["uniqueDownloadCount"]),
                "mods": g["modCount"],
                "collections": g["collectionCount"],
                "source": "api",
            })
    sf = next((g for g in games if g["domainName"] == "starfield"), None)
    msg = f"collect: wrote {len(games)} games for {today}"
    if sf:
        msg += f" (Starfield {int(sf['downloadCount']) / 1e6:.1f}M downloads, {sf['modCount']} mods)"
    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
