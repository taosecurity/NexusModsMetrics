"""Mod types (Nexus categories): counts per category for the top games, plus Starfield's downloads per category.

Daily (cheap, about 20 requests):
  - for each tracked game: mods per category now and 30 / 90 / 365 days ago (from mod creation dates)
  - for Starfield: mods per category on the 1st of every month since its first mod
  -> data/types.json (rewritten each run; the history is rebuilt from creation dates every time)
Weekly (about 180 requests, Starfield only):
  - total downloads per category, and downloads of mods created in the last 90 days, by paging through every
    Starfield mod (80 per page). Only the per-category totals are stored, never per-mod data.
  -> one row per category appended to data/category_downloads.csv

Usage: python types.py [--force-downloads]
"""
import argparse
import calendar
import csv
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # python -I leaves the script folder off the path
import nexus  # noqa: E402
import model  # noqa: E402

TYPES_JSON = os.path.join(HERE, "data", "types.json")
CAT_DL = os.path.join(HERE, "data", "category_downloads.csv")
CAT_DL_FIELDS = ["date", "category", "mods", "downloads", "new90_mods", "new90_downloads"]
FOCUS = "starfield"
WINDOWS = (0, 30, 90, 365)
DL_EVERY_DAYS = 7
PAGE = 80  # the API returns at most 80 mods per page


def _ts(d):
    return calendar.timegm(d.timetuple())


def facets_at(domain, dates):
    """{date_or_None: {category: count}} for mods created before each date (None = all mods now)."""
    out = {}
    for i in range(0, len(dates), 12):
        chunk = dates[i:i + 12]
        parts = []
        for j, d in enumerate(chunk):
            created = f', createdAt: [{{value: "{_ts(d)}", op: LT}}]' if d else ""
            parts.append(f'f{j}: mods(filter: {{gameDomainName: [{{value: "{domain}", op: EQUALS}}]{created}}}, '
                         f'facets: {{categoryName: []}}, count: 0) {{ totalCount facetsData }}')
        data = nexus.query("{ " + " ".join(parts) + " }")
        for j, d in enumerate(chunk):
            fd = data[f"f{j}"]["facetsData"] or {}
            out[d] = {k: int(v) for k, v in (fd.get("categoryName") or {}).items()}
    return out


def month_starts(first, last):
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


def last_dl_date():
    if not os.path.exists(CAT_DL):
        return None
    with open(CAT_DL, newline="", encoding="utf-8") as f:
        dates = [r["date"] for r in csv.DictReader(f)]
    return max(dates) if dates else None


def downloads_by_category(categories, today):
    """Sum mod downloads per category for the focus game (pages through each category separately)."""
    cut = today - datetime.timedelta(days=90)
    rows = []
    for cat in categories:
        total, n, new_n, new_dl, offset = 0, 0, 0, 0, 0
        while True:
            q = ('query($d: String!, $c: String!, $o: Int!) { m: mods(filter: {gameDomainName: [{value: $d, op: EQUALS}], '
                 'categoryName: [{value: $c, op: EQUALS}]}, sort: [{downloads: {direction: DESC}}], count: 80, offset: $o) '
                 '{ totalCount nodes { downloads createdAt } } }')
            m = nexus.query(q, {"d": FOCUS, "c": cat, "o": offset})["m"]
            for node in m["nodes"]:
                dl = int(node["downloads"] or 0)
                total += dl
                n += 1
                if node["createdAt"] and datetime.date.fromisoformat(node["createdAt"][:10]) >= cut:
                    new_n += 1
                    new_dl += dl
            offset += PAGE
            if not m["nodes"] or offset >= m["totalCount"]:
                break
        rows.append({"date": today.isoformat(), "category": cat, "mods": n, "downloads": total,
                     "new90_mods": new_n, "new90_downloads": new_dl})
        print(f"  {cat:22} {n:6} mods  {total / 1e6:8.2f}M downloads")
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force-downloads", action="store_true", help="run the weekly downloads-by-category pass now")
    args = ap.parse_args()
    today = datetime.datetime.now(datetime.timezone.utc).date()

    data = model.load()
    ranked = model.current_ranking(data)[:model.TOP_N]
    if FOCUS not in ranked:
        ranked.append(FOCUS)
    out = {"date": today.isoformat(), "focus": FOCUS, "games": {}, "focus_monthly": []}
    for dom in ranked:
        dates = [None] + [today - datetime.timedelta(days=w) for w in WINDOWS[1:]]
        f = facets_at(dom, dates)
        out["games"][dom] = {"name": data["names"].get(dom, dom),
                             "windows": {str(w): f[d] for w, d in zip(WINDOWS, dates)}}
        top = sorted(f[None].items(), key=lambda kv: -kv[1])[:3]
        print(f"types: {dom:28} {len(f[None]):3} categories  top: {', '.join(f'{k} {v}' for k, v in top)}")

    # Starfield monthly history per category
    mods_hist = data["mods"].get(FOCUS, [])
    first = mods_hist[0][0] if mods_hist else datetime.date(2023, 8, 1)
    months = month_starts(first - datetime.timedelta(days=31), today)
    hist = facets_at(FOCUS, months)
    out["focus_monthly"] = [[d.isoformat(), hist[d]] for d in months]

    with open(TYPES_JSON, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, indent=0, sort_keys=True)
    print(f"types: wrote {TYPES_JSON}")

    last = last_dl_date()
    due = args.force_downloads or not last or (today - datetime.date.fromisoformat(last)).days >= DL_EVERY_DAYS
    if due and last != today.isoformat():
        cats = sorted(out["games"][FOCUS]["windows"]["0"], key=lambda c: -out["games"][FOCUS]["windows"]["0"][c])
        print(f"types: weekly downloads-by-category pass for {FOCUS} ({len(cats)} categories)")
        rows = downloads_by_category(cats, today)
        new_file = not os.path.exists(CAT_DL)
        with open(CAT_DL, "a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=CAT_DL_FIELDS, lineterminator="\n")
            if new_file:
                w.writeheader()
            w.writerows(rows)
        print(f"types: appended {len(rows)} rows to {CAT_DL}")
    else:
        print(f"types: downloads-by-category not due (last {last})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
