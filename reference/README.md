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
- `nyserda_column` is the matching price column in NY Open Data dataset `nqur-w4p7`.
- `county` for New York City is New York County (Manhattan), where the point sits.
