# Data sources

No data is stored in this repository. Every file is downloaded from its official
publisher by `make data`, and each download is recorded in
`provenance/manifest.csv` with its URL, query parameters, access time, size,
SHA-256 checksum and row count. The MIT licence in `LICENSE` covers the code
only. Each dataset stays under its publisher's terms, summarised below. Please
read the publisher's own terms before reusing the data.

| Source | Role in the study | Publisher and access | Terms |
|---|---|---|---|
| NYC TLC Yellow Taxi trip records | Fine-grain domain (one row per trip) | NYC Taxi and Limousine Commission, monthly Parquet files listed on the [TLC Trip Record Data page](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page) | Public data published by the City of New York, subject to the [NYC terms of use](https://www.nyc.gov/home/terms-of-use.page) |
| NYC TLC taxi zone lookup | Lowest level of the geography dimension | Same TLC page | Same as above |
| NYC TLC High Volume FHV trips (optional, off by default) | Larger grain ratio sensitivity check | Same TLC page | Same as above |
| Gasoline Retail Prices Weekly Average by Region: Beginning January 2017 | Coarse-grain domain (one region per week) | NYSERDA on NY Open Data, dataset [`nqur-w4p7`](https://data.ny.gov/d/nqur-w4p7), Socrata export endpoint. NYSERDA averages AAA Daily Fuel Gauge prices | Open NY terms of use, linked from the dataset page |
| EIA weekly retail regular gasoline prices (New York State, Central Atlantic PADD 1B) | Cross-check of the NYSERDA panel only, never a model input | U.S. Energy Information Administration, [API v2](https://www.eia.gov/opendata/), needs a free key in `EIA_API_KEY` | U.S. government data; see [EIA copyright and reuse](https://www.eia.gov/about/copyrights_reuse.php) |
| Open-Meteo historical weather | Daily weather per metro region | [Open-Meteo archive API](https://open-meteo.com/en/docs/historical-weather-api) | [CC BY 4.0](https://open-meteo.com/en/license), attribution to Open-Meteo required |

## Known quirks

- From January 2025 the yellow taxi files carry a new `cbd_congestion_fee`
  column (the Manhattan congestion relief zone toll that started on 5 January
  2025). The pipeline reads all months with a schema union by name, so months
  before 2025 hold NULL in that column.
- NY Open Data publishes a new week every week and can revise earlier weeks.
  The study therefore fixes a `data_cutoff_date` in `config/study.yaml`, filters
  every analysis to it, and compares each download's checksum with the
  committed manifest.
- data.ny.gov refused every request from the network this pipeline was first
  developed on (HTTP 403 from the Socrata front end), while the other sources
  answered normally. If `make check-sources` reports a 403 for
  `nyserda_gasoline`, the network you are on is being refused by the publisher.
