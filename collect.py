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
    if len(games) < 16:
        print(f"collect: only {len(games)} games returned, not writing", file=sys.stderr)
        return 1

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
