"""Profile the daily weather series for each metro region."""

import pandas as pd

WEATHER_VARIABLES = (
    "temperature_2m_max",
    "temperature_2m_min",
    "temperature_2m_mean",
    "precipitation_sum",
    "snowfall_sum",
    "wind_speed_10m_max",
)


def profile_weather(weather: pd.DataFrame) -> pd.DataFrame:
    """Summarise day coverage, missing values and ranges for each region."""
    region_rows = []
    for region_code, region_weather in weather.groupby("region_code"):
        first_day = region_weather["weather_date"].min()
        last_day = region_weather["weather_date"].max()
        days_expected = (last_day - first_day).days + 1
        missing_values = int(region_weather[list(WEATHER_VARIABLES)].isna().sum().sum())
        region_rows.append(
            {
                "region_code": region_code,
                "first_day": first_day.date(),
                "last_day": last_day.date(),
                "days": len(region_weather),
                "days_expected": days_expected,
                "duplicate_days": int(region_weather["weather_date"].duplicated().sum()),
                "missing_values": missing_values,
                "mean_temperature_c": round(region_weather["temperature_2m_mean"].mean(), 2),
                "min_temperature_c": region_weather["temperature_2m_min"].min(),
                "max_temperature_c": region_weather["temperature_2m_max"].max(),
                "max_daily_precipitation_mm": region_weather["precipitation_sum"].max(),
                "max_daily_snowfall_cm": region_weather["snowfall_sum"].max(),
            }
        )
    return pd.DataFrame(region_rows)
