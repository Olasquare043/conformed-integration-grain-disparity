"""Write results/run_log.json: code version, environment, machine and per-stage timings."""

import json
import platform
import subprocess
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import psutil

from cigd.config import REPOSITORY_ROOT, StudyConfig

RECORDED_LIBRARIES = (
    "duckdb",
    "pandas",
    "pyarrow",
    "numpy",
    "scipy",
    "scikit-learn",
    "lightgbm",
    "statsmodels",
    "matplotlib",
    "requests",
    "rich",
    "papermill",
)


def run_git(*arguments: str) -> str:
    """Run a read-only git command in the repository and return its output."""
    completed = subprocess.run(
        ["git", *arguments],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip()


def describe_git_state() -> dict[str, Any]:
    """Return the current commit and whether the working tree has uncommitted changes."""
    commit = run_git("rev-parse", "HEAD") or "unknown"
    # Untracked files under data/ and logs/ are git-ignored, so they never mark the tree dirty.
    dirty = bool(run_git("status", "--porcelain", "--untracked-files=no"))
    return {"commit": commit, "dirty_tree": dirty}


def library_versions() -> dict[str, str]:
    """Return the installed version of every library that can change a result."""
    versions = {}
    for library in RECORDED_LIBRARIES:
        try:
            versions[library] = version(library)
        except PackageNotFoundError:
            versions[library] = "not installed"
    return versions


def describe_machine() -> dict[str, Any]:
    """Return CPU, memory and operating system details for the integration-cost tables."""
    return {
        "os": platform.platform(),
        "python": platform.python_version(),
        "processor": platform.processor() or platform.machine(),
        "logical_cpus": psutil.cpu_count(logical=True),
        "physical_cpus": psutil.cpu_count(logical=False),
        "ram_gb": round(psutil.virtual_memory().total / 1024**3, 1),
    }


def utc_now_text() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def read_run_log(path: Path) -> dict[str, Any]:
    """Read an existing run log, or return an empty one."""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def start_run_log(config: StudyConfig, reset: bool) -> dict[str, Any]:
    """Refresh the run header, keeping earlier stage entries unless this is a full run."""
    run_log = {} if reset else read_run_log(config.run_log_path)
    run_log.update(
        {
            "profile": config.profile,
            "config_hash": config.config_hash,
            "git": describe_git_state(),
            "library_versions": library_versions(),
            "machine": describe_machine(),
            "updated_utc": utc_now_text(),
        }
    )
    run_log.setdefault("stages", {})
    return run_log


def record_stage(
    run_log: dict[str, Any],
    stage_name: str,
    started_utc: str,
    duration_seconds: float,
    status: str,
    summary: dict[str, Any],
) -> None:
    """Store one stage's timing, status and summary in the run log."""
    run_log["stages"][stage_name] = {
        "started_utc": started_utc,
        "ended_utc": utc_now_text(),
        "duration_seconds": round(duration_seconds, 3),
        "status": status,
        "summary": summary,
    }


def write_run_log(run_log: dict[str, Any], path: Path) -> None:
    """Write the run log as indented JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(run_log, indent=2, default=str) + "\n", encoding="utf-8", newline="\n"
    )
