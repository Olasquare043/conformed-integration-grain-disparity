"""Shared fixtures: the profile under test and a skip when its data is not built yet."""

import os

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
