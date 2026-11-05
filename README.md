# Nexus Mods Growth

This tracks how fast downloads and mod counts grow for the 15 most-downloaded games on
[Nexus Mods](https://www.nexusmods.com/), and forecasts when Starfield passes the games around it.

- **Page:** https://taosecurity.github.io/NexusModsMetrics/ (rebuilt every day)
- **Data:** `data/` (CSV files you can open on GitHub or in a spreadsheet)

Not affiliated with or endorsed by Nexus Mods.

## How it works

A GitHub Actions workflow (`.github/workflows/daily.yml`) runs once a day at about 20:17 UTC:

1. `collect.py` asks the Nexus Mods public GraphQL API for the top 40 games by downloads. That's one
   request, with no API key needed. It appends one row per game to `data/downloads.csv`. Running it
   twice on the same day changes nothing.
2. `build.py` makes the forecasts (`model.py`), logs them to `data/forecasts.csv`, and writes
   `site/index.html`. The page is a single file with the data built in and no outside requests.
3. The workflow commits the new data and publishes the page to GitHub Pages.

To run it now: open the repo's Actions tab, click **daily**, then **Run workflow**. From a terminal,
use `gh workflow run daily.yml`.

## Files

| File | What it does |
|---|---|
| `nexus.py` | Sends API requests. Identifies itself with the `Application-Name` and `Application-Version` headers that Nexus asks for. |
| `collect.py` | Daily snapshot into `data/downloads.csv`. |
| `model.py` | Growth speeds, pass dates and rank projections. |
| `build.py` | Builds the page. `--local` also runs `git pull` first and copies the page to a local folder. |
| `template.html` | The page layout and chart code. |
| `import_sheet.py` | One-time import of the hand-recorded history (2025-04 to 2026-11) from a spreadsheet. Formula (forecast) cells are skipped. |
| `backfill_mods.py` | One-time rebuild of monthly mod counts back to each game's first mod. |

## Data files

- `data/downloads.csv`: date, time, game, total downloads, unique downloads, mods, collections, and
  source (`api` = daily snapshot, `sheet` = hand-recorded, to 0.1 million).
- `data/modcounts.csv`: mod count on the 1st of each month, rebuilt from mod creation dates. Mods that
  were later deleted or hidden aren't counted, so older figures run slightly low.
- `data/forecasts.csv`: each day's pass-date forecasts, used by the page's Forecast check section.

## How the forecast works

For each game: the gain per day over the last 30, 90 and 365 days (whichever the history covers, at
least 7 days).
- **Likely** uses the 90-day speed.
- **The range** uses the slowest and fastest windows.
- Every forecast starts from the newest real count.
- A pass date is the day the gap closes at those speeds.

The download history for most games starts on 2026-11-05, the first day of daily collection, so their
speeds show "collecting" for the first week. Witcher 3, Bannerlord, Starfield, Morrowind and Fallout 3
have earlier hand-recorded history.

## Running it yourself

Python 3.9 or newer, standard library only.

```
python collect.py
python build.py
```

Then open `site/index.html`.

## License

MIT. The data comes from the Nexus Mods public API. Please respect their
[API acceptable use policy](https://help.nexusmods.com/article/114-api-acceptable-use-policy).
