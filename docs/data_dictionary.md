# Data dictionary

The warehouse is one DuckDB file per profile (`data/full/warehouse.duckdb`,
`data/smoke/warehouse.duckdb`). It is rebuilt from scratch by `make warehouse`,
one SQL file per table in `sql/warehouse/`. The first line of each file states
the table's grain, and `results/tables/warehouse_tables.csv` lists every table
with that grain and its row count.

## Conventions

- **Dates.** Every date key is an integer `YYYYMMDD` that joins to
  `dim_date.date_key`.
- **Weeks.** A week starts on Monday, as in NYSERDA and EIA. `week_start_date_key`
  is that Monday.
- **NYSERDA week label.** A NYSERDA price dated Monday w describes the seven days
  before it, Monday w - 7 to Sunday w - 1 (see `docs/decisions.md`). The price
  fact is keyed by the week it describes, and the published Monday is kept as
  `nyserda_week_label_date_key`. Every day in `dim_date` carries the label of its
  week in `nyserda_week_label_date`.
- **Geography.** Every geography key joins to `dim_geography.geography_key`. Each
  member carries the codes of all its ancestors, so a fact rolls up by grouping on
  `region_code`, `state_code`, `padd_code` or `country_code`.
- **Units.** Prices in US dollars per gallon, distance in miles, durations in
  seconds, temperature in degrees Celsius, precipitation in millimetres, snowfall
  in centimetres, wind speed in km/h.

## Dimensions

### dim_date

One row per calendar day, from two weeks before the first price week to the data
cutoff.

| Column | Meaning |
|---|---|
| `date_key` | `YYYYMMDD` |
| `full_date` | The day |
| `year`, `quarter`, `month`, `month_name`, `day_of_month` | Calendar parts |
| `iso_day_of_week`, `day_name`, `is_weekend` | 1 is Monday; Saturday and Sunday are weekend days |
| `iso_year`, `iso_week` | ISO 8601 week numbering |
| `week_start_date`, `week_start_date_key` | Monday of the day's week |
| `nyserda_week_label_date` | The NYSERDA date that describes this day's week: `week_start_date + 7` |
| `is_us_federal_holiday`, `us_federal_holiday_name` | Observed US federal holidays (pandas `USFederalHolidayCalendar`, including Juneteenth from 2021) |

### dim_geography

One row per member at each level of the nested hierarchy: zone, borough, metro
region, state, PADD and country. The rule is in `reference/borough_to_region.csv`.

| Column | Meaning |
|---|---|
| `geography_key` | Surrogate key, assigned in a fixed order (level, then code) |
| `geography_level` | `zone`, `borough`, `metro_region`, `state`, `padd` or `country` |
| `geography_code`, `geography_name` | The member's code and name; zones use their three-digit TLC id |
| `zone_id` | TLC LocationID (zones only) |
| `borough_code`, `region_code`, `state_code`, `padd_code`, `country_code` | Codes of the member and its ancestors |
| `is_nyserda_region` | True for the 16 NYSERDA metro regions |

Members outside the 16 regions: `new_jersey_outside_ny_regions` (Newark Airport,
in New Jersey and PADD 1B), and an `unknown` member at every level for TLC zones
264 and 265.

## Facts

### fact_trip

One valid yellow taxi trip from 2024 to 2025.

| Column | Meaning |
|---|---|
| `trip_id` | File month `YYYYMM` times 10^8 plus the trip's row position in the published file |
| `pickup_date_key`, `pickup_hour` | Pickup day and hour (local New York time, as published) |
| `pickup_geography_key`, `dropoff_geography_key` | Pickup and dropoff zones |
| `pickup_datetime`, `dropoff_datetime`, `duration_seconds` | Timestamps and their difference |
| `vendor_id`, `rate_code_id`, `payment_type`, `passenger_count` | As published |
| `trip_distance_miles`, `fare_amount`, `total_amount` | As published |
| `cbd_congestion_fee` | Congestion relief zone fee; NULL before January 2025, when the column did not exist |

**Validity rules.** A trip is loaded only if it passes every rule.
`results/tables/warehouse_trip_validity.csv` reports, for each year, how many
trips fail each rule and how many each rule removes when the rules are applied in
this order. Thresholds are in `config/study.yaml` under `quality.trip_validity`.

| Order | Rule | A trip fails when |
|---|---|---|
| 1 | `pickup_outside_file_month` | its pickup is not in the month of the file that published it (for example pickups dated 2002 or 2026) |
| 2 | `excluded_vendor` | its VendorID is 7 (every VendorID 7 trip has a dropoff at or before its pickup) |
| 3 | `nonpositive_duration` | the dropoff is at or before the pickup |
| 4 | `duration_below_minimum` | it lasts less than 60 seconds |
| 5 | `duration_above_maximum` | it lasts more than 3 hours |
| 6 | `nonpositive_distance` | its distance is zero, negative or missing |
| 7 | `distance_above_maximum` | its distance is more than 100 miles |
| 8 | `speed_above_maximum` | its average speed is above 80 miles per hour |
| 9 | `unknown_zone` | its pickup or dropoff zone is Unknown (264), N/A (265) or missing |

Fare is not checked, because the fine-grain target is trip duration and fare is
never a model input.

### fact_fuel_price_weekly

One NYSERDA price series (the 16 metro regions and the New York State average)
per described week.

| Column | Meaning |
|---|---|
| `week_start_date_key` | Monday of the week the price describes |
| `nyserda_week_label_date_key` | The Monday NYSERDA dated the price with (one week later) |
| `geography_key` | A metro region, or New York State for the state average |
| `price_usd_per_gallon` | Weekly average regular gasoline price |

Blank prices are not loaded. Every missing series-week is listed in
`reference/known_price_gaps.csv`.

### fact_weather_daily

One metro region per day, from Open-Meteo (ERA5) at the region's point in
`reference/region_coordinates.csv`: `temperature_max_c`, `temperature_min_c`,
`temperature_mean_c`, `precipitation_mm`, `snowfall_cm`, `wind_speed_max_kmh`.

## Aggregates at the shared grains

All aggregates are built from facts or staged counts through `dim_date` and
`dim_geography`, never by joining the domains directly.

| Table | Grain | Built from |
|---|---|---|
| `agg_trip_zone_day` | pickup zone per day, 2017 to the cutoff | `stg_trip_zone_day` (every published trip) |
| `agg_trip_zone_week` | pickup zone per Monday week | `agg_trip_zone_day` through `dim_date` |
| `agg_trip_region_week` | metro region per Monday week, with `days_with_trips` | `agg_trip_zone_day` through `dim_date` and the zone's `region_code` |
| `agg_weather_region_week` | metro region per Monday week | `fact_weather_daily` through `dim_date` |

Trip demand counts **every published trip**, before the validity rules, so it has
the same meaning in 2017 as in 2025. Pickups dated outside their file's month are
left out.

## Staging and audit tables

| Table | Contents |
|---|---|
| `stg_zone_lookup`, `stg_borough_region`, `stg_metro_region` | The TLC zone lookup and the two reference CSVs |
| `stg_us_federal_holiday` | Holidays used by `dim_date` |
| `stg_trip_validity_threshold` | The validity thresholds from config, as one row |
| `stg_fuel_price`, `stg_weather` | Tidy NYSERDA snapshot and weather downloads |
| `stg_trip_zone_day` | Zone-day trip counts for every month, as counted from each file (history months from their kept aggregates) |
| `audit_trip_validity` | Trips failing and removed per validity rule per year |
