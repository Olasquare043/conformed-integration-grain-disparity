# Pipeline

Every stage is one function in `src/cigd/cli.py`, run with
`python -m cigd [--profile full|smoke] [--quiet] <stage>`. The Makefile has one
target per stage, and `make all` runs them in order inside a single process,
then prints a summary table of stages, durations and outcomes.

| Stage | What it does | Writes |
|---|---|---|
| `check-sources` | Sends one small request to every official source, so an unreachable publisher is reported before a long run | log only |
| `data` | Downloads every source that is not already on disk, and compares each file with `provenance/manifest.csv` | `data/raw/`, `provenance/manifest.csv` |
| `profile` | Counts rows, gaps, schema changes and flagged values in every source, and cross-checks NYSERDA against EIA | `results/tables/profile_*.csv`, `docs/data_profile.md` |
| `warehouse` | Rebuilds the DuckDB warehouse from scratch, one timed SQL step per table | `data/<profile>/warehouse.duckdb`, `results/tables/warehouse_*.csv` |
| `test` | Runs the pytest suite against this profile's outputs | `results/run_log.json` |

## Where the data lives

By default everything downloaded or derived goes under `data/` in the repository:
raw files in `data/raw/`, and each profile's warehouse in `data/full/` or
`data/smoke/`. To keep the data on another drive, set `CIGD_DATA_DIR` to an
absolute path in `.env` or the environment. Docker Compose mounts that folder at
`/app/data` inside the container. Moving the data does not change the
configuration hash, because the location is not part of the study design.

## Trip history streaming

The coarse-grain trip-demand features need trip counts back to 2017, but the
study keeps raw trip records only for 2024 to 2025. The `tlc_history` downloader
handles each month from 2017-01 to 2023-12 in turn: it downloads the file, records
its checksum and row count in the manifest (`stored_locally = aggregate_only`),
counts trips per pickup zone per day with `sql/staging/zone_day_trip_counts.sql`,
saves those counts to `data/raw/yellow_taxi_zone_day/`, and deletes the raw file.
The same SQL counts the 2024 to 2025 months from their kept files during the
warehouse build, so trip demand means the same thing in every year. A month whose
counts already exist is not downloaded again, so its checksum is only checked
when its counts are rebuilt.

## The warehouse

`src/cigd/warehouse/build.py` deletes the old warehouse, loads the
Python-prepared sources (holidays, validity thresholds, the price snapshot,
weather and zone-day counts), creates a view over the raw 2024 to 2025 trip
files, and runs the files in `sql/warehouse/` in the order listed in
`WAREHOUSE_STEPS`. Each step is timed. The timings, the row counts and the
warehouse size go to `results/run_log.json` and `results/tables/` as the
integration-cost record. The views over the raw files are dropped at the end, so
the finished warehouse opens without the raw data. Tables and columns are
described in `docs/data_dictionary.md`.

## Profiles

`full` is the paper run. `smoke` uses one month of trips and a short slice of the
price panel, so a reviewer can check the whole pipeline in a few minutes. Smoke
outputs go to `data/smoke/` and `results/smoke/`, so they never overwrite the
paper outputs. Raw downloads in `data/raw/` are shared between profiles.

## The manifest

Each downloaded file has one row: source, file name, URL, query parameters (never
the API key), UTC access time, size, SHA-256 checksum, row count and checksum
policy.

- `must_match` files are frozen. If a fresh download has a different checksum,
  the run logs a `SOURCE CHANGED` warning, keeps the committed row, and the
  `data` stage summary counts it under `manifest_changed`.
- `informational` files are expected to change. The only one is the full NYSERDA
  export, which gains a row every week. The pipeline copies the weeks up to
  `data_cutoff_date` from it, byte for byte, into a frozen snapshot file, and
  the analysis reads only that snapshot.

To check your downloads against the authors' snapshot, run `make data` on a
clean clone and look for `manifest_changed` in the summary. `git diff
provenance/manifest.csv` shows any row that was added.

## Fetching NYSERDA from a refused network

data.ny.gov refuses some networks (see `DATA_SOURCES.md`). The manual workflow
`.github/workflows/fetch_nyserda.yml` runs `python -m cigd data --source
nyserda_gasoline` on a GitHub-hosted runner and returns the export and its
manifest row as an artifact that is kept for three days. Copy the export into
`data/raw/nyserda_gasoline/` and run `make data`, which verifies its checksum.

## Logging and the run log

All stages log through `src/cigd/logging.py`: rich output on the console and the
same messages, with timestamps, in `logs/run_<UTC timestamp>.log`. `QUIET=1`
turns off progress bars. `results/run_log.json` records the Git commit and
whether the tree had uncommitted changes, the configuration hash, library
versions, machine details, and each stage's start, end, duration and summary.
