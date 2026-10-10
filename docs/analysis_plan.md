# Analysis plan (pre-registration)

**Status: approved by the author on 2026-10-09, after one round of review
(recorded in `docs/decisions.md`), and committed before any model was trained or
any model output was looked at.** Any later change is added to the change log at
the end, with the date and the reason.

Everything below refers to the frozen snapshot: data cutoff 2025-12-31
(`config/study.yaml`), files as recorded in `provenance/manifest.csv`, and the
warehouse described in `docs/data_dictionary.md`. Design decisions taken during
data preparation are in `docs/decisions.md`.

## 1. Questions

1. **Integration cost.** What does it cost to integrate a one-trip domain and a
   one-region-per-week domain through conformed date and geography dimensions?
   This part is descriptive; it has no hypothesis test.
2. **Downstream model effect, fine grain.** Does adding features that exist only
   because of the conformed dimensions (calendar, weather, fuel price) improve
   trip-level prediction?
3. **Downstream model effect, coarse grain.** Do engineered features (lags,
   calendar, weather and trip demand brought in through the conformed geography)
   beat simple baselines for one-week-ahead regional gasoline price forecasts?

## 2. Fixed inputs from data preparation

- **Week convention.** Weeks start on Monday. A NYSERDA price dated Monday w
  describes the week starting Monday w - 7. Below, *week k* always means a
  described week, identified by its Monday (the warehouse key), and *label k*
  means the NYSERDA date of week k, which is the Monday after it ends.
- **Geography.** As in `reference/borough_to_region.csv`: the five boroughs roll
  up to the New York City region; zone 1 (EWR) to New Jersey, outside the 16 New
  York regions but inside PADD 1B; zones 264 and 265 to Unknown.
- **Trip demand** counts every published yellow taxi trip per pickup zone per day
  (`agg_trip_zone_day`), from 2017-01 to 2025-12, rolled up to weeks and regions
  through `dim_date` and `dim_geography`.
- **Trip validity rules** for `fact_trip`, with thresholds from
  `config/study.yaml` (`quality.trip_validity`), applied in this order:

  | Order | Rule | A trip is removed when |
  |---|---|---|
  | 1 | pickup outside file month | its pickup is not in the month of the file that published it |
  | 2 | excluded vendor | VendorID is 7 |
  | 3 | non-positive duration | dropoff at or before pickup |
  | 4 | duration below minimum | under 60 seconds |
  | 5 | duration above maximum | over 10,800 seconds (3 hours) |
  | 6 | non-positive distance | distance zero, negative or missing |
  | 7 | distance above maximum | over 100 miles |
  | 8 | speed above maximum | average speed over 80 miles per hour |
  | 9 | unknown zone | pickup or dropoff zone 264, 265 or missing |

  Rows removed per rule and year: `results/tables/warehouse_trip_validity.csv`.
- **EIA** is used only to cross-check the NYSERDA panel and is never a model
  input. The original level check was fixed before profiling. The weekly change
  check (change correlation at least 0.75, absolute mean level bias at most
  0.15 USD per gallon) was added on 2026-10-09, **after** the Phase 2 profile had
  been seen, as recorded in `docs/decisions.md`.

## 3. Information sets and publication lags

A feature may use a source only up to the point at which that source would have
been published at the forecast origin. Two information sets are pre-registered.
Every model rung is run under both, and the leakage tests (section 8) check each
one separately.

### 3.1 Evidence for each publication lag

**NYSERDA weekly prices (target series).** By assumption, at origin label t the
prices up to and including label t are known: the forecaster's clock is the
NYSERDA release. The evidence on the real release delay comes from Internet
Archive copies of the data.ny.gov export and metadata, listed with links in
`docs/evidence/nyserda_release_dates.csv` (built by
`docs/evidence/collect_nyserda_release_dates.py`), plus our own download:

- Each archived export shows the newest label at a known capture time. In every
  capture from 2022 to 2026 (10 captures), the label after the newest was still
  missing 2 to 12 days after its date, and from 2023 to 2026 the newest label
  was out within 11 to 19 days of its date.
- An archived metadata copy shows a rows update on 2025-01-31, when the newest
  label was 2025-01-13 (18 days).
- On 2026-10-09 the metadata showed a rows update on 2026-10-02 and the newest
  label was 2026-09-21 (11 days); label 2026-09-28 was still missing 11 days
  after its date.
- Earlier captures show longer gaps: in 2016, 2020 and 2021 the next label was
  still missing 14 to 32 days after its date.

So in recent years a label has typically appeared one and a half to three weeks
after its date. Because the real origin is therefore *later* than label t,
lagging the other sources from label t (as below) is conservative by about two to
three weeks: it never gives them information that a real forecaster at that
release would not have had.

**NYC TLC trip records (trip demand features, and fine-grain training data).**

- The TLC Trip Record Data page states: "Trip data is published monthly on this
  website, typically with a two-month delay to allow time for full vendor
  submissions." (https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page,
  read 2026-10-09.)
- On 2026-10-09 the August 2026 file was available and September 2026 was not
  (HTTP 403), consistent with that statement.
- `Last-Modified` headers on 2026-10-09 are upper bounds on the first release,
  because TLC replaces files after release: January 2025 was listed on the page by
  2025-03-29, yet its file is dated 2025-04-23.
- Archived copies of the TLC page in the Internet Archive date the first
  release of every month from 2023-10 to 2026-08 (35 months).
  `docs/evidence/tlc_release_dates.csv` gives, for each month, a link to the last
  snapshot that does not list it and the first that does, the file's
  `Last-Modified` header, and a verdict for each candidate rule. A month counts
  as released once its file can be downloaded, because the file URL follows a
  fixed pattern; for 2024-02 the file existed a few days before the page linked
  to it. The script that builds the table is
  `docs/evidence/collect_tlc_release_dates.py`.
- Findings: 33 of the 35 months were released within 19 to 57 days of the end
  of the month (median 49 days). Two came much later: December 2025 between
  2026-03-23 and 2026-03-25 (82 to 84 days after the month ended, released
  together with January and February 2026) and June 2026 between 2026-09-10 and
  2026-09-17 (72 to 79 days).
- A rule of "usable from the first day of month m + 3", which is the literal
  reading of TLC's "two-month delay", would have used both of those months
  before they existed. A rule of "usable from the first day of month m + 4"
  holds for all 35 months.
- Our own manifest access history adds no precision: every study file was first
  downloaded on 2026-10-09, long after release.
- The evidence starts in late 2023. The study period starts in 2017, so the rule
  assumes that release practice before 2023 was no faster than after it.

**Rule (primary):** the trip records for month m are usable from the first day
of month m + 4 (for example, August data from 1 December). This is the shortest
calendar-month rule that every observed release satisfies.

**Open-Meteo archive (weather features).** The Open-Meteo historical weather API
documentation lists ERA5 as "Daily with 5 days delay"
(https://open-meteo.com/en/docs/historical-weather-api, read 2026-10-09). A query
on 2026-10-09 for New York City with `models=era5` returned values through
2026-10-02 and nothing after it, a 7-day delay on that day. **Rule (primary):**
weather for day d is usable from day d + 7.

**Vintage.** Every source is used as downloaded on the access dates in the
manifest, not as it was first published. TLC replaces files after release (see
January 2025 above), so the realistic information set reproduces publication
*timing*, not the original *vintage*. This is a stated limitation.

### 3.2 The two information sets

| Source | Primary (realistic) | Secondary (best case, timely availability) |
|---|---|---|
| NYSERDA prices | labels up to t | labels up to t |
| Weather | days up to t - 7 | days up to t - 1 (all of week k) |
| Trip demand (coarse task) | days in months released by t: months up to month(t) - 4 | days up to t - 1 (all of week k) |
| Calendar (`dim_date`) | known in advance | known in advance |

Here t is the origin date: label t for the coarse task, the pickup day for the
fine task. In the fine-grain task the secondary set uses the weather of the
pickup day itself, an observed stand-in for a same-day forecast. The secondary
set is reported explicitly as a best case that no real
forecaster could reach; it bounds how much the integration could help if every
source were published at once.

## 4. Fine-grain task: trip duration

**Target:** natural log of `duration_seconds` from `fact_trip`.

**Population and sampling.** Trips in `fact_trip`. A trip's sample bucket is the
first 8 hexadecimal digits of the MD5 of its `trip_id` (as text), modulo 1,000,
so selection depends on content only and never on scan order. Training rows:
buckets 0 to 49 (5 percent) of the training months. Test rows: buckets 500 to 519
(2 percent) of the test month. The same test trips are used by every rung and
both information sets.

**Rolling origin.** One origin per test month, refit at every origin.

| Run | Test months | Training months, primary | Training months, secondary |
|---|---|---|---|
| Main | 2025-01 to 2025-12 | 2024-01 to m - 4 | 2024-01 to m - 1 |
| Robustness (2024 only) | 2024-07 to 2024-12 | 2024-01 to m - 4 | 2024-01 to m - 1 |

The primary set ends training at month m - 4 because, under the TLC rule above,
trips from months m - 3 to m - 1 are not yet published at the start of month m.
For the first robustness month (2024-07) this leaves three training months
(2024-01 to 2024-03).
The 2024-only run sits before the 2025 data quality changes.

**Booking-time distance.** The main models do not use the recorded
`trip_distance`: it is measured after the trip and largely determines its
duration, which would hide the effect of the integrated features. Instead they
use the straight-line distance between the centroids of the pickup and dropoff
zones, computed from the official TLC taxi zone shapefile
(`https://d37ci6vzurychx.cloudfront.net/misc/taxi_zones.zip`, recorded in the
manifest). The shapefile is in NAD83 New York State Plane, Long Island zone, in US
survey feet, so the distance is the Euclidean distance between centroids divided
by 5,280. A zone drawn as several polygons in the shapefile is merged into one
shape before its centroid is taken. A trip within one zone has distance zero.
The centroids are carried by `dim_geography`, so the feature reaches the trips
through the conformed geography dimension.

**Naive baseline (N0).** For each test trip, the median duration in the training
trips with the same pickup zone, dropoff zone and hour of the week (168 hours);
if there is none, the median for the same zone pair; if there is none, the median
of all training trips. It is fitted on the same training rows as the rungs and
predicts log duration as the log of that median.

**Rungs** (each adds to the one before):

| Rung | Features |
|---|---|
| F0 trip only | pickup zone, dropoff zone (both categorical), centroid distance between them, pickup hour, pickup minute of day, vendor, rate code (missing kept as its own value), passenger count |
| F1 + calendar | from `dim_date` for the pickup day: ISO day of week, weekend flag, federal holiday flag, month, day of month |
| F2 + weather | NYC region daily weather through `dim_geography` and `dim_date`: mean temperature, precipitation, snowfall, maximum wind. Primary: day d - 7. Secondary: day d |
| F3 + fuel price | NYC regional price of the latest label on or before the pickup day, and its one-week change |

Recorded trip distance, fare, tip, tolls, totals and payment type are never
features of the main models: they are set at or after the end of the trip.

**Sensitivity run (recorded distance).** Rungs F0 to F3 are run once more with
the recorded `trip_distance` added, on the main test months, under both
information sets. It is labelled a sensitivity run everywhere it is reported and
is not part of the win criteria. It shows how much of each rung's gain survives
when the post-trip distance is known.

## 5. Coarse-grain task: one-week-ahead regional gasoline price

**Units:** the 16 NYSERDA metro regions. The New York State average is an
aggregate of them, so it is a feature (see C1) but not a forecast target.

**Target:** the next published NYSERDA weekly value for the region: at origin
label t, the value published under label t + 7 days, which describes week k + 1.
If that label was never published, there is no target and the forecast is
skipped.

**What is modelled.** Every learner predicts the one-week change
y(k+1) - y(k), not the level, so a tree model is not limited to the price range
seen in training. The level forecast is y(k) plus the predicted change, and all
metrics are computed on the level (which equals the error on the change).

**Periods.**

- First training target: week starting 2018-05-07, the first week at which every
  feature of every rung exists under both information sets (the 52-week change in
  trip demand, measured on the latest week released under the TLC rule, needs
  demand back to the first full week of 2017).
- Evaluation: targets from the week starting 2023-01-02 to the week starting
  2025-12-22, 156 target weeks per region, 2,496 region-week forecasts before
  skips.

**Rolling origin.** Step of one week, expanding training window, refit at every
origin. At origin k, a training row is usable only if its target week is k or
earlier.

**Baselines:**

- B1 random walk: a predicted change of zero, so y(k+1) is forecast as y(k).
- B2 seasonal naive: y(k+1) forecast as the price 52 weeks before the target
  week. If that week is missing, the price 53 weeks before is used.

**Learners.** Every rung is fitted with two learners on the same features, and
both are reported:

- LightGBM, pooled over regions, region as a categorical feature.
- Ridge regression, pooled over regions, region one-hot encoded. Features are
  standardised with the training window's mean and standard deviation. A missing
  feature value is replaced by the training-window mean, and a missing-value
  indicator is added for every feature that can be missing (the lag features
  around the missing week, and the trip-demand features outside New York City).
  **Penalty rule:** the ridge penalty alpha is chosen once per rung and
  information set from {0.01, 0.1, 1, 10, 100, 1000}, by the same weekly
  rolling-origin procedure run on target weeks 2022-01-03 to 2022-12-26, which is
  before the evaluation period, with training from the first training target.
  The alpha with the lowest pooled MAE is kept, the larger one on a tie, and it
  is then frozen for every evaluation origin. The evaluation period is never used
  to choose it.

**Rungs** (each adds to the one before):

| Rung | Features |
|---|---|
| C1 lags + calendar | last four weekly changes, current level, current spread to the state average, 52-week change, region; week of year and number of federal holidays in the target week (from `dim_date`) |
| C2 + weather | the region's latest available complete week of weather (`agg_weather_region_week`): mean temperature, precipitation, snowfall. Primary: week k - 1. Secondary: week k |
| C3 + trip demand | NYC region only (missing for other regions): log trips in the latest available complete week, its 4-week and 52-week log changes (`agg_trip_region_week`). Primary: the latest complete week inside the released months. Secondary: week k |

**C3 is evaluated on the New York City region only**, because trip demand
exists only for that region. Its comparisons are C3 against C2 and C3 against
B1, for each learner, on the NYC series of about 155 forecasts. **Power is limited.** For each of
these tests the plan reports the minimum detectable difference in mean absolute
error at 80 percent power and a 5 percent two-sided level, computed as
(1.96 + 0.84) times the HAC standard error of the mean loss difference, both in
dollars and as a percent of the random walk MAE. A non-significant result is
reported as "not detectable at this sample size", never as "no effect".

**COVID (2020).** Weekly NYC yellow taxi demand fell from an average of 1.60
million trips in 2019 to 455 thousand in 2020 (lowest week 50,741), and was still
about half the 2019 level in 2025. Main analysis: all weeks are kept in training
for every rung, with no indicator and no adjustment; the evaluation period
(2023 to 2025) is outside the pandemic. Robustness: the same rolling evaluation,
with training rows whose target week falls between 2020-03-02 and 2021-06-28
(New York's pause order to the lifting of most restrictions) removed from every
rung. The same rows are removed from every rung, so rung comparisons stay like
for like.

**Missing weeks.** No price is imputed. The week labelled 2024-12-30 (week
starting 2024-12-23) is missing for every region:

- the forecast whose target is that week is skipped;
- the origin at that label does not exist, because nothing was published, so
  the forecast of the next week is skipped as well;
- lag features that need the missing week are left missing (LightGBM handles
  missing values natively; ridge uses the rule above).

The number of skipped forecasts is reported per region and in total. Forecasts
are skipped identically for every model, so all comparisons use the same
region-weeks.

## 6. Models and determinism

LightGBM is used for every rung of both tasks, and ridge regression is added
for the coarse task (section 5). LightGBM hyperparameters are fixed here and never
tuned, so a change in error comes from the features, not from the model:

| Setting | Fine grain | Coarse grain |
|---|---|---|
| trees | 500 | 300 |
| learning rate | 0.05 | 0.05 |
| leaves | 63 | 15 |
| minimum rows per leaf | 100 | 20 |
| row and feature subsampling | none | none |

Determinism: `deterministic=True`, `force_row_wise=True`, a fixed thread count,
and the seed from `config/study.yaml` passed to Python, NumPy and LightGBM. With
no subsampling the fits do not depend on the seed. A test checks that two smoke
runs give identical result tables.

## 7. Metrics, tests and what counts as a win

**Metrics.**

- Fine grain: MAE and RMSE of log duration; MAE in seconds and MAPE of duration
  in seconds after back-transforming.
- Coarse grain: MAE, RMSE (dollars per gallon) and MAPE, pooled over regions and
  per region, plus the number of regions where a model's MAE is below the random
  walk's.

**Diebold-Mariano tests.** Absolute-error loss is primary; squared-error loss is
reported alongside it. Each test is two-sided, uses the Harvey, Leybourne and
Newbold small-sample correction with Student t reference, and Newey-West HAC
variance with bandwidth floor(4 (T / 100)^(2/9)).

- Coarse, per region: on that region's weekly loss differences (T about 155).
- Coarse, pooled: the loss difference is first averaged over the 16 regions
  within each week, and the test is run on that weekly series. This clusters by
  week, since the regions share common shocks, and the HAC handles correlation
  across weeks.
- Fine grain: the loss difference is averaged over trips within each pickup day,
  and the test is run on that daily series.

**Effect sizes with confidence intervals.** For every comparison, the effect
size is the difference in MAE (model minus comparator) and the same difference as
a percent of the comparator's MAE. Each comes with a 95 percent percentile
confidence interval from a block bootstrap with 2,000 resamples and the seed from
`config/study.yaml`:

- coarse task: whole weeks are resampled with replacement, keeping all regions
  of a week together;
- fine task: whole pickup days are resampled with replacement, keeping all trips
  of a day together.

Confidence intervals are reported next to the DM tests; the win criteria below
use the DM tests.

**Multiple comparisons.** Holm correction within each family below; both raw and
adjusted p-values are reported.

**Wins.**

- Fine grain: a rung beats the one below it if its MAE on log duration is lower
  and the Holm-adjusted DM p-value is below 0.05. Family: the four adjacent
  comparisons (F0 vs N0, F1 vs F0, F2 vs F1, F3 vs F2), separately for each
  information set and each run (main, 2024 only).
- Coarse grain, all regions: a model beats the random walk if its pooled MAE is
  lower and the Holm-adjusted pooled DM p-value is below 0.05. Family: B2, and C1
  and C2 with each learner, against B1 (five comparisons), separately for each
  information set. The per-region win count and per-region p-values are reported
  but are not a win criterion.
- Coarse grain, NYC (C3): C3 beats C2 (and, separately, B1) if its NYC MAE is
  lower and the Holm-adjusted DM p-value is below 0.05. Family: those two
  comparisons for each learner (four comparisons). The minimum detectable
  difference is reported with each.
- Results going the other way, or not significant, are reported with the same
  prominence as wins.

**Robustness and sensitivity runs** (2024-only fine-grain run, recorded-distance
fine-grain run, COVID-excluded coarse training) are reported next to the main
results, with the same metrics, tests and confidence intervals. They do not
change the win criteria above.

## 8. Leakage tests

Implemented in `tests/` before any model runs. Each is checked under both
information sets.

- Coarse grain, for every feature row at origin k:
  - every price input belongs to week k or earlier;
  - every weather day is on or before t - 7 (primary) or t - 1 (secondary);
  - every trip-demand day is inside a released month (primary) or on or before
    t - 1 (secondary);
  - every training row's target week is week k or earlier.
- Fine grain:
  - every weather day is on or before d - 7 (primary) or d (secondary);
  - every fuel price label is on or before the pickup day;
  - every training trip is from month m - 4 or earlier (primary) or m - 1 or
    earlier (secondary);
  - the test trip set is identical across rungs and N0;
  - the main fine-grain feature sets never contain the recorded trip distance;
  - N0 medians use training trips only.
- Week convention: every NYSERDA label is its described week's Monday plus seven
  days (already in `tests/test_warehouse_conformance.py`).

## 9. Integration cost measurements (experiment A)

- **Build time** of every warehouse step and pipeline stage, from
  `results/run_log.json`. The warehouse is built three times in the paper run;
  the median and range are reported per step.
- **Storage:** raw bytes per source from the manifest, the size of the
  warehouse file, and the estimated size and row count of each table.
- **Grain ratio:** valid trips per NYC region-week in 2024 to 2025, trips per
  fuel price row, and all published trips per NYC region-week over 2017 to
  2025.
- **Query latency.** One analytical question: weekly count of valid NYC trips
  next to the NYC regional price, for 2024 to 2025. It is answered at four
  grains: `fact_trip` with the dimensions, and zone-day, zone-week and
  region-week aggregates. The warehouse aggregates count every published trip,
  so for this experiment the three aggregate grains are rebuilt from `fact_trip`
  as temporary tables, through the same dimensions, and their build times are
  reported too. Each query runs once as a warm-up and then 30 timed runs on one
  connection. The median and interquartile range are reported. The four answers
  must be identical, and the run fails if they are not.
- **Conformance:** the number of tests passed per category: grain, referential
  integrity, mappings, reconciliation, leakage.

## 10. Outputs

Every table goes to `results/tables/`, every figure to `results/figures/` (PNG
at 300 dpi and PDF), and every number quoted in the paper to
`results/paper_numbers.json`, all written by code.

## Change log

| Date | Change | Reason |
|---|---|---|
| 2026-10-10 | Added an exploratory comparison of C2 against C1 (the weather increment) for the coarse task, both learners, all regions, with bootstrap intervals and raw DM p-values: `results/tables/coarse_exploratory_comparisons.csv`. It is outside every registered Holm family and has no win criterion. | The registered ladder tests C3 against C2 and each model against the random walk, but never the step from C1 to C2, which is the weather part of the integration question. Added after the main results were seen, so it is post hoc and reported as such. |
| 2026-10-10 | Wrote per-region Diebold-Mariano tests against the random walk to `results/tables/coarse_region_comparisons.csv` (raw p-values, no win criterion). | Section 7 promises them; they were computed from the stored forecasts rather than refitting. No change of design. |
| 2026-10-10 | Limitation recorded, no change of design: F1 (calendar) features come from the pickup timestamp alone, so F0 omits them by choice. The F0 to F1 gain is not a cross-grain integration effect; only weather (F2) and fuel price (F3) cross the grain. | Needed to read the fine-grain results correctly. |
| 2026-10-10 | Limitation recorded, no change of design: F3 uses the NYSERDA label dated on or before the pickup day. Labels were published about 11 to 19 days after their date (section 3.1), so the primary information set gives fuel price more recent information than a real forecaster would have had. | The fuel result is therefore an upper bound on what a real-time user could gain. |
| 2026-10-10 | Limitation recorded, no change of design: wins of C3 against the random walk on New York City come mostly from the lag features shared with C1 and C2; the effect attributable to trip demand is the C3 against C2 comparison. | Prevents a misreading of the NYC wins. |
