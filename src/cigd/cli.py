"""Command-line entry point: python -m cigd [--profile smoke] [--quiet] <stage>."""

import argparse
import os
import random
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from dotenv import load_dotenv
from rich.table import Table

from cigd.config import PROFILES, REPOSITORY_ROOT, StudyConfig, load_config
from cigd.ingest.run import DOWNLOADERS, download_sources
from cigd.ingest.source_check import check_all_sources
from cigd.logging import get_logger, setup_logging, show, stage_banner
from cigd.run_log import record_stage, start_run_log, utc_now_text, write_run_log

logger = get_logger(__name__)

StageFunction = Callable[[StudyConfig, argparse.Namespace], dict[str, Any]]


class OutcomeCounter:
    """Pytest plugin that counts passed, failed and skipped tests for the run log."""

    def __init__(self) -> None:
        self.counts = {"passed": 0, "failed": 0, "skipped": 0}

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        """Count each test once, using its call phase (or setup, if setup failed or skipped)."""
        if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
            self.counts[report.outcome] += 1


def run_check_sources(config: StudyConfig, arguments: argparse.Namespace) -> dict[str, Any]:
    """Probe every official source and fail if any required one is unreachable."""
    checks = check_all_sources(config)
    unreachable = [check.source for check in checks if check.status not in ("200", "skipped")]
    if unreachable:
        raise RuntimeError(f"Sources not reachable from this machine: {unreachable}")
    return {"sources_checked": len(checks), "unreachable": 0}


def run_data(config: StudyConfig, arguments: argparse.Namespace) -> dict[str, Any]:
    """Download every source (or the one named with --source) and check the manifest."""
    selected = [arguments.source] if arguments.source else None
    return download_sources(config, selected)


def run_tests(config: StudyConfig, arguments: argparse.Namespace) -> dict[str, Any]:
    """Run the pytest suite against this profile's outputs."""
    # Tests read the profile from the environment so they check the run that was just built.
    os.environ["CIGD_PROFILE"] = config.profile
    counter = OutcomeCounter()
    exit_code = pytest.main([str(REPOSITORY_ROOT / "tests"), "-q"], plugins=[counter])
    if exit_code not in (pytest.ExitCode.OK, pytest.ExitCode.NO_TESTS_COLLECTED):
        raise RuntimeError(f"pytest failed with exit code {int(exit_code)}: {counter.counts}")
    return counter.counts


STAGES: dict[str, StageFunction] = {
    "check-sources": run_check_sources,
    "data": run_data,
    "test": run_tests,
}
# The order "all" runs the stages in. Later stages read what earlier ones wrote.
PIPELINE_ORDER = ["check-sources", "data", "test"]


def set_global_seeds(seed: int) -> None:
    """Seed Python and NumPy; model libraries receive the same seed explicitly."""
    random.seed(seed)
    np.random.seed(seed)


def run_stage(
    stage_name: str,
    config: StudyConfig,
    arguments: argparse.Namespace,
    run_log: dict[str, Any],
) -> None:
    """Run one stage inside a banner, record its timing and write the run log."""
    started_utc = utc_now_text()
    started = time.perf_counter()
    status = "failed"
    summary: dict[str, Any] = {}
    try:
        with stage_banner(stage_name):
            summary = STAGES[stage_name](config, arguments)
        status = "ok"
        logger.info("%s summary: %s", stage_name, summary)
    finally:
        duration_seconds = time.perf_counter() - started
        record_stage(run_log, stage_name, started_utc, duration_seconds, status, summary)
        write_run_log(run_log, config.run_log_path)


def show_run_summary(run_log: dict[str, Any], config: StudyConfig, log_path: Path) -> None:
    """Print the closing table of stages, durations, outcomes and output paths."""
    table = Table(title=f"Run summary (profile: {config.profile})")
    table.add_column("stage")
    table.add_column("status")
    table.add_column("seconds", justify="right")
    table.add_column("summary")
    for stage_name, entry in run_log["stages"].items():
        summary_text = ", ".join(f"{key}={value}" for key, value in entry["summary"].items())
        table.add_row(stage_name, entry["status"], f"{entry['duration_seconds']:.1f}", summary_text)
    show(table)
    show(f"results:  {config.results_dir}")
    show(f"run log:  {config.run_log_path}")
    show(f"log file: {log_path}")


def parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    """Read the stage name and options from the command line."""
    parser = argparse.ArgumentParser(prog="python -m cigd", description=__doc__)
    parser.add_argument("stage", choices=[*STAGES, "all"])
    parser.add_argument("--profile", choices=PROFILES, default="full")
    parser.add_argument("--quiet", action="store_true", help="turn off progress bars")
    parser.add_argument("--source", choices=list(DOWNLOADERS), help="data stage: one source only")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run one stage, or every stage in order for "all"."""
    arguments = parse_arguments(argv)
    load_dotenv(REPOSITORY_ROOT / ".env")
    quiet = arguments.quiet or os.environ.get("QUIET", "0") == "1"
    config = load_config(arguments.profile)
    log_path = setup_logging(config.logs_dir, quiet)
    set_global_seeds(config.random_seed)

    is_full_run = arguments.stage == "all"
    run_log = start_run_log(config, reset=is_full_run)
    stage_names = PIPELINE_ORDER if is_full_run else [arguments.stage]
    try:
        for stage_name in stage_names:
            run_stage(stage_name, config, arguments, run_log)
    except Exception:
        logger.exception("Pipeline stopped")
        show_run_summary(run_log, config, log_path)
        return 1
    show_run_summary(run_log, config, log_path)
    return 0
