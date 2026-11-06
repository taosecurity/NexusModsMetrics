"""Part 4 Top mods: Starfield's most downloaded, most endorsed, rising and trending mods, plus top collections.

Adult-flagged mods and collections are never listed: every named list filters them out (the page doesn't feature
NSFW or adult content). Only public top-list entries are stored (mod id, name, author, category, release date,
downloads, endorsements), never anything about players.

Daily (about 20 requests):
  - top 10 overall by downloads and by endorsements
  - top 5 per category, both ways
  - rising: top 10 mods released in the last 90 days, both ways
  - top 10 Starfield collections, both ways
  - concentration: downloads of the top 10 and top 100 mods for each tracked game (sums only, no names)
Weekly (about 180 requests, same 7-day rule as modtypes.py):
  - pages through every Starfield mod, category by category, for top authors, best-loved and trending
  - data/mod_totals.csv keeps every non-adult mod's totals (numbers only) for the last two weekly crawls;
    "trending" = the gain between them
-> data/top_mods.json (rewritten each run; the weekly part carries over between weekly passes)

Usage: python topmods.py [--force-weekly] [--out DIR]
  --out DIR writes top_mods.json and mod_totals.csv to DIR instead of data/ (local previews: the bot owns data/)
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
import collect  # noqa: E402  (for log_issue)

DATA = os.path.join(HERE, "data")
TYPES_JSON = os.path.join(DATA, "types.json")
FOCUS = "starfield"
WEEKLY_DAYS = 7
PAGE = 80              # the API returns at most 80 mods per page
RISING_DAYS = 90
BEST_LOVED_MIN = 50000  # downloads a mod needs before its endorsement rate counts
TOTALS_FIELDS = ["date", "mod_id", "downloads", "endorsements"]

GAME = f'gameDomainName: [{{value: "{FOCUS}", op: EQUALS}}]'
# Modlists (Wabbajack lists and similar) are collections uploaded as mods: they are left out of every mod list and
# shown with the collections instead. Most carry this tag; the ids below are untagged modlists (hand-kept, add more
# as they turn up: Odyssey - A True RPG (Collection), Andromeda - A Starfield Mod List, Starborn Royalty).
MODLIST_TAG = "Wabbajack Mod List"
MODLIST_IDS = {1363, 8819, 6397}
SFW = (f'adultContent: [{{value: false, op: EQUALS}}], tag: [{{value: "{MODLIST_TAG}", op: NOT_EQUALS}}]')
SFW_ONLY = "adultContent: [{value: false, op: EQUALS}]"
MOD_FIELDS = "modId name author downloads endorsements createdAt adultContent modCategory { name }"
SORTS = {"downloads": "downloads", "endorsements": "endorsements"}


def _ts(d):
    return calendar.timegm(d.timetuple())


def mod_row(n, cat=None):
    if n.get("adultContent"):
        raise RuntimeError(f"adult-flagged mod {n.get('modId')} reached a list")   # filter failed: never publish it
    return {"id": int(n["modId"]), "name": n["name"] or "", "author": n.get("author") or "",
            "cat": cat or ((n.get("modCategory") or {}).get("name") or ""),
            "created": (n.get("createdAt") or "")[:10],
            "dl": int(n.get("downloads") or 0), "en": int(n.get("endorsements") or 0)}


def lists(alias_specs, per_request=8):
    """alias_specs: [(alias, filter_text, sort_key, count)] -> {alias: [mod rows]} (batched aliased queries).
    Asks for a few extra rows so the hand-kept untagged modlists can be dropped without shortening a list."""
    out = {}
    extra = len(MODLIST_IDS)
    for i in range(0, len(alias_specs), per_request):
        chunk = alias_specs[i:i + per_request]
        parts = [f'{a}: mods(filter: {{{flt}}}, sort: [{{{SORTS[s]}: {{direction: DESC}}}}], count: {c + extra}) '
                 f'{{ totalCount nodes {{ {MOD_FIELDS} }} }}' for a, flt, s, c in chunk]
        data = nexus.query("{ " + " ".join(parts) + " }")
        for a, _, _, c in chunk:
            out[a] = [mod_row(n) for n in data[a]["nodes"] if int(n["modId"]) not in MODLIST_IDS][:c]
    return out


def categories():
    """Starfield categories, biggest first, with their mod counts (from types.json when it has them)."""
    if os.path.exists(TYPES_JSON):
        with open(TYPES_JSON, encoding="utf-8") as fh:
            tj = json.load(fh)
        w = ((tj.get("games") or {}).get(FOCUS) or {}).get("windows", {}).get("0")
        if w:
            return sorted(w.items(), key=lambda kv: -kv[1])
    fd = nexus.query(f'{{ m: mods(filter: {{{GAME}}}, facets: {{categoryName: []}}, count: 0) {{ facetsData }} }}')
    cats = {k: int(v) for k, v in (fd["m"]["facetsData"] or {}).get("categoryName", {}).items()}
    return sorted(cats.items(), key=lambda kv: -kv[1])


def daily(today, data):
    out = {"date": today.isoformat()}
    # counts: all mods, adult-flagged mods
    c = nexus.query(f'{{ a: mods(filter: {{{GAME}}}, count: 0) {{ totalCount }} '
                    f'b: mods(filter: {{{GAME}, adultContent: [{{value: true, op: EQUALS}}]}}, count: 0) {{ totalCount }} }}')
    out["total_mods"], out["adult_mods"] = int(c["a"]["totalCount"]), int(c["b"]["totalCount"])

    # overall + rising
    since = today - datetime.timedelta(days=RISING_DAYS)
    rising = f'{GAME}, {SFW}, createdAt: [{{value: "{_ts(since)}", op: GT}}]'
    specs = [("od", f"{GAME}, {SFW}", "downloads", 10), ("oe", f"{GAME}, {SFW}", "endorsements", 10),
             ("rd", rising, "downloads", 10), ("re", rising, "endorsements", 10)]
    got = lists(specs)
    out["overall"] = {"downloads": got["od"], "endorsements": got["oe"]}
    out["rising"] = {"since": since.isoformat(), "days": RISING_DAYS, "downloads": got["rd"], "endorsements": got["re"]}

    # top 5 per category
    cats = categories()
    specs = []
    for i, (cat, _) in enumerate(cats):
        flt = f'{GAME}, {SFW}, categoryName: [{{value: {json.dumps(cat)}, op: EQUALS}}]'
        specs += [(f"d{i}", flt, "downloads", 5), (f"e{i}", flt, "endorsements", 5)]
    got = lists(specs)
    out["categories"] = [{"name": cat, "mods": n, "downloads": got[f"d{i}"], "endorsements": got[f"e{i}"]}
                         for i, (cat, n) in enumerate(cats)]

    # collections
    cf = f'gameDomain: [{{value: "{FOCUS}", op: EQUALS}}], {SFW}'
    cfields = "totalCount nodes { slug name totalDownloads endorsements overallRating overallRatingCount user { name } category { name } }"
    col = nexus.query(f'{{ d: collectionsV2(filter: {{{cf}}}, sort: [{{downloads: {{direction: DESC}}}}], count: 10) {{ {cfields} }} '
                      f'e: collectionsV2(filter: {{{cf}}}, sort: [{{endorsements: {{direction: DESC}}}}], count: 10) {{ {cfields} }} }}')
    crow = lambda n: {"slug": n["slug"], "name": n["name"] or "", "curator": (n.get("user") or {}).get("name") or "",
                      "cat": (n.get("category") or {}).get("name") or "", "dl": int(n.get("totalDownloads") or 0),
                      "en": int(n.get("endorsements") or 0),
                      "rating": float(n["overallRating"]) if n.get("overallRating") not in (None, "") else None,
                      "ratings": int(n.get("overallRatingCount") or 0)}
    out["collections"] = {"total": int(col["d"]["totalCount"]),
                          "downloads": [crow(n) for n in col["d"]["nodes"]],
                          "endorsements": [crow(n) for n in col["e"]["nodes"]]}

    # modlists uploaded as mods (tagged, plus the hand-kept untagged ones)
    gid = nexus.query(f'{{ game(domainName: "{FOCUS}") {{ id }} }}')["game"]["id"]
    parts = [f't: mods(filter: {{{GAME}, {SFW_ONLY}, tag: [{{value: "{MODLIST_TAG}", op: EQUALS}}]}}, '
             f'sort: [{{downloads: {{direction: DESC}}}}], count: 40) {{ nodes {{ {MOD_FIELDS} }} }}']
    parts += [f'i{m}: mods(filter: {{gameId: [{{value: "{gid}", op: EQUALS}}], modId: [{{value: "{m}", op: EQUALS}}], {SFW_ONLY}}}, '
              f'count: 1) {{ nodes {{ {MOD_FIELDS} }} }}' for m in sorted(MODLIST_IDS)]
    ml = nexus.query("{ " + " ".join(parts) + " }")
    seen, mlist = set(), []
    for k in ml:
        for n in ml[k]["nodes"]:
            if int(n["modId"]) not in seen:
                seen.add(int(n["modId"]))
                mlist.append(mod_row(n))
    out["modlists"] = sorted(mlist, key=lambda r: -r["dl"])[:10]
    out["modlists_count"] = len(mlist)

    # concentration: share of each game's downloads taken by its top 10 / top 100 mods (sums only, all mods)
    ranked = model.current_ranking(data)[:model.TOP_N]
    if FOCUS not in ranked:
        ranked.append(FOCUS)
    parts = []
    for i, dom in enumerate(ranked):
        g = f'gameDomainName: [{{value: "{dom}", op: EQUALS}}]'
        parts += [f'a{i}: mods(filter: {{{g}}}, sort: [{{downloads: {{direction: DESC}}}}], count: 80) {{ nodes {{ downloads }} }}',
                  f'b{i}: mods(filter: {{{g}}}, sort: [{{downloads: {{direction: DESC}}}}], count: 20, offset: 80) {{ nodes {{ downloads }} }}']
    res = {}
    for i in range(0, len(parts), 10):
        res.update(nexus.query("{ " + " ".join(parts[i:i + 10]) + " }"))
    conc = []
    for i, dom in enumerate(ranked):
        dls = [int(n["downloads"] or 0) for n in res[f"a{i}"]["nodes"] + res[f"b{i}"]["nodes"]]
        total = int((data["snapshot"].get(dom) or {}).get("downloads") or 0)
        if not total or len(dls) < 100:
            continue
        conc.append({"domain": dom, "name": data["names"].get(dom, dom), "total": total,
                     "top10": sum(dls[:10]), "top100": sum(dls[:100])})
    # Starfield's top 10 without modlists (the overall list above already leaves them out)
    for c in conc:
        if c["domain"] == FOCUS:
            c["top10_no_modlists"] = sum(m["dl"] for m in out["overall"]["downloads"])
    out["concentration"] = conc
    return out


def read_totals(path):
    """{date: {mod_id: (downloads, endorsements)}}"""
    if not os.path.exists(path):
        return {}
    out = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out.setdefault(r["date"], {})[int(r["mod_id"])] = (int(r["downloads"]), int(r["endorsements"]))
    return out


def weekly(today, cats, totals_path, expect=0):
    """Crawl every non-adult Starfield mod; return the weekly block and write mod_totals.csv."""
    q = ('query($c: String!, $o: Int!) { m: mods(filter: {' + GAME + ', ' + SFW + ', categoryName: [{value: $c, op: EQUALS}]}, '
         'sort: [{downloads: {direction: DESC}}], count: 80, offset: $o) '
         '{ totalCount nodes { modId name author downloads endorsements createdAt adultContent uploader { name memberId } } } }')
    mods, authors = {}, {}
    for cat, _ in cats:
        off = 0
        while True:
            m = nexus.query(q, {"c": cat, "o": off})["m"]
            for n in m["nodes"]:
                if int(n["modId"]) in MODLIST_IDS:   # tagged modlists are already filtered out by SFW
                    continue
                row = mod_row(n, cat)
                mods[row["id"]] = row
                up = n.get("uploader") or {}
                key = up.get("memberId") or row["author"]
                a = authors.setdefault(key, {"name": up.get("name") or row["author"], "mods": 0, "dl": 0, "en": 0})
                a["mods"] += 1
                a["dl"] += row["dl"]
                a["en"] += row["en"]
            off += PAGE
            if not m["nodes"] or off >= m["totalCount"]:
                break
        print(f"  {cat:22} done ({len(mods)} mods so far)")
    rows = list(mods.values())
    if expect and len(rows) < expect * 0.95:
        raise RuntimeError(f"only {len(rows):,} of {expect:,} non-adult Starfield mods came back")
    dl_total = sum(r["dl"] for r in rows)
    en_total = sum(r["en"] for r in rows)

    # best-loved: endorsements per 1,000 downloads among mods with enough downloads
    for r in rows:
        r["rate"] = round(r["en"] / r["dl"] * 1000, 2) if r["dl"] else 0
    big = [r for r in rows if r["dl"] >= BEST_LOVED_MIN]
    top100 = sorted(rows, key=lambda r: -r["dl"])[:100]
    best = {"min_dl": BEST_LOVED_MIN, "eligible": len(big),
            "median_rate": sorted(r["rate"] for r in big)[len(big) // 2] if big else None,
            "top": sorted(big, key=lambda r: -r["rate"])[:10],
            "low": sorted(top100, key=lambda r: r["rate"])[:5]}

    # trending: gains since the previous crawl
    old = read_totals(totals_path)
    prev_dates = sorted(d for d in old if d < today.isoformat())
    trending = None
    if prev_dates:
        prev = old[prev_dates[-1]]
        gains = []
        for r in rows:
            p_dl, p_en = prev.get(r["id"], (0, 0))
            gains.append({**r, "g_dl": r["dl"] - p_dl, "g_en": r["en"] - p_en, "new": r["id"] not in prev})
        trending = {"since": prev_dates[-1],
                    "downloads": sorted(gains, key=lambda r: -r["g_dl"])[:10],
                    "endorsements": sorted(gains, key=lambda r: -r["g_en"])[:10]}
    # keep the newest earlier crawl plus this one
    keep = {d: old[d] for d in prev_dates[-1:]}
    keep[today.isoformat()] = {r["id"]: (r["dl"], r["en"]) for r in rows}
    with open(totals_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(TOTALS_FIELDS)
        for d in sorted(keep):
            for mid in sorted(keep[d]):
                w.writerow([d, mid, *keep[d][mid]])

    au = list(authors.values())
    return {"date": today.isoformat(), "mods_counted": len(rows), "downloads_counted": dl_total,
            "endorsements_counted": en_total,
            "authors": {"count": len(au),
                        "downloads": sorted(au, key=lambda a: -a["dl"])[:10],
                        "endorsements": sorted(au, key=lambda a: -a["en"])[:10]},
            "best_loved": best, "trending": trending}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force-weekly", action="store_true", help="run the weekly crawl now")
    ap.add_argument("--out", help="folder for top_mods.json and mod_totals.csv (default: data/)")
    args = ap.parse_args()
    out_dir = args.out or DATA
    os.makedirs(out_dir, exist_ok=True)
    out_json = os.path.join(out_dir, "top_mods.json")
    totals = os.path.join(out_dir, "mod_totals.csv")
    log = (lambda *a: None) if args.out else collect.log_issue   # previews never write data/issues.csv
    today = datetime.datetime.now(datetime.timezone.utc).date()

    old = {}
    for p in (out_json, os.path.join(DATA, "top_mods.json")):
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                old = json.load(fh)
            break

    data = model.load()
    try:
        out = daily(today, data)
    except RuntimeError as e:
        log(today.isoformat(), "kept last top-mods lists", str(e)[:200])
        print(f"top: daily lists failed, keeping the last ones: {e}")
        return 0
    print(f"top: {out['total_mods']:,} Starfield mods, {out['adult_mods']:,} adult-flagged (left out)")
    print("top: #1 by downloads: {name} ({dl:,}); #1 by endorsements: {e[name]} ({e[en]:,})".format(
        **out["overall"]["downloads"][0], e=out["overall"]["endorsements"][0]))
    print(f"top: {len(out['categories'])} categories, {out['collections']['total']} collections, "
          f"{len(out['concentration'])} games for concentration")

    last = (old.get("weekly") or {}).get("date")
    due = args.force_weekly or not last or (today - datetime.date.fromisoformat(last)).days >= WEEKLY_DAYS
    if due and (last != today.isoformat() or args.force_weekly):
        cats = [(c["name"], c["mods"]) for c in out["categories"]]
        print(f"top: weekly crawl of every Starfield mod ({len(cats)} categories)")
        try:
            wk = weekly(today, cats, totals, out["total_mods"] - out["adult_mods"])
        except RuntimeError as e:
            log(today.isoformat(), "kept last weekly top-mods figures", str(e)[:200])
            print(f"top: weekly crawl failed, keeping the last figures: {e}")
            wk = old.get("weekly")
        else:
            print(f"top: weekly: {wk['mods_counted']:,} mods, {wk['downloads_counted'] / 1e6:.1f}M downloads; "
                  f"trending {'since ' + wk['trending']['since'] if wk['trending'] else 'starts next week'}")
        out["weekly"] = wk
    else:
        out["weekly"] = old.get("weekly")
        print(f"top: weekly crawl not due (last {last})")

    with open(out_json, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, indent=0, sort_keys=True)
    print(f"top: wrote {out_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
