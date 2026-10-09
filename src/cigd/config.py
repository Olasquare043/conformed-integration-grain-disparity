"""Load config/study.yaml and resolve it for one profile (full or smoke)."""

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
STUDY_CONFIG_PATH = REPOSITORY_ROOT / "config" / "study.yaml"
PROFILES = ("full", "smoke")


@dataclass(frozen=True)
class StudyConfig:
    """The study settings for one profile, with every path made absolute."""

    profile: str
    trip_first_month: str
    trip_last_month: str
    price_first_week: date
    data_cutoff_date: date
    random_seed: int
    include_high_volume_fhv: bool
    raw_dir: Path
    derived_dir: Path
    results_dir: Path
    logs_dir: Path
    manifest_path: Path
    sources: dict[str, Any]
    config_hash: str

    @property
    def tables_dir(self) -> Path:
        return self.results_dir / "tables"

    @property
    def figures_dir(self) -> Path:
        return self.results_dir / "figures"

    @property
    def run_log_path(self) -> Path:
        return self.results_dir / "run_log.json"

    @property
    def warehouse_path(self) -> Path:
        return self.derived_dir / "warehouse.duckdb"


def read_study_yaml(path: Path = STUDY_CONFIG_PATH) -> dict[str, Any]:
    """Read the raw study configuration file."""
    with path.open(encoding="utf-8") as config_file:
        return yaml.safe_load(config_file)


def hash_settings(settings: dict[str, Any]) -> str:
    """Return a short SHA-256 of the resolved settings, recorded in the run log."""
    canonical_text = json.dumps(settings, sort_keys=True, default=str)
    return hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()[:16]


def load_config(profile: str = "full") -> StudyConfig:
    """Resolve the study settings for one profile."""
    if profile not in PROFILES:
        raise ValueError(f"Unknown profile {profile!r}; expected one of {PROFILES}")

    raw_settings = read_study_yaml()
    study_settings = {**raw_settings["study"], **raw_settings["profiles"][profile]}
    path_settings = raw_settings["paths"]

    results_key = "smoke_results_dir" if profile == "smoke" else "results_dir"
    resolved_for_hash = {
        "profile": profile,
        "study": study_settings,
        "sources": raw_settings["sources"],
    }

    return StudyConfig(
        profile=profile,
        trip_first_month=study_settings["trip_first_month"],
        trip_last_month=study_settings["trip_last_month"],
        price_first_week=date.fromisoformat(study_settings["price_first_week"]),
        data_cutoff_date=date.fromisoformat(study_settings["data_cutoff_date"]),
        random_seed=int(study_settings["random_seed"]),
        include_high_volume_fhv=bool(study_settings["include_high_volume_fhv"]),
        raw_dir=REPOSITORY_ROOT / path_settings["raw_dir"],
        derived_dir=REPOSITORY_ROOT / path_settings["derived_dir"].format(profile=profile),
        results_dir=REPOSITORY_ROOT / path_settings[results_key],
        logs_dir=REPOSITORY_ROOT / path_settings["logs_dir"],
        manifest_path=REPOSITORY_ROOT / path_settings["manifest"],
        sources=raw_settings["sources"],
        config_hash=hash_settings(resolved_for_hash),
    )
