"""Shared fixtures: the profile under test and a skip when its data is not built yet."""

import os
from collections.abc import Iterator

import duckdb
import pytest

from cigd.config import StudyConfig, load_config
from cigd.ingest.eia import eia_path
from cigd.ingest.nyserda import snapshot_path


@pytest.fixture(scope="session")
def config() -> StudyConfig:
    """Return the profile that was just built (set by the CLI test stage; full by default)."""
    return load_config(os.environ.get("CIGD_PROFILE", "full"))


@pytest.fixture(scope="session")
def price_sources_ready(config: StudyConfig) -> None:
    """Skip data tests when the price files for this profile have not been downloaded."""
    if not snapshot_path(config).exists() or not eia_path(config).exists():
        pytest.skip(f"price data for profile {config.profile!r} not downloaded; run make data")


@pytest.fixture(scope="session")
def warehouse(config: StudyConfig) -> Iterator[duckdb.DuckDBPyConnection]:
    """Open this profile's warehouse read-only, or skip when it has not been built."""
    if not config.warehouse_path.exists():
        pytest.skip(f"warehouse for profile {config.profile!r} not built; run make warehouse")
    connection = duckdb.connect(str(config.warehouse_path), read_only=True)
    yield connection
    connection.close()
