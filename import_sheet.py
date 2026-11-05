"""One-time import of the hand-typed history from "Mod growth estimates.xlsx" into data/downloads.csv.

Only typed numbers come in: every cell holding a formula (the FORECAST.LINEAR rows, the Diff/Growth
columns) is skipped. Values in the sheet are millions of downloads, stored here as whole numbers
(rounded to the sheet's 0.1M precision). Rows are tagged source=sheet.

Usage: python -I import_sheet.py "C:\\temp\\FromRB\\Mod growth estimates.xlsx"
"""
import csv
import datetime
import html
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "data", "downloads.csv")
FIELDS = ["date", "time_utc", "domain", "name", "downloads", "unique_downloads", "mods", "collections", "source"]

# Sheet labels -> Nexus domain and display name.
GAMES = {
    "witcher 3": ("witcher3", "The Witcher 3: Wild Hunt"),
    "mount": ("mountandblade2bannerlord", "Mount & Blade II: Bannerlord"),
    "starfield": ("starfield", "Starfield"),
    "morrowind": ("morrowind", "Morrowind"),
    "morrow": ("morrowind", "Morrowind"),
    "fallout 3": ("fallout3", "Fallout 3"),
    "blades": ("bladeandsorcery", "Blade & Sorcery"),
    "tools": ("site", "Modding Tools"),
}
EPOCH = datetime.date(1899, 12, 30)  # spreadsheet serial date 0


def col_num(col):
    n = 0
    for ch in col:
        n = n * 26 + ord(ch) - 64
    return n


def read_sheet(z, path, strings):
    """Return {(row, col): value} of typed (non-formula) cells, plus the set of formula cells."""
    x = z.read(path).decode("utf-8")
    cells, formulas = {}, set()
    for m in re.finditer(r'<c r="([A-Z]+)(\d+)"([^>]*?)(?:/>|>(.*?)</c>)', x, re.S):
        col, row, attrs, body = m.groups()
        key = (int(row), col_num(col))
        if body and "<f" in body:
            formulas.add(key)
            continue
        v = re.search(r"<v>(.*?)</v>", body or "")
        if not v:
            continue
        val = v.group(1)
        cells[key] = strings[int(val)] if 't="s"' in attrs else float(val)
    return cells, formulas


def date_of(serial):
    return (EPOCH + datetime.timedelta(days=int(serial))).isoformat()


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    z = zipfile.ZipFile(sys.argv[1])
    strings = [html.unescape(re.sub(r"<[^>]+>", "", s))
               for s in re.findall(r"<si>(.*?)</si>", z.read("xl/sharedStrings.xml").decode("utf-8"), re.S)]
    found = {}  # (date, domain) -> (millions, priority); lower priority number wins

    def add(date, label, value, prio):
        g = GAMES.get(str(label).strip().lower())
        if not g or not isinstance(value, float):
            return
        key = (date, g[0])
        if key not in found or prio < found[key][1]:
            found[key] = (value, prio)

    # Main tab ("Sheet3" in the workbook = sheet1.xml): dates down column A, games across row 1.
    cells, _ = read_sheet(z, "xl/worksheets/sheet1.xml", strings)
    heads = {c: v for (r, c), v in cells.items() if r == 1 and isinstance(v, str)}
    for (r, c), v in cells.items():
        if r > 1 and c in heads and isinstance(cells.get((r, 1)), float):
            add(date_of(cells[(r, 1)]), heads[c], v, 0)

    # "Sheet2" (sheet2.xml): dates across row 1, games down column A (rows 2-5 only; rows 8+ are differences).
    cells, _ = read_sheet(z, "xl/worksheets/sheet2.xml", strings)
    for (r, c), v in cells.items():
        if 2 <= r <= 5 and c > 1 and isinstance(cells.get((1, c)), float) and isinstance(cells.get((r, 1)), str):
            add(date_of(cells[(1, c)]), cells[(r, 1)], v, 1)

    # "Sheet1" (sheet3.xml): blocks with a date in column B of a header row; column B below it = that date's value.
    cells, _ = read_sheet(z, "xl/worksheets/sheet3.xml", strings)
    current = None
    for r in range(1, max(k[0] for k in cells) + 1):
        b = cells.get((r, 2))
        if cells.get((r, 1)) in (None, "Title") and isinstance(b, float) and b > 40000:
            current = date_of(b)
            continue
        if current and isinstance(cells.get((r, 1)), str) and isinstance(b, float):
            add(current, cells[(r, 1)], b, 2)

    names = {d: n for d, n in GAMES.values()}
    rows = sorted(found.items())
    # Keep any API rows already collected; replace earlier sheet rows.
    keep = []
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            keep = [r for r in csv.DictReader(f) if r["source"] != "sheet"]
    out = [{"date": d, "time_utc": "", "domain": dom, "name": names[dom],
            "downloads": int(round(v * 1e6)), "unique_downloads": "", "mods": "", "collections": "",
            "source": "sheet"} for (d, dom), (v, _) in rows]
    out.extend(keep)
    out.sort(key=lambda r: (r["date"], r["source"] != "sheet", r["domain"]))
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    per = {}
    for (d, dom), _ in rows:
        per.setdefault(dom, []).append(d)
    for dom, ds in sorted(per.items()):
        print(f"  {dom:26} {len(ds):3} points  {min(ds)} .. {max(ds)}")
    print(f"import_sheet: {len(rows)} sheet values written ({len(keep)} API rows kept)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
