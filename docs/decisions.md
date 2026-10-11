# Decision log

Design decisions made after the study began, with the date, the reason and what
changed. Decisions about models, splits and tests are pre-registered in
`docs/analysis_plan.md`, which keeps its own change log.

## 2026-10-09: NY Open Data is fetched on a GitHub-hosted runner

data.ny.gov refused every request from the network the pipeline was developed on
(HTTP 403 from the Socrata front end), while the other sources answered. The
manual workflow `.github/workflows/fetch_nyserda.yml` runs the same download code
from the official URL on a GitHub-hosted runner. The manifest row records that
download. No file is rehosted.

## 2026-10-09: every pipeline file is written with LF line endings

On Windows, Python and pandas write CRLF by default, which gave the EIA and weather
files checksums that a Linux or Docker run could never match. All writes now use
LF. The affected files were downloaded again and their manifest rows replaced.
Their content was unchanged; only the line endings differed.

## 2026-10-09: EIA cross-check

**Original level check, unchanged.** The tolerance fixed before profiling
(median absolute difference at most 0.10 USD per gallon, correlation at least
0.98, NYSERDA state average against EIA New York State on the same Monday) stays
exactly as it was. It is enforced on the full profile, where it passes (0.085,
0.997). On the smoke profile it is computed and written to the outputs but does
not fail the build. Reason: the threshold was calibrated for the full window, and
the 15-month smoke window is too short to estimate the level bias. NYSERDA runs 6
to 11 cents above EIA, and the size of that gap changes from year to year.

**New weekly change check, enforced in both profiles.** Agreement of weekly
changes, pairing NYSERDA week w with EIA week w - 1, with the mean level bias
bounded separately: change correlation at least 0.75, absolute mean level bias at
most 0.15 USD per gallon. These thresholds were chosen **after** the Phase 2
profile had been seen (full window: change correlation 0.869, level bias 0.088),
so they are not blind. They are set below the observed values to allow for
shorter windows, not tuned to pass a particular window. Both the original and the
new results appear in `results/tables/profile_eia_crosscheck.csv`,
`results/tables/profile_eia_change_check.csv` and `docs/data_profile.md`.

## 2026-10-09: NYSERDA week convention

A NYSERDA date (a Monday, w) describes the week before it: the seven days from
Monday w - 7 to Sunday w - 1. Evidence from the Phase 2 profile: weekly changes in
the NYSERDA state average correlate 0.87 with EIA's Monday survey one week
earlier, against 0.78 on the same Monday. `dim_date` carries both the calendar
week (Monday start) and the NYSERDA label that describes it, and
`fact_fuel_price_weekly` is keyed by the week the prices describe. The leakage
tests and the publication-lag assumption in the analysis plan follow this
convention.

## 2026-10-09: geography rule for zones outside the 16 metro regions

Taxi zones in the five boroughs roll up to the New York City metro region. Zone
1 (Newark Airport, borough "EWR") is in New Jersey: it maps to New Jersey, outside
the 16 New York metro regions but inside PADD 1B and the United States. Zones 264
and 265 (boroughs "Unknown" and "N/A") map to an explicit Unknown member at every
level. The rule is written in `reference/borough_to_region.csv`.

## 2026-10-09: trip-demand history from 2017

The coarse-grain trip-demand features need trip counts from the start of the
price panel. Each yellow taxi month from 2017-01 to 2023-12 is downloaded, its
checksum and row count are recorded in the manifest (`stored_locally =
aggregate_only`), it is aggregated, and the raw file is deleted. `fact_trip`
stays at 2024 to 2025.

The kept aggregate is at zone-day grain rather than zone-week. A Monday-start
week often spans two monthly files, so a zone-week total cannot be completed
inside one file. The zone-week and region-week totals are then built in the
warehouse through `dim_date` and `dim_geography`. The same SQL
(`sql/staging/zone_day_trip_counts.sql`) counts trips for 2024 to 2025 from the
kept raw files, so trip demand means the same thing in every year: every
published trip, before any validity rule.

## 2026-10-09: fine-grain target and validity rules

The fine-grain target is log trip duration. Trips from VendorID 7 are excluded
(every one of them has a dropoff at or before its pickup), as are trips that fail
the validity rules in `sql/warehouse/stg_trip_validity.sql`, with thresholds in
`config/study.yaml` under `quality.trip_validity`. Rows removed per rule are
written to `results/tables/warehouse_trip_validity.csv`. A robustness run on 2024
only (before the 2025 data-quality changes) is pre-registered in the analysis
plan.

## 2026-10-09: missing price week

The week labelled 2024-12-30 is absent from the NYSERDA export. It is not imputed
for evaluation: forecasts whose target week is missing are skipped, and the
number skipped is reported.

## 2026-10-09: publication lags measured from archived evidence

TLC's "typically with a two-month delay" was checked against Internet Archive
copies of the TLC page and the files' `Last-Modified` headers for 35 months
(`docs/evidence/tlc_release_dates.csv`). A rule of "usable from month m + 3" would
have used December 2025 and June 2026 before they were released, so the primary
information set uses "usable from the first day of month m + 4". Weather uses a
7-day lag (documented as 5 days, observed as 7 on 2026-10-09). NYSERDA release
timing was bounded from archived exports and metadata
(`docs/evidence/nyserda_release_dates.csv`): recent labels appeared about one
and a half to three weeks after their date, so lagging the other sources from
the label date is conservative.

## 2026-10-09: analysis plan edits requested in review, before approval

The author approved `docs/analysis_plan.md` subject to these edits, made before
it was committed and before any model ran:

- The main fine-grain models do not use the recorded `trip_distance`, which is
  known only after the trip and largely determines duration. They use
  booking-time features instead: pickup zone, dropoff zone, and the
  centroid-to-centroid distance between the zones from the official TLC taxi
  zone shapefile (added to the manifest). The recorded distance is kept for one
  sensitivity run, labelled as such.
- The coarse task models the one-week change in price, not the level, so trees
  are not limited to the training range; the random walk is a zero-change
  forecast. A ridge regression learner is added on the same features, with its
  penalty chosen by a rule stated in the plan on the year before the evaluation
  period, then frozen. Both learners are reported.
- The fine task gets a naive baseline below F0: the training median duration for
  the zone pair and hour of the week, falling back to the zone pair, then the
  overall median.
- Effect sizes are reported with 95 percent confidence intervals from a block
  bootstrap (whole weeks for the coarse task, whole days for the fine task),
  next to the Diebold-Mariano tests.
- More evidence on the NYSERDA release lag was gathered (see the entry above).
- The coarse target is defined as the next published NYSERDA weekly value.

Everything else in the draft was approved as written, including the model
settings, sample sizes, COVID window and query-latency design.

## 2026-10-11: clean-room reproduction

The study was rebuilt from a fresh clone of the repository, in the pinned Docker
image, to check that `make all` regenerates the committed results. The clone sits
in a sibling folder and the working folder was not used.

**Run 1 (2026-10-10, head `2ad1534`) failed, and its verify result is void.** It
downloaded every source from scratch: all 129 files matched the manifest, including
the 84 streamed months and a fresh NYSERDA download fetched by the `fetch-nyserda`
workflow, because data.ny.gov refuses this machine. The profile and warehouse
outputs matched. Then the container was killed by the out-of-memory killer (exit
137; the Docker VM log shows the Python process at 7.0 GB resident memory against a
7.7 GB container limit) at the end of the fine-grain experiment, after 5.6 hours. The cause
was the code, not the machine: the experiment held all 21 million predictions in
memory at once, which only fitted on the 16 GB laptop it was first run on. The
`verify` check reported "26 of 26 match" for that run, but it was vacuous: the
fine-grain, figure, paper-number and notebook stages never ran, the clone still
held the committed copies of their outputs, and `verify` only compared files that
existed. That result was withdrawn.

**Fixes** (commits `3be1446` and `0cad375`):

- The fine-grain experiment processes one run and information set at a time and
  appends its predictions to Parquet. Every smoke table was byte-identical before
  and after the change, so no number moved.
- `make verify` now also fails when a committed table, figure or notebook is
  missing from the rebuild, and it compares `docs/data_profile.md` exactly. The
  committed profile had been written before the configuration last changed and
  carried a stale hash; it was refreshed from the clean run.
- Each stage's peak memory is recorded in `results/run_log.json`, and the README
  states that Docker needs at least 8 GB.

**Run 2 (2026-10-11, same clone updated to `0cad375`) passed.** `make all` exited 0
after 256 minutes and 87 tests passed (2 skipped by design: the determinism rerun
runs on the smoke profile). `make verify` reported 27 of 27 outputs matching, none
differing and none missing. Of 25 comparable tables, 19 were byte-identical to the
committed ones (including the fine-grain accuracy table, so LightGBM gave identical
results on Windows and in Linux), every name, flag and win mark matched, and the
largest numeric difference was 2.5e-12 relative (coarse ridge and comparison
tables).

**Deviation: run 2 reused the downloaded raw files from run 1.** The 1.5 GB of
2024 to 2025 trip files, the 84 zone-day aggregates and the small files were not
downloaded again. Their checksums were verified from scratch in run 1 (all 129
matched the manifest) and checked again against the manifest in run 2. Everything
derived was deleted first and rebuilt: the warehouse, the feature and prediction
files, every results table, figure and notebook, the paper numbers and
`docs/data_profile.md`. The reason was disk space and time.

**How run 2 got there.** A first attempt was paused by the low-disk rule when free
space fell to 2.4 GB (most likely the Windows page file growing while the warehouse built). It was
stopped and restarted instead of resumed, because a frozen container's clock keeps
running and the pause would have been recorded as build time in the run log. A
second attempt died within a minute when the Docker VM crashed during an
interruption of the session (`unexpected EOF`). The third attempt completed, and the run log
contains only that attempt.

**Measured requirements** (also in the README): peak memory 6.4 GB for the
warehouse stage and 6.9 GB for the experiments stage, in a container limited to
7.7 GB; `data/` peaking at 4.0 GB; free system-drive space falling by 16 GB in the
from-scratch run 1 and by 3.8 GB in run 2; about 5.5 hours in total from scratch
(77 minutes of downloading, 256 minutes for run 2's stages).

`results/run_log.json` is the run log of run 2 and is the canonical record of the
reproduced results. It marks the working tree dirty (`dirty_tree: true`) because
the committed outputs had been deleted and were regenerated during the run.

## 2026-10-11: the journal font was added to the Docker image after the clean-room run

The clean-room reproduction (entry above) ran with the image built from the
Dockerfile at commit `0cad375`. Commit `e0993b5` then added the Debian package
`fonts-texgyre` to the Dockerfile, so the journal and concept figures can be drawn in
TeX Gyre Heros. This affects figure rendering only: no table, number or model output
depends on fonts. The committed `fig_*` figures were drawn inside the rebuilt image;
the working figures from before were not redrawn. `make verify` does not compare figure
pixels, but it requires the seven journal and concept figures to exist and every PNG to
be 300 dpi. Because the image is no longer the one used in the clean-room run, **a
fresh clean-room run will be done before the release tag**, from a new clone and in the
current image.

## 2026-10-11: only a full run writes results/run_log.json

`make verify` was found to rewrite `results/run_log.json` with the header of the
machine it ran on, which would have replaced the committed clean-room record. Now only
a full run (`python -m cigd all`, as in `make all` and `make smoke`) writes
`results/run_log.json`. Any stage run on its own writes `results/run_log_partial.json`,
which is git-ignored. A test (`tests/test_run_log.py`) checks that a stage run leaves an
existing run log byte for byte unchanged, and the committed clean-room run log was
confirmed unchanged by its git hash.
