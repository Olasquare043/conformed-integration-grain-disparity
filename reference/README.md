# Reference mappings

Versioned CSVs that the pipeline reads but never downloads. Any change to a file
here is a change to the study design and should be committed with a reason.

## region_coordinates.csv

One representative point per NYSERDA metro region, used to request daily
weather from Open-Meteo.

- Rule: the GeoNames point of the city the region is named after. Two regions
  are named after counties, so they use the county seat: Dutchess uses
  Poughkeepsie and Nassau uses Mineola. New York City uses the GeoNames point
  for New York (lower Manhattan).
- Source: Open-Meteo geocoding API (`https://geocoding-api.open-meteo.com/v1/search`,
  which serves GeoNames), filtered to `admin1 = New York`, accessed 2026-10-09.
  The `geonames_id` column lets anyone check each point.
- `nyserda_column` is the exact header of the matching price column in the CSV
  export of NY Open Data dataset `nqur-w4p7`. The pipeline requires an exact
  match, so a renamed column stops the run instead of being silently dropped.
- `county` for New York City is New York County (Manhattan), where the point sits.

## known_price_gaps.csv

Every week without a price in the NYSERDA panel, with the reason. `series_code`
`all` means the whole week is missing from the export. The test suite fails if
the panel has a gap that is not listed here, so no gap can go unnoticed. Gaps
are never filled in the raw data; how the models treat them is set in
`docs/analysis_plan.md`.

## borough_to_region.csv

The rule that places every TLC taxi zone in the nested geography hierarchy
(zone, borough, metro region, state, PADD, country). A zone inherits everything
above it from its borough in the TLC zone lookup, so the mapping is stated once
per borough, with the reason in the `rule` column:

- The five New York City boroughs roll up to the New York City metro region,
  New York State, PADD 1B and the United States.
- EWR (zone 1, Newark Airport) is in New Jersey: it sits outside the 16 New York
  metro regions but inside PADD 1B and the United States.
- Unknown (zone 264) and N/A (zone 265, "Outside of NYC") map to an explicit
  Unknown member at every level, so their trips keep a valid key.

The 15 metro regions outside New York City come from `region_coordinates.csv`
and exist in the dimension even though no taxi trip maps to them. The tests fail
if a borough in the TLC lookup has no row here, or if a row here is never used.
