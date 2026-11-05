"""Build the page: site/index.html (data embedded, no outside requests).

Usage:
  python build.py            build site/index.html (what GitHub Actions runs)
  python -I build.py --local git pull first, build, then copy to D:\\Starfield Dev\\Browser\\nexus-metrics.html
"""
import argparse
import csv
import datetime
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # python -I leaves the script folder off the path
import model  # noqa: E402

SITE = os.path.join(HERE, "site")
FORECASTS = os.path.join(HERE, "data", "forecasts.csv")
LOCAL_COPY = r"D:\Starfield Dev\Browser\nexus-metrics.html"
FOCUS = "starfield"
FC_FIELDS = ["built", "metric", "domain", "name", "dir", "earliest", "likely", "latest"]


def log_forecasts(today, dl, mods, write=True):
    """Record today's pass-date forecasts once per day (for the Forecast check section).
    Local builds (write=False) only read the log, so they never clash with the daily GitHub commit."""
    rows = []
    if os.path.exists(FORECASTS):
        with open(FORECASTS, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    if not write:
        return rows
    rows = [r for r in rows if r["built"] != today]
    for metric, res in (("downloads", dl), ("mods", mods)):
        for p in res["passes"]:
            if not p["known"] or not p["dates"]:
                continue
            e, l, la = (model.fmt_date(d) for d in p["dates"])
            if not l:
                continue
            rows.append({"built": today, "metric": metric, "domain": p["domain"], "name": p["name"], "dir": p["dir"],
                         "earliest": e or "", "likely": l, "latest": la or ""})
    rows.sort(key=lambda r: (r["built"], r["metric"], r["domain"]))
    with open(FORECASTS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FC_FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return rows


def check_table(rows):
    """First vs latest forecast for each event that has been forecast on at least two different days."""
    by = {}
    for r in rows:
        by.setdefault((r["metric"], r["domain"], r["dir"]), []).append(r)
    out = []
    for (metric, dom, d), rs in sorted(by.items()):
        rs.sort(key=lambda r: r["built"])
        if len({r["built"] for r in rs}) < 2:
            continue
        a, b = rs[0], rs[-1]
        drift = (datetime.date.fromisoformat(b["likely"]) - datetime.date.fromisoformat(a["likely"])).days
        what = "downloads" if metric == "downloads" else "mod count"
        event = (f"Starfield passes {a['name']}" if d == "up" else f"{a['name']} passes Starfield") + f" ({what})"
        out.append({"event": event, "first_on": a["built"], "first": a["likely"], "last_on": b["built"],
                    "last": b["likely"], "drift": drift})
    return out


def backtest():
    """Check the method on the hand-recorded data: as of 2026-09-26, when did it say Starfield passes Fallout 3?"""
    as_of = datetime.date(2026, 9, 26)
    data = model.load(as_of)
    dl = data["downloads"]
    if "fallout3" not in dl or FOCUS not in dl:
        return None
    ranked = sorted((d for d in ("witcher3", FOCUS, "fallout3", "mountandblade2bannerlord", "morrowind") if d in dl),
                    key=lambda d: -dl[d][-1][1])
    res = model.analyse(dl, data["names"], ranked, FOCUS)
    p = next((p for p in res["passes"] if p["domain"] == "fallout3" and p["dir"] == "up"), None)
    if not p or not p["dates"]:
        return None
    # When did it really happen? First recorded date where Starfield was ahead.
    full = model.load()["downloads"]
    fo3 = dict(full["fallout3"])
    actual = None
    prev = None
    for d, v in full[FOCUS]:
        if d in fo3 and v > fo3[d]:
            actual = (prev, d)
            break
        if d in fo3:
            prev = d
    act = (f"In fact Starfield was behind on {actual[0]} and ahead by {actual[1]}." if actual and actual[0]
           else "The actual pass date isn't in the data yet.")
    e, l, la = (model.fmt_date(d) for d in p["dates"])
    return {"as_of": as_of.isoformat(), "name": "Fallout 3", "earliest": e, "likely": l, "latest": la, "actual": act}


def jsonable(res):
    out = {"rows": [], "passes": [], "unknown": res["unknown"]}
    for r in res["rows"]:
        r = dict(r)
        r["speed"] = list(r["speed"]) if r["speed"] else None
        r["proj_rank"] = {str(k): v for k, v in r["proj_rank"].items()}
        out["rows"].append(r)
    for p in res["passes"]:
        p = dict(p)
        p["dates"] = [model.fmt_date(d) for d in p["dates"]] if p["dates"] else None
        out["passes"].append(p)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true", help="git pull first and copy the page to the local DD folder")
    args = ap.parse_args()
    if args.local:
        r = subprocess.run(["git", "-C", HERE, "pull", "--ff-only", "--quiet"], capture_output=True, text=True)
        if r.returncode != 0:
            print("build: git pull failed (building from local data):", (r.stderr or r.stdout).strip()[:300])

    data = model.load()
    if not data["latest_snapshot"]:
        print("build: no API snapshot yet; run collect.py first", file=sys.stderr)
        return 1
    ranked = model.current_ranking(data)[:model.TOP_N]
    names = data["names"]
    dl = model.analyse(data["downloads"], names, ranked, FOCUS)
    by_mods = sorted(ranked, key=lambda d: -(data["mods"].get(d, [(0, 0)])[-1][1]))
    mods = model.analyse(data["mods"], names, by_mods, FOCUS)

    # race chart: Starfield plus the two games above and two below it by downloads
    i = ranked.index(FOCUS)
    race = [FOCUS] + [d for d in (ranked[i - 1] if i >= 1 else None, ranked[i + 1] if i + 1 < len(ranked) else None,
                                  ranked[i - 2] if i >= 2 else None, ranked[i + 2] if i + 2 < len(ranked) else None) if d]

    today = data["latest_snapshot"]
    fc_rows = log_forecasts(today, dl, mods, write=not args.local)
    page_data = {
        "focus": FOCUS,
        "latest_snapshot": today,
        "built": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "games": [{"domain": d, "name": names.get(d, d),
                   "dl": [[x.isoformat(), v] for x, v in data["downloads"].get(d, [])],
                   "mods": [[x.isoformat(), v] for x, v in data["mods"].get(d, [])]} for d in ranked],
        "dl": jsonable(dl), "mods": jsonable(mods), "race": race,
        "check": check_table(fc_rows), "backtest": backtest(),
    }
    with open(os.path.join(HERE, "template.html"), encoding="utf-8") as f:
        tpl = f.read()
    blob = json.dumps(page_data, separators=(",", ":")).replace("</", "<\\/")
    html = tpl.replace("{{DATA}}", blob)
    os.makedirs(SITE, exist_ok=True)
    out = os.path.join(SITE, "index.html")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    sf = next(r for r in dl["rows"] if r["domain"] == FOCUS)
    print(f"build: {out} ({len(html) // 1024} KB), snapshot {today}, Starfield #{sf['rank']} {sf['value'] / 1e6:.1f}M")
    for p in sorted(dl["passes"], key=lambda p: p["gap"])[:4]:
        d = [model.fmt_date(x) for x in p["dates"]] if p["dates"] else None
        print(f"   {p['dir']:4} {p['name']:32} gap {p['gap'] / 1e6:6.1f}M  dates {d}")
    if args.local:
        try:
            shutil.copyfile(out, LOCAL_COPY)
            print(f"build: copied to {LOCAL_COPY}")
        except OSError as e:
            print(f"build: local copy failed: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
