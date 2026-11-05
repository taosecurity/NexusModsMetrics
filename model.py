"""Load the collected data and make the predictions.

Method (kept simple on purpose):
- Every forecast starts from the newest real count.
- Growth speed = gain per day over the last 30, 90 and 365 days (whichever the history covers).
  Likely = the 90-day speed (or the longest window available); low/high = slowest/fastest of the windows.
- "A passes B": the date the gap closes at those speeds (earliest / likely / latest).
"""
import csv
import datetime
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
SKIP = {"site"}           # "Modding Tools" is not a game
TOP_N = 15
WINDOWS = (30, 90, 365)
MIN_SPAN = 7              # need at least this many days of history for a speed
HORIZON_YEARS = 10        # beyond this, a pass date is "not in sight"
D = datetime.date


def _read(name):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load(as_of=None):
    """Return dict with series per game: downloads [(date, value)], mods [(date, value)], names, latest snapshot."""
    cut = as_of.isoformat() if as_of else "9999"
    dl, mods, names, snap = {}, {}, {}, {}
    for r in _read("downloads.csv"):
        if r["date"] > cut:
            continue
        dom = r["domain"]
        names.setdefault(dom, r["name"])
        if r["source"] == "api":
            names[dom] = r["name"]
            snap.setdefault(r["date"], {})[dom] = r
        # API rows win over sheet rows on the same date
        cur = dl.setdefault(dom, {})
        if r["source"] == "api" or r["date"] not in cur:
            cur[r["date"]] = int(r["downloads"])
        if r["mods"]:
            mods.setdefault(dom, {})[r["date"]] = int(r["mods"])
    for r in _read("modcounts.csv"):
        if r["date"] > cut:
            continue
        names.setdefault(r["domain"], r["name"])
        mods.setdefault(r["domain"], {}).setdefault(r["date"], int(r["mods"]))
    as_series = lambda m: {k: sorted((D.fromisoformat(d), v) for d, v in s.items()) for k, s in m.items()}
    latest = max(snap) if snap else None
    return {"downloads": as_series(dl), "mods": as_series(mods), "names": names,
            "latest_snapshot": latest, "snapshot": snap.get(latest, {}) if latest else {}}


def speeds(series):
    """Gain per day over each window. Returns {"30": x, ...} for windows the history covers (>= MIN_SPAN days)."""
    if len(series) < 2:
        return {}
    last_d, last_v = series[-1]
    out = {}
    for w in WINDOWS:
        target = last_d - datetime.timedelta(days=w)
        older = [p for p in series[:-1] if p[0] >= target] or []
        # the point closest to the window start (inside it), else the oldest point if the window is longer than history
        if older:
            d0, v0 = older[0]
        else:
            continue
        span = (last_d - d0).days
        if span >= max(MIN_SPAN, w * 0.5):
            out[str(w)] = (last_v - v0) / span
    if not out:
        d0, v0 = series[0]
        span = (last_d - d0).days
        if span >= MIN_SPAN:
            out[str(span)] = (last_v - v0) / span
    return out


def speed_range(series):
    """(low, likely, high) gain per day, or None if there isn't enough history."""
    s = speeds(series)
    if not s:
        return None
    likely = s.get("90") or s[max(s, key=int)]
    return (min(s.values()), likely, max(s.values()))


def pass_date(today, gap, fast_rng, slow_rng):
    """`fast` is behind by `gap` (> 0). Returns (earliest, likely, latest) dates or None per slot."""
    def one(fs, ss):
        close = fs - ss
        if close <= 0:
            return None
        days = gap / close
        if days > HORIZON_YEARS * 365:
            return None
        return today + datetime.timedelta(days=round(days))
    if not fast_rng or not slow_rng:
        return None
    return (one(fast_rng[2], slow_rng[0]), one(fast_rng[1], slow_rng[1]), one(fast_rng[0], slow_rng[2]))


def project(series, rng, days):
    last_d, last_v = series[-1]
    return last_v + rng[1] * days if rng else None


def analyse(metric_series, names, ranked, focus="starfield"):
    """Per-game stats + passes for one metric. `ranked` = domains in current rank order (biggest first)."""
    rows = []
    for i, dom in enumerate(ranked):
        s = metric_series.get(dom, [])
        if not s:
            continue
        rng = speed_range(s)
        last_d, last_v = s[-1]
        def gain(days):
            t = last_d - datetime.timedelta(days=days)
            prev = [p for p in s if p[0] <= t]
            if not prev or (t - prev[-1][0]).days > days * 0.25:
                return None
            return last_v - prev[-1][1]
        rows.append({
            "domain": dom, "name": names.get(dom, dom), "rank": i + 1, "value": last_v, "as_of": last_d.isoformat(),
            "speed": rng, "gain30": gain(30), "gain90": gain(90),
            "pct_month": (rng[1] * 30.44 / last_v * 100) if rng and last_v else None,
            "history_days": (last_d - s[0][0]).days, "points": len(s),
        })
    by = {r["domain"]: r for r in rows}
    f = by.get(focus)
    passes = []
    if f:
        today = D.fromisoformat(f["as_of"])
        for r in rows:
            if r["domain"] == focus:
                continue
            gap = r["value"] - f["value"]
            if gap > 0:   # above the focus game: when does focus pass it?
                dates = pass_date(today, gap, f["speed"], r["speed"])
                passes.append({"domain": r["domain"], "name": r["name"], "dir": "up", "gap": gap, "dates": dates,
                               "known": bool(f["speed"] and r["speed"])})
            else:         # below: could it pass the focus game?
                dates = pass_date(today, -gap, r["speed"], f["speed"])
                passes.append({"domain": r["domain"], "name": r["name"], "dir": "down", "gap": -gap, "dates": dates,
                               "known": bool(f["speed"] and r["speed"])})
    # projected rank of every game at +6/+12/+24 months (games without a speed are held flat and flagged)
    proj = {}
    for months in (6, 12, 24):
        days = round(months * 30.44)
        vals = []
        for r in rows:
            v = r["value"] + (r["speed"][1] * days if r["speed"] else 0)
            vals.append((v, r["domain"]))
        vals.sort(reverse=True)
        proj[months] = {dom: i + 1 for i, (_, dom) in enumerate(vals)}
    for r in rows:
        r["proj_rank"] = {m: proj[m][r["domain"]] for m in proj}
    return {"rows": rows, "passes": passes, "unknown": [r["name"] for r in rows if not r["speed"]]}


def current_ranking(data, metric="downloads"):
    """Domains of the current top games (Modding Tools left out), biggest first, by the newest snapshot."""
    snap = data["snapshot"]
    key = "downloads" if metric == "downloads" else "mods"
    order = sorted((dom for dom in snap if dom not in SKIP), key=lambda d: -int(snap[d][key] or 0))
    return order


def fmt_date(d):
    return d.isoformat() if d else None
