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
