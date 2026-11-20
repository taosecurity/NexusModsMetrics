# AGENTS.md: NexusModsMetrics

Instructions for AI assistants working with this repository.

1. **What it is:** a set of small Python scripts that collect public totals from the Nexus Mods GraphQL API once a day and build one static page, "Tracking Starfield on Nexus Mods", published with GitHub Pages at https://taosecurity.github.io/NexusModsMetrics/.
   - The page tracks and forecasts mod downloads and mod counts for the top 15 games on Nexus Mods, with a focus on Starfield, in five Parts: Mod downloads, Mod count, Mod types, Top mods and Hot topics.
   - Use the page or the CSV and JSON files in `data/` to answer questions such as "How many Starfield mods are on Nexus Mods?" or "When will Starfield pass another game in downloads?".
   - A GitHub Actions workflow (`.github/workflows/daily.yml`, about 15:17 UTC) runs the scripts, commits `data/` as "Data: snapshot <date>" and deploys `site/`. Pull before you push, because the workflow pushes every day.
2. **Prerequisites:** Python 3.9 or later, standard library only (the workflow uses Python 3.12). `collect.py`, `modtypes.py` and `topmods.py` need internet access to `https://api.nexusmods.com/v2/graphql`. No API key is needed.
3. **Install:** none. Get a copy with `git clone https://github.com/taosecurity/NexusModsMetrics.git`.
4. **Prove it works:** from the repo folder, run the line below. It reads `data/` only, writes nothing and uses no network. It prints the newest snapshot date and the number of games, for example `2026-11-19 40 games`, and exits with code 0.
   ```
   python -c "import model; d=model.load(); print(d['latest_snapshot'], len(d['names']), 'games')"
   ```
   Each script also answers `--help` without touching the network or `data/`, for example `python build.py --help`.
5. **Common tasks:**
   - Run the daily job on GitHub: `gh workflow run daily.yml` (or the Actions tab, **daily**, **Run workflow**).
   - Run it locally, in the workflow's order. These need the network and write to `data/`, so run them only when you mean to add a day's data:
     ```
     python collect.py
     python modtypes.py
     python topmods.py
     python build.py
     ```
     Then open `site/index.html`.
   - Preview Part 4 without touching `data/`: `python topmods.py --out <folder>` (needs the network), then `python build.py --top <folder>`. Note that `build.py` still rewrites `data/forecasts.csv` and `data/headlines.json`.
   - Force the weekly passes: `python modtypes.py --force-downloads` and `python topmods.py --force-weekly` (each about 180 requests).
   - Change the page layout or text: edit `template.html`, then run `python build.py`. The build puts the data into the `{{DATA}}` placeholder.
6. **Inputs:** the Nexus Mods API, and the files in `data/` (see the README's "Data files" section). `collect.py --count N` sets how many games to record (default 40).
7. **Outputs:**
   - `collect.py` appends to `data/downloads.csv` and changes nothing when the day is already recorded.
   - `modtypes.py` writes `data/types.json`, and weekly `data/category_downloads.csv` and `data/critics_downloads.csv`.
   - `topmods.py` writes `data/top_mods.json` and `data/mod_totals.csv` (or the `--out` folder).
   - `build.py` writes `site/index.html` and `site/preview.png`, adds the day's forecasts to `data/forecasts.csv` (replacing any from the same day) and updates `data/headlines.json`.
   - Numbers that look wrong are refused and written to `data/issues.csv`, and the page shows them for 7 days.
8. **Exit codes:** `collect.py`, `modtypes.py` and `topmods.py` exit 0 when they ran, including when they skipped or kept old figures (the reason goes to `data/issues.csv` and stderr). `build.py` exits 1 when `data/downloads.csv` has no API snapshot yet. Any script exits 1 with a traceback on an unexpected error, such as the API failing after 4 tries. argparse errors exit 2.
9. **Log:** there is no log file. Each script prints what it read and wrote on lines that start with `collect:`, `types:`, `top:` or `build:`, and data problems are printed as `collect: ISSUE ...`. On GitHub, each run's output is on the Actions tab.
10. **Limits:**
    - It only reads public totals from Nexus Mods, about 20 requests a day plus about 180 a week for each weekly pass, with a 1-second gap between requests. Respect the [API acceptable use policy](https://help.nexusmods.com/article/114-api-acceptable-use-policy) and don't add bulk crawls.
    - It never stores adult-flagged mods, and only Part 4 (`data/top_mods.json`) names mods.
    - Don't run `build.py --local`: it is the maintainer's preview option and copies the page to a folder on the maintainer's PC.
    - `import_sheet.py` and `backfill_mods.py` were one-time imports. Don't run them again.
    - It is not affiliated with or endorsed by Nexus Mods.
11. **Corrections:** open an issue at https://github.com/taosecurity/NexusModsMetrics/issues.
