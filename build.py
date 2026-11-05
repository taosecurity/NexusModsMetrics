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


TYPES_JSON = os.path.join(HERE, "data", "types.json")
CAT_DL = os.path.join(HERE, "data", "category_downloads.csv")
TOP_TYPES = 7  # categories drawn in colour; the rest fold into "Other"


def types_section():
    """Mod types (Nexus categories): Starfield's mix and trends, plus each tracked game's biggest and fastest-growing type."""
    if not os.path.exists(TYPES_JSON):
        return None
    with open(TYPES_JSON, encoding="utf-8") as f:
        tj = json.load(f)
    g = tj["games"].get(FOCUS)
    if not g:
        return None
    w = g["windows"]
    now = w["0"]
    total = sum(now.values())
    new = {k: {d: now.get(k, 0) - w[d].get(k, 0) for d in ("30", "90", "365")} for k in now}
    total_new90 = sum(v["90"] for v in new.values()) or 1

    # downloads per category: latest weekly snapshot, and the gain since the previous one
    dl_snaps = {}
    if os.path.exists(CAT_DL):
        with open(CAT_DL, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                dl_snaps.setdefault(r["date"], {})[r["category"]] = r
    snap_dates = sorted(dl_snaps)
    latest = dl_snaps[snap_dates[-1]] if snap_dates else {}
    prev_date = next((d for d in reversed(snap_dates[:-1])
                      if (datetime.date.fromisoformat(snap_dates[-1]) - datetime.date.fromisoformat(d)).days >= 6), None)
    prev = dl_snaps.get(prev_date, {})
    dl_total = sum(int(r["downloads"]) for r in latest.values()) or 1
    dl_new_total = sum(int(r["new90_downloads"]) for r in latest.values()) or 1

    rows = []
    for k in sorted(now, key=lambda c: -now[c]):
        n = now[k]
        d = latest.get(k)
        dls = int(d["downloads"]) if d else None
        rows.append({
            "name": k, "mods": n, "share": n / total * 100 if total else 0,
            "new30": new[k]["30"], "new90": new[k]["90"], "new365": new[k]["365"],
            "pct_month": (new[k]["90"] / 3.0) / (n - new[k]["90"]) * 100 if n - new[k]["90"] > 0 else None,
            "share_new90": new[k]["90"] / total_new90 * 100,
            "downloads": dls, "dl_share": dls / dl_total * 100 if d else None,
            "avg_dl": dls / n if d and n else None,
            "new90_downloads": int(d["new90_downloads"]) if d else None,
            "new90_dl_share": int(d["new90_downloads"]) / dl_new_total * 100 if d else None,
            "dl_gain": (dls - int(prev[k]["downloads"])) if d and k in prev else None,
        })
    for r in rows:
        r["trend"] = r["share_new90"] - r["share"]

    top = [r["name"] for r in rows[:TOP_TYPES]]
    monthly = tj.get("focus_monthly", [])
    # cumulative mods per top type (+ Other), month by month, then today's count
    lines = {k: [] for k in top + ["Other"]}
    points = monthly + [[tj["date"], now]]
    for date, counts in points:
        for k in top:
            lines[k].append([date, counts.get(k, 0)])
        lines["Other"].append([date, sum(v for c, v in counts.items() if c not in top)])
    # new mods per quarter by type (share of each quarter's new mods)
    qstarts = [(date, counts) for date, counts in monthly if date[5:7] in ("01", "04", "07", "10")]
    quarters = []
    for i in range(len(qstarts)):
        start, c0 = qstarts[i]
        end, c1, partial = (qstarts[i + 1][0], qstarts[i + 1][1], False) if i + 1 < len(qstarts) else (tj["date"], now, True)
        per = {k: c1.get(k, 0) - c0.get(k, 0) for k in top}
        per["Other"] = sum(v for c, v in c1.items() if c not in top) - sum(v for c, v in c0.items() if c not in top)
        quarters.append({"start": start, "partial": partial, "counts": per, "total": sum(per.values())})
    # first quarter (the launch months before the first quarter boundary)
    if monthly and qstarts and monthly[0][0] < qstarts[0][0]:
        c0, c1 = monthly[0][1], qstarts[0][1]
        per = {k: c1.get(k, 0) - c0.get(k, 0) for k in top}
        per["Other"] = sum(v for c, v in c1.items() if c not in top) - sum(v for c, v in c0.items() if c not in top)
        quarters.insert(0, {"start": monthly[0][0], "partial": False, "counts": per, "total": sum(per.values())})

    games = []
    for dom, gg in tj["games"].items():
        n0, n90 = gg["windows"]["0"], gg["windows"]["90"]
        tot = sum(n0.values()) or 1
        newc = {k: n0[k] - n90.get(k, 0) for k in n0}
        tn = sum(newc.values())
        big = max(n0, key=n0.get) if n0 else None
        fast = max(newc, key=newc.get) if newc else None
        rising = max((k for k in n0 if newc[k] >= 20), key=lambda k: newc[k] / (tn or 1) - n0[k] / tot, default=None)
        games.append({"domain": dom, "name": gg["name"], "categories": len(n0),
                      "biggest": big, "biggest_share": n0[big] / tot * 100 if big else None,
                      "fastest": fast, "fastest_new": newc.get(fast, 0), "fastest_share": newc.get(fast, 0) / (tn or 1) * 100,
                      "rising": rising, "rising_gap": (newc[rising] / (tn or 1) - n0[rising] / tot) * 100 if rising else None,
                      "new90": tn})
    return {"date": tj["date"], "total": total, "rows": rows, "top": top, "lines": lines, "quarters": quarters,
            "dl_date": snap_dates[-1] if snap_dates else None, "dl_prev": prev_date, "games": games}


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
        "types": types_section(),
    }
    order = {d: i for i, d in enumerate(ranked)}
    if page_data["types"]:
        page_data["types"]["games"].sort(key=lambda g: order.get(g["domain"], 99))
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
