"""Mod types (Nexus categories): counts per category for the top games, plus Starfield's downloads per category.

Daily (cheap, about 20 requests):
  - for each tracked game: mods per category now and 30 / 90 / 365 days ago (from mod creation dates)
  - for Starfield: mods per category on the 1st of every month since its first mod
  -> data/types.json (rewritten each run; the history is rebuilt from creation dates every time)
Weekly (about 180 requests, Starfield only):
  - total downloads per category, and downloads of mods created in the last 90 days, by paging through every
    Starfield mod (80 per page). Only the per-category totals are stored, never per-mod data.
  -> one row per category appended to data/category_downloads.csv

Usage: python modtypes.py [--force-downloads]
"""
import argparse
import calendar
import csv
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # python -I leaves the script folder off the path
import nexus  # noqa: E402
import model  # noqa: E402
import collect  # noqa: E402  (for log_issue)

TYPES_JSON = os.path.join(HERE, "data", "types.json")
CAT_DL = os.path.join(HERE, "data", "category_downloads.csv")
CAT_DL_FIELDS = ["date", "category", "mods", "downloads", "new90_mods", "new90_downloads"]
FOCUS = "starfield"
WINDOWS = (0, 30, 90, 365)
DL_EVERY_DAYS = 7
PAGE = 80  # the API returns at most 80 mods per page


def _ts(d):
    return calendar.timegm(d.timetuple())


TRANSLATION = "Translation"
FRANCHISE = "Related to Movies/TV/Books/Other Games"
TAGS = (TRANSLATION, FRANCHISE)
# Star Wars by name (the API's WILDCARD name filter matches these words in the mod name)
SW_TERMS = ["star wars", "mandalorian", "jedi", "sith", "lightsaber", "stormtrooper", "clone trooper", "boba fett",
            "x-wing", "tie fighter", "millennium falcon", "darth", "kenobi", "skywalker", "grogu", "galactic empire"]
SW_RE = re.compile(r"\b(" + "|".join(re.escape(t).replace(r"\ ", r"\s+") for t in SW_TERMS) + r")\b", re.I)
# Hot-topic groups made of several tags (a mod with more than one of the tags counts once)
GROUPS = {"presets": ["Character Preset", "Saved games"],
          "ai": ["AI-Generated Content", "AI Media", "AI Assisted"]}
CRITICS_DL = os.path.join(HERE, "data", "critics_downloads.csv")
CRITICS_FIELDS = ["date", "group", "mods", "downloads", "new90_mods", "new90_downloads"]


def facets_at(domain, dates, tags_out=None):
    """{date_or_None: {category: count}} for mods created before each date (None = all mods now).
    If tags_out is a dict, it also gets {date_or_None: {tag: count}} for the TAGS of interest."""
    out = {}
    for i in range(0, len(dates), 12):
        chunk = dates[i:i + 12]
        parts = []
        for j, d in enumerate(chunk):
            created = f', createdAt: [{{value: "{_ts(d)}", op: LT}}]' if d else ""
            parts.append(f'f{j}: mods(filter: {{gameDomainName: [{{value: "{domain}", op: EQUALS}}]{created}}}, '
                         f'facets: {{categoryName: [], tag: []}}, count: 0) {{ totalCount facetsData }}')
        data = nexus.query("{ " + " ".join(parts) + " }")
        for j, d in enumerate(chunk):
            fd = data[f"f{j}"]["facetsData"] or {}
            out[d] = {k: int(v) for k, v in (fd.get("categoryName") or {}).items()}
            if tags_out is not None:
                tg = fd.get("tag") or {}
                tags_out[d] = {t: int(tg.get(t, 0)) for t in TAGS}
                tags_out[d]["_total"] = int(data[f"f{j}"]["totalCount"])
    return out


def group_counts(domain, dates, tags_out):
    """Add {group: count} to tags_out[date] for each GROUPS entry (mods with ANY of the group's tags)."""
    jobs = [(g, d) for d in dates for g in GROUPS]
    for i in range(0, len(jobs), 12):
        chunk = jobs[i:i + 12]
        parts = []
        for j, (g, d) in enumerate(chunk):
            created = f', createdAt: [{{value: "{_ts(d)}", op: LT}}]' if d else ""
            anyof = ", ".join(f'{{tag: [{{value: "{t}", op: EQUALS}}]}}' for t in GROUPS[g])
            parts.append(f'q{j}: mods(filter: {{gameDomainName: [{{value: "{domain}", op: EQUALS}}]{created}, '
                         f'filter: [{{op: OR, filter: [{anyof}]}}]}}, count: 0) {{ totalCount }}')
        data = nexus.query("{ " + " ".join(parts) + " }")
        for j, (g, d) in enumerate(chunk):
            tags_out.setdefault(d, {})[g] = int(data[f"q{j}"]["totalCount"])


def starwars(today):
    """Starfield mods with Star Wars terms in their names: total, how many are translations, new per month.
    Only counts are kept (no mod names or ids)."""
    q = ('query($t: String!, $o: Int!) { m: mods(filter: {gameDomainName: [{value: "starfield", op: EQUALS}], '
         'name: [{value: $t, op: WILDCARD}]}, count: 80, offset: $o) { totalCount nodes { modId name createdAt tags { name } } } }')
    found, per_term = {}, {}
    for term in SW_TERMS:
        off = 0
        while True:
            m = nexus.query(q, {"t": term, "o": off})["m"]
            per_term[term] = m["totalCount"]
            for x in m["nodes"]:
                if SW_RE.search(x["name"] or ""):   # keep only real name matches
                    found[x["modId"]] = (x["createdAt"] or "")[:7], {t["name"] for t in (x.get("tags") or [])}
            off += PAGE
            if off >= m["totalCount"] or not m["nodes"]:
                break
    monthly = {}
    for ym, _ in found.values():
        if ym:
            monthly[ym] = monthly.get(ym, 0) + 1
    return {"date": today.isoformat(), "count": len(found),
            "translations": sum(1 for _, tg in found.values() if TRANSLATION in tg),
            "franchise_tagged": sum(1 for _, tg in found.values() if FRANCHISE in tg),
            "per_term": per_term, "monthly_new": dict(sorted(monthly.items()))}


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


def downloads_by_category(categories, today, groups):
    """Sum mod downloads per category for the focus game (pages through each category separately).
    Also fills `groups` with downloads for translations, Star Wars by name, franchise-tagged and everything else."""
    cut = today - datetime.timedelta(days=90)
    rows = []
    for g in ("translation", "starwars", "franchise", "presets", "ai", "neither", "none", "all"):
        groups[g] = {"mods": 0, "downloads": 0, "new90_mods": 0, "new90_downloads": 0}
    for cat in categories:
        total, n, new_n, new_dl, offset = 0, 0, 0, 0, 0
        while True:
            q = ('query($d: String!, $c: String!, $o: Int!) { m: mods(filter: {gameDomainName: [{value: $d, op: EQUALS}], '
                 'categoryName: [{value: $c, op: EQUALS}]}, sort: [{downloads: {direction: DESC}}], count: 80, offset: $o) '
                 '{ totalCount nodes { downloads createdAt name tags { name } } } }')
            m = nexus.query(q, {"d": FOCUS, "c": cat, "o": offset})["m"]
            for node in m["nodes"]:
                dl = int(node["downloads"] or 0)
                total += dl
                n += 1
                is_new = bool(node["createdAt"]) and datetime.date.fromisoformat(node["createdAt"][:10]) >= cut
                if is_new:
                    new_n += 1
                    new_dl += dl
                tg = {t["name"] for t in (node.get("tags") or [])}
                member = {"all"}
                if TRANSLATION in tg:
                    member.add("translation")
                if SW_RE.search(node.get("name") or ""):
                    member.add("starwars")
                if FRANCHISE in tg:
                    member.add("franchise")
                for g, gtags in GROUPS.items():
                    if tg & set(gtags):
                        member.add(g)
                if not member & {"translation", "starwars"}:
                    member.add("neither")          # neither translation nor Star Wars
                if not member & {"translation", "starwars", "presets", "ai"}:
                    member.add("none")             # none of the four hot topics
                for g in member:
                    groups[g]["mods"] += 1
                    groups[g]["downloads"] += dl
                    if is_new:
                        groups[g]["new90_mods"] += 1
                        groups[g]["new90_downloads"] += dl
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
    old = {}
    if os.path.exists(TYPES_JSON):
        with open(TYPES_JSON, encoding="utf-8") as fh:
            old = json.load(fh)
    for dom in ranked:
        dates = [None] + [today - datetime.timedelta(days=w) for w in WINDOWS[1:]]
        tg = {}
        f = facets_at(dom, dates, tg)
        group_counts(dom, dates, tg)
        live = int((data["snapshot"].get(dom) or {}).get("mods") or 0)
        got = sum(f[None].values())
        # some games have a catch-all parent category that counts the same mods again (Witcher 3's "The Witcher 3"):
        # if one category's count equals the excess, drop it from every window
        extra = got - live
        if live and extra > live * 0.02:
            gname = data["names"].get(dom, dom).lower()
            dup = [k for k in f[None] if k.lower() in gname and abs(f[None][k] - extra) <= max(10, live * 0.002)]
            if dup:
                for d in f:
                    f[d].pop(dup[0], None)
                print(f"types: {dom}: dropped '{dup[0]}' ({f[None].get(dup[0], extra):,} mods counted twice)")
                got = sum(f[None].values())
        # sanity: categories must cover (nearly) all of the game's mods; a shortfall means missing data
        if live and got < live * 0.95:
            detail = f"{data['names'].get(dom, dom)}: categories add up to {got:,}, mod total is {live:,}"
            collect.log_issue(today.isoformat(), "kept last mod-type figures", detail)
            if dom in old.get("games", {}):
                out["games"][dom] = old["games"][dom]
            continue
        out["games"][dom] = {"name": data["names"].get(dom, dom),
                             "windows": {str(w): f[d] for w, d in zip(WINDOWS, dates)},
                             "tags": {str(w): tg[d] for w, d in zip(WINDOWS, dates)}}
        top = sorted(f[None].items(), key=lambda kv: -kv[1])[:3]
        print(f"types: {dom:28} {len(f[None]):3} categories  top: {', '.join(f'{k} {v}' for k, v in top)}")

    # Starfield monthly history per category
    mods_hist = data["mods"].get(FOCUS, [])
    first = mods_hist[0][0] if mods_hist else datetime.date(2023, 8, 1)
    months = month_starts(first - datetime.timedelta(days=31), today)
    htags = {}
    hist = facets_at(FOCUS, months, htags)
    group_counts(FOCUS, months, htags)
    out["focus_monthly"] = [[d.isoformat(), hist[d]] for d in months]
    out["focus_monthly_tags"] = [[d.isoformat(), htags[d]] for d in months]
    # Star Wars by name (about 25 requests; counts only)
    try:
        out["starwars"] = starwars(today)
        print(f"types: Star Wars by name: {out['starwars']['count']} Starfield mods "
              f"({out['starwars']['translations']} of them translations)")
    except RuntimeError as e:
        collect.log_issue(today.isoformat(), "kept last Star Wars count", str(e)[:200])
        if "starwars" in old:
            out["starwars"] = old["starwars"]

    with open(TYPES_JSON, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, indent=0, sort_keys=True)
    print(f"types: wrote {TYPES_JSON}")

    if FOCUS not in out["games"]:
        print("types: no Starfield figures this run; skipping the weekly downloads count")
        return 0
    last = last_dl_date()
    due = args.force_downloads or not last or (today - datetime.date.fromisoformat(last)).days >= DL_EVERY_DAYS
    if due and (last != today.isoformat() or args.force_downloads):
        cats = sorted(out["games"][FOCUS]["windows"]["0"], key=lambda c: -out["games"][FOCUS]["windows"]["0"][c])
        print(f"types: weekly downloads-by-category pass for {FOCUS} ({len(cats)} categories)")
        groups = {}
        rows = downloads_by_category(cats, today, groups)
        counted = sum(r["mods"] for r in rows)
        total = sum(out["games"][FOCUS]["windows"]["0"].values())
        if total and counted < total * 0.95:
            collect.log_issue(today.isoformat(), "skipped the weekly downloads-by-type count",
                              f"only {counted:,} of {total:,} Starfield mods came back")
            return 0
        crow = [{"date": today.isoformat(), "group": g, **v} for g, v in groups.items()]
        for path, fields, new_rows in ((CAT_DL, CAT_DL_FIELDS, rows), (CRITICS_DL, CRITICS_FIELDS, crow)):
            keep = []
            if os.path.exists(path):   # a forced rerun on the same day replaces that day's rows
                with open(path, newline="", encoding="utf-8") as fh:
                    keep = [r for r in csv.DictReader(fh) if r["date"] != today.isoformat()]
            with open(path, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
                w.writeheader()
                w.writerows(keep + new_rows)
        print(f"types: wrote {len(rows)} category rows and {len(crow)} translation/Star Wars rows")
        for g, v in groups.items():
            print(f"  {g:12} {v['mods']:6} mods  {v['downloads'] / 1e6:8.2f}M downloads")
    else:
        print(f"types: downloads-by-category not due (last {last})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
