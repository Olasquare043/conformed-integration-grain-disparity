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
| `test` | Runs the pytest suite against this profile's outputs | `results/run_log.json` |

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
