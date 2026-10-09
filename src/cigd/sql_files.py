"""Read SQL statements from the sql/ directory."""

from cigd.config import REPOSITORY_ROOT

SQL_DIR = REPOSITORY_ROOT / "sql"


def load_sql(relative_path: str) -> str:
    """Return the text of one SQL file, for example "profile/trip_month_profile.sql"."""
    return (SQL_DIR / relative_path).read_text(encoding="utf-8")
