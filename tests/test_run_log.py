"""Only a full run writes results/run_log.json; a stage run on its own never touches it."""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from cigd import cli
from cigd.config import StudyConfig, load_config
from cigd.run_log import latest_stage_entry

COMMITTED_RECORD = b'{"sentinel": "the committed record of a full run"}\n'


def stand_in_stage(config: StudyConfig, arguments: Any) -> dict[str, Any]:
    """A cheap stage, so the test exercises the CLI without running the pipeline."""
    return {"rows": 1}


@pytest.fixture
def scratch_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> StudyConfig:
    """Point the CLI at a scratch results folder and a one-stage pipeline."""
    config = replace(
        load_config("smoke"), results_dir=tmp_path / "results", logs_dir=tmp_path / "logs"
    )
    monkeypatch.setattr(cli, "load_config", lambda profile: config)
    monkeypatch.setitem(cli.STAGES, "check-sources", stand_in_stage)
    monkeypatch.setattr(cli, "PIPELINE_ORDER", ["check-sources"])
    return config


def test_a_stage_run_on_its_own_leaves_the_committed_run_log_untouched(
    scratch_config: StudyConfig,
) -> None:
    scratch_config.results_dir.mkdir(parents=True)
    scratch_config.run_log_path.write_bytes(COMMITTED_RECORD)

    assert cli.main(["--quiet", "--profile", "smoke", "check-sources"]) == 0

    assert scratch_config.run_log_path.read_bytes() == COMMITTED_RECORD
    partial = json.loads(scratch_config.partial_run_log_path.read_text(encoding="utf-8"))
    assert list(partial["stages"]) == ["check-sources"]


def test_a_stage_run_on_its_own_creates_no_run_log_when_none_exists(
    scratch_config: StudyConfig,
) -> None:
    assert cli.main(["--quiet", "--profile", "smoke", "check-sources"]) == 0

    assert not scratch_config.run_log_path.exists()
    assert scratch_config.partial_run_log_path.exists()


def test_a_full_run_writes_the_run_log_and_no_partial_log(scratch_config: StudyConfig) -> None:
    scratch_config.results_dir.mkdir(parents=True)
    scratch_config.run_log_path.write_bytes(COMMITTED_RECORD)

    assert cli.main(["--quiet", "--profile", "smoke", "all"]) == 0

    run_log = json.loads(scratch_config.run_log_path.read_text(encoding="utf-8"))
    assert list(run_log["stages"]) == ["check-sources"]
    assert not scratch_config.partial_run_log_path.exists()


def test_the_latest_stage_entry_comes_from_whichever_log_ran_it_last(
    scratch_config: StudyConfig,
) -> None:
    assert latest_stage_entry(scratch_config, "check-sources") is None
    cli.main(["--quiet", "--profile", "smoke", "all"])
    full_entry = latest_stage_entry(scratch_config, "check-sources")
    cli.main(["--quiet", "--profile", "smoke", "check-sources"])
    partial_entry = latest_stage_entry(scratch_config, "check-sources")
    assert full_entry is not None and partial_entry is not None
    assert partial_entry["ended_utc"] >= full_entry["ended_utc"]
