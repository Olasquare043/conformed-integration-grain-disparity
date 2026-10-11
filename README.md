# Conformed Dimensional Integration at Extreme Grain Disparity

This repository holds the full pipeline behind the manuscript *"Conformed
Dimensional Integration at Extreme Grain Disparity: Integration Cost and
Downstream Model Effect across Two Domains"*. One command downloads every
source from its official publisher, builds a dimensional warehouse, runs every
experiment and regenerates every table, figure and number in the paper.

## What the study asks

When two domains are recorded at very different grains, what does it cost to
integrate them through conformed dimensions, and does the integration make
downstream models better? We measure both sides:

1. **Integration cost**: build time, storage, row counts, the grain ratio
   between domains, query latency for the same analytical question at each
   grain, and the results of conformance checks.
2. **Downstream model effect**: a ladder of models where each rung adds
   features that only exist because the domains were integrated through the
   conformed date and geography dimensions.

## The two domains, both in New York

| Domain | Source | Grain |
|---|---|---|
| Fine | NYC TLC Yellow Taxi trip records | one trip |
| Coarse | NYSERDA weekly regular gasoline prices for New York State and 16 metro regions (NY Open Data `nqur-w4p7`) | one region per week |

Both domains come from New York on purpose. With the same place, calendar and
holidays on both sides, any difference in results comes from the grain
disparity and not from a difference in country or market context. Daily weather
from Open-Meteo is integrated into both domains, and EIA weekly prices are used
only to cross-check the NYSERDA panel. See [DATA_SOURCES.md](DATA_SOURCES.md).

## Quick start

You need Git and either [uv](https://docs.astral.sh/uv/) with GNU make, or
Docker.

```bash
git clone https://github.com/Olasquare043/conformed-integration-grain-disparity.git
cd conformed-integration-grain-disparity
cp .env.example .env          # then put your free EIA key in .env
make smoke                    # a few minutes, tiny sample, checks the whole pipeline
make all                      # the full study
```

The same run inside the pinned Docker image:

```bash
docker compose run --rm pipeline make smoke
docker compose run --rm pipeline make all
```

To keep the data on another drive, set `CIGD_DATA_DIR` in `.env` to an
absolute path; both the local and the Docker runs use it.

Add `QUIET=1` to any target to turn off progress bars. Run `make help` to list
every stage. Each stage can also be run on its own with
`uv run python -m cigd <stage>`.

## Runtime and disk space

These figures come from the clean-room reproduction (see `docs/decisions.md`): a
fresh clone built and run with `docker compose run --rm pipeline make all` on a
Windows 11 laptop with 8 logical CPUs, 16 GB of RAM and Docker Desktop limited to
7.7 GB. `results/run_log.json` is that run's log. Your times will differ, and the
download time depends on your network.

| Stage | Minutes | Peak memory so far (GB) |
|---|---|---|
| check-sources | 0.3 | 0.3 |
| data | 0.9 | 0.3 |
| profile | 0.5 | 0.8 |
| warehouse | 2.6 | 6.4 |
| experiments | 251.0 | 6.9 |
| test | 0.7 | 6.9 |
| figures | 0.1 | 6.9 |
| paper-numbers | 0.0 | 6.9 |
| notebooks | 0.3 | 6.9 |

Peak memory is the highest the pipeline process has reached up to the end of that
stage, so it never goes down. The warehouse build needs 6.4 GB (DuckDB), and the
experiments stage 6.9 GB because it rebuilds the warehouse three times to time
it. **Give Docker at least 8 GB.** The clean-room run completed under a 7.7 GB
limit, but with little to spare. Under the same limit, an earlier version that held
all predictions in memory was killed by the out-of-memory killer.

| Run | Download | Disk | Time |
|---|---|---|---|
| `make smoke` | about 110 MB | about 0.4 GB | about 4 to 8 minutes |
| `make all` | about 7.9 GB, of which 6.4 GB is streamed and deleted | `data/` peaks at 4.0 GB (1.4 GB raw, 2.5 GB derived including the 2.1 GB warehouse) | about 5.5 hours: about 77 minutes of downloading and 4.3 hours of computing |

The 4.3 hours of computing is nearly all the experiments stage (251 minutes, mainly
240 LightGBM fits in the fine-grain task). On the same laptop run natively on
Windows, the fine-grain task alone took about 5.6 hours. The 77 minutes of
downloading was measured from scratch on the development network; the clean-room
run reused those downloads after checking their checksums.

Beyond `data/`, a first run from nothing also needs room for the Docker image, and
on Windows the system page file grows while the warehouse builds: free space fell
by 16 GB in the from-scratch run, against 3.8 GB when the downloads were already
in place. **Keep about 20 GB free on the system drive.**

The full run downloads every yellow taxi month from 2017 to 2025. Months before
2024 are reduced to daily trip counts per zone and deleted straight away, so only
one of them is on disk at a time.

## Verifying a run against the frozen snapshot

`config/study.yaml` fixes the study window, a `data_cutoff_date`, and every
random seed. `provenance/manifest.csv` records the URL, query parameters,
access time, size, SHA-256 checksum and row count of every file the authors
downloaded. When you run `make data`, each new download is checked against that
manifest and any changed source is reported in a clear warning. After a full
run, check your outputs with `make verify`. It compares every table with the
committed copy (exactly for counts and profiles, and to a relative tolerance of
1e-6 for model results), checks `docs/data_profile.md`, and fails if any
committed table, figure or notebook was not regenerated. Timings and storage
sizes depend on the machine and are skipped. In the clean-room run, 19 of the 25
comparable tables were byte-identical to the committed ones, every name, flag and
win mark matched, and the largest numeric difference was 2.5e-12 (relative).
`results/run_log.json` records the commit, configuration hash, library versions
and machine of the clean-room run.

## Repository map

```
config/study.yaml        study window, cutoff, seeds, source URLs
src/cigd/                pipeline code; cli.py is the single entry point
  ingest/                downloads and the provenance manifest
  profiling/             data profile of every source
  warehouse/             staging and the warehouse build
sql/                     warehouse SQL, one transformation per file
reference/               versioned mapping CSVs (zone to region, region coordinates)
tests/                   pytest suite (grain, integrity, leakage, reconciliation)
notebooks/               presentation only; they read results/ and never compute
docs/                    analysis plan, data dictionary, pipeline notes, data profile
provenance/manifest.csv  what was downloaded, when, and its checksum
results/                 generated tables, figures, paper numbers and run log
docker/, docker-compose.yml, Makefile, pyproject.toml, uv.lock
```

## Provenance note

This pipeline builds on the author's earlier coursework repository
(multi-grain-analytical-data-platform); all data sources, experiments and
results here are new.

## Licence and citation

Code is released under the MIT licence ([LICENSE](LICENSE)). Data stays under
each publisher's terms ([DATA_SOURCES.md](DATA_SOURCES.md)). Citation metadata
is in [CITATION.cff](CITATION.cff).
