# NexusModsMetrics

NexusModsMetrics builds "Tracking Starfield on Nexus Mods", a page that tracks and forecasts mod downloads and mod counts for the top 15 games on [Nexus Mods](https://www.nexusmods.com/), with a focus on Starfield. A GitHub Action collects fresh numbers and rebuilds the page every day.

Open the site: https://taosecurity.github.io/NexusModsMetrics/

For AI assistants: step-by-step instructions are in [AGENTS.md](AGENTS.md).

The page has five Parts:

- **Part 1 · Mod downloads:** how often players download each game's mods, with forecasts of when one game will pass another.
- **Part 2 · Mod count:** how many mods modders have published, with the same kind of forecasts.
- **Part 3 · Mod types:** what kinds of mods are published for Starfield, and which kinds are growing.
- **Part 4 · Top mods:** Starfield's most downloaded, most endorsed, trending and rising mods, top authors and top collections.
- **Part 5 · Hot topics:** tests of critics' claims about translations, Star Wars, character presets and AI content.

## Example

Open the site, click **Part 4 · Top mods** in the side menu, and then click **Concentration** under it. The section "How concentrated are downloads?" shows how much of each game's downloads go to its most popular mods. With the data of 2026-11-19, its summary box said:

    Starfield's top 10 mods take 9.2% of its downloads (#7 of 15, where #1 is the most
    concentrated; the middle game is 8.8%), and its top 100 take 26.1% (#10 of 15). That
    puts it in the middle: no single handful of mods dominates.

The two bar charts below the box compare all 15 games, with Starfield's bar in its own color. The numbers change a little every day as the Action collects new totals. For a broader view, **Part 1 · Mod downloads** showed Starfield as the 10th game on Nexus Mods by downloads on the same day, with 213.0 million downloads and 14,159 mods.

What's new: the page has no news list yet. Changes to the page and the scripts are in the [commit history](https://github.com/taosecurity/NexusModsMetrics/commits/main), next to the daily "Data: snapshot" commits.

## What the page leaves out

The page does not feature NSFW or adult content. Part 4 leaves adult-flagged mods and collections out of every list, and no other Part names individual mods.

Game-wide totals come from Nexus as they are, so they include adult-flagged mods.

The page is not affiliated with or endorsed by Nexus Mods.

## How it works

A GitHub Actions workflow (`.github/workflows/daily.yml`) runs once a day at about 15:17 UTC:

1. `collect.py` asks the Nexus Mods public GraphQL API for the top 40 games by downloads. That's one request, with no API key needed. It appends one row per game to `data/downloads.csv`. Running it twice on the same day changes nothing.
2. `modtypes.py` counts mods per category, and once a week Starfield's downloads per category.
3. `topmods.py` gathers Part 4's lists. If it fails, the page keeps the previous day's lists.
4. `build.py` makes the forecasts (`model.py`), logs them to `data/forecasts.csv`, and writes `site/index.html`. The page is a single file with the data built in and no outside requests.
5. The workflow commits the new data and publishes the page to GitHub Pages.

To run it now, open the repo's Actions tab, click **daily**, then click **Run workflow**. From a terminal, use `gh workflow run daily.yml`.

## Files

| File | What it does |
|---|---|
| `nexus.py` | Sends API requests. It identifies itself with the `Application-Name` and `Application-Version` headers that Nexus asks for. |
| `collect.py` | Writes the daily snapshot into `data/downloads.csv`. |
| `modtypes.py` | Counts mod types (Nexus categories), daily and weekly (see below). |
| `topmods.py` | Gathers Part 4's top mods, daily and weekly (see below). |
| `model.py` | Works out growth speeds, pass dates and rank projections. |
| `headlines.py` | Writes each Part's Headlines (3 to 5 plain-English sentences) from the day's data, by rules: passes, surges, and types gaining or losing ground. |
| `build.py` | Builds the page. `--top DIR` uses Part 4 data from another folder, and `--local FOLDER` makes a local preview (see below). |
| `template.html` | Holds the page layout and chart code. |
| `import_sheet.py` | Did the one-time import of the hand-recorded history (2025-04 to 2026-11) from a spreadsheet. Formula (forecast) cells are skipped. |
| `backfill_mods.py` | Did the one-time rebuild of monthly mod counts back to each game's first mod. |

`modtypes.py` makes about 20 requests a day. It counts mods per category for every tracked game, now and 30, 90 and 365 days ago, plus Starfield's monthly category history. Once a week it also counts Starfield downloads per category (about 180 requests; only category totals are kept).

`topmods.py` makes about 20 requests a day for:

- the top 10 mods overall and the top 5 per category, by downloads and by endorsements;
- the top new mods (released in the last 90 days) and the top 10 collections;
- each tracked game's top 10 and top 100 download sums.

Once a week (about 180 requests) it reads every Starfield mod's totals, for top authors, best-loved and trending. Adult-flagged mods and collections are filtered out.

Modlists are kept out of the mod lists and shown with the collections. They are mods tagged `Wabbajack Mod List`, plus a hand-kept list of untagged ones in `MODLIST_IDS`. `--out DIR` writes the results to another folder, for local previews.

## Data files

- `data/downloads.csv`: date, time, game, total downloads, unique downloads, mods, collections, and source (`api` = daily snapshot, `sheet` = hand-recorded, to 0.1 million).
- `data/modcounts.csv`: the mod count on the 1st of each month, rebuilt from mod creation dates. Mods that were later deleted or hidden aren't counted, so older figures run slightly low.
- `data/forecasts.csv`: each day's pass-date forecasts, used by the page's Forecast check section.
- `data/types.json`: mods per category for each tracked game (now, 30, 90 and 365 days ago), and Starfield's category counts on the 1st of each month. It is rewritten daily. It also holds the hot-topic tag counts per game, and Starfield's Star Wars count (counts only, no mod names).
- `data/category_downloads.csv`: weekly Starfield downloads per category, with downloads of mods created in the last 90 days.
- `data/top_mods.json`: Part 4's lists, rewritten daily (the weekly part carries over). Unlike the other files it names mods. Each entry is a public Nexus listing (mod id, name, credited author, category, release date, downloads, endorsements). Adult-flagged mods are never stored.
- `data/mod_totals.csv`: downloads and endorsements of every non-adult Starfield mod at the last two weekly counts (numbers and mod ids only), used for "Trending this week".
- `data/critics_downloads.csv`: weekly Starfield mods and downloads for the Part 5 hot topics (translations, Star Wars by name, franchise-tagged, character presets and saves, AI content, and mods that are none of them).
- `data/headlines.json`: each day's Headlines, so the page can mark the new ones.
- `data/issues.csv`: numbers the collectors refused because they looked wrong (for example a total that fell). The page shows a notice for the last 7 days.

## How the forecast works

For each game, the forecast uses the gain per day over the last 30, 90 and 365 days (whichever the history covers, at least 7 days).

- **Likely** uses the 90-day speed.
- **The range** uses the slowest and fastest windows.
- Every forecast starts from the newest real count.
- A pass date is the day the gap closes at those speeds.

The download history for most games starts on 2026-11-05, the first day of daily collection, so their speeds showed "collecting" for the first week. Witcher 3, Bannerlord, Starfield, Morrowind and Fallout 3 have earlier hand-recorded history.

## Running it yourself

You need Python 3.9 or newer (the workflow uses 3.12) and nothing else: the scripts use only the standard library.

```
python collect.py
python build.py
```

Then open `site/index.html`. `collect.py` needs the internet and appends to `data/`, and `build.py` rewrites `data/forecasts.csv`, `data/headlines.json` and `site/index.html`.

For a local preview that logs nothing to `data/`, run `python build.py --local <folder>`. It runs `git pull --ff-only` first, builds the page without logging forecasts or headlines, and copies `index.html` and `preview.png` to the folder. If you leave out the folder, it uses the `NEXUS_METRICS_LOCAL_DIR` environment variable, and if neither is set it stops with an error that names both. The GitHub workflow runs plain `python build.py`, which never copies anything.

The tests need no network and never touch `data/`. Run them from the repo folder with `python -m unittest discover -s tests`.

## Troubleshooting

Each script prints what it read and wrote, on lines that start with its name (`collect:`, `types:`, `top:` and `build:`), such as `collect: wrote 40 games for 2026-11-19 (Starfield 213.0M downloads, 14159 mods)`. Problems with the data go to `data/issues.csv` and are printed as `collect: ISSUE ...` lines. On GitHub, each run's full output is on the Actions tab: click **daily**, then the run.

Found a mistake? Open an issue: https://github.com/taosecurity/NexusModsMetrics/issues

## Credits and License

Richard Bejtlich of [Richard Presents Starfield Essentials](https://www.youtube.com/@RichardBejtlich) made this page. I am the developer, and Claude is the programmer. More Starfield tools and references are on the [Richard Presents Development Hub](https://taosecurity.github.io/).

The code is MIT licensed; see [LICENSE](LICENSE). The data comes from the Nexus Mods public API. Please respect their [API acceptable use policy](https://help.nexusmods.com/article/114-api-acceptable-use-policy).
