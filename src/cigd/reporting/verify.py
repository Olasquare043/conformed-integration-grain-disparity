"""Check a rebuilt results/ folder against the committed one (a reproducibility check).

What "match" means is fixed here, before any rebuild:

- Exact: data profiles (and docs/data_profile.md), warehouse row counts, validity
  counts, grain ratios, raw sizes from the manifest, and every non-numeric value
  (names, flags, wins).
- Numeric model results (accuracy, error, p-values, bootstrap intervals) must agree
  to a relative tolerance, because LightGBM and linear algebra libraries can differ
  in the last digits across platforms.
- Timings and storage depend on the machine and the run, so they are skipped.
"""

import json
import math
import subprocess
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd

from cigd.config import REPOSITORY_ROOT, StudyConfig
from cigd.logging import show

RELATIVE_TOLERANCE = 1e-6
ABSOLUTE_TOLERANCE = 1e-9
# Tables whose values depend on the machine and the run.
SKIPPED_TABLES = {
    "integration_build_times",
    "integration_build_time_summary",
    "integration_table_storage",
    "integration_query_latency",
    "integration_latency_aggregate_builds",
    "warehouse_build_steps",
}
# Tables compared with the numeric tolerance; every other table is compared exactly.
TOLERANT_PREFIXES = ("coarse_", "fine_")


def committed_text(reference: str, relative_path: str) -> str | None:
    """Return a file as it was at a git reference, or None if it did not exist."""
    completed = subprocess.run(
        ["git", "show", f"{reference}:{relative_path}"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout if completed.returncode == 0 else None


def numbers_match(first: float, second: float, tolerant: bool) -> bool:
    """Compare two numbers exactly, or within the tolerance."""
    if math.isnan(first) and math.isnan(second):
        return True
    if not tolerant:
        return first == second
    return math.isclose(first, second, rel_tol=RELATIVE_TOLERANCE, abs_tol=ABSOLUTE_TOLERANCE)


def compare_values(first: Any, second: Any, tolerant: bool) -> bool:
    """Compare two values, recursing into lists and dictionaries."""
    if isinstance(first, dict) and isinstance(second, dict):
        return first.keys() == second.keys() and all(
            compare_values(first[key], second[key], tolerant) for key in first
        )
    if isinstance(first, list) and isinstance(second, list):
        return len(first) == len(second) and all(
            compare_values(a, b, tolerant) for a, b in zip(first, second, strict=True)
        )
    both_numbers = all(
        isinstance(value, int | float) and not isinstance(value, bool) for value in (first, second)
    )
    if both_numbers:
        return numbers_match(float(first), float(second), tolerant)
    return first == second


def compare_table(path: Path, reference: str, root: Path) -> str:
    """Return "match", "differs" or "no committed copy" for one result table."""
    committed = committed_text(reference, path.relative_to(root).as_posix())
    if committed is None:
        return "no committed copy"
    old = pd.read_csv(StringIO(committed))
    new = pd.read_csv(path)
    tolerant = path.stem.startswith(TOLERANT_PREFIXES)
    same = list(old.columns) == list(new.columns) and compare_values(
        old.to_dict("list"), new.to_dict("list"), tolerant
    )
    return "match" if same else "differs"


def compare_paper_numbers(path: Path, reference: str, root: Path) -> str:
    """Compare paper_numbers.json without its machine-dependent section."""
    committed = committed_text(reference, path.relative_to(root).as_posix())
    if committed is None:
        return "no committed copy"
    old = json.loads(committed)
    new = json.loads(path.read_text(encoding="utf-8"))
    for numbers in (old, new):
        numbers.pop("machine_dependent", None)
        numbers.pop("tests", None)
    return "match" if compare_values(old, new, tolerant=True) else "differs"


def compare_text_file(path: Path, reference: str) -> str:
    """Compare a generated text document exactly with its committed copy."""
    committed = committed_text(reference, path.relative_to(REPOSITORY_ROOT).as_posix())
    if committed is None:
        return "no committed copy"
    # Git may convert line endings on Windows checkouts; the text itself must match.
    current = path.read_text(encoding="utf-8")
    same = committed.splitlines() == current.splitlines()
    return "match" if same else "differs"


def committed_files(reference: str, folder: str) -> list[str]:
    """List the files git holds under a folder at a reference."""
    completed = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", reference, f"{folder}/"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.split()


def find_missing_outputs(config: StudyConfig, reference: str) -> dict[str, str]:
    """Flag committed tables, figures and notebooks that the rebuild did not produce.

    Without this, a stage that never ran would leave no file to compare and pass unnoticed.
    Machine-dependent tables are still expected to exist; only their values are skipped.
    """
    if config.profile != "full":
        return {}
    missing = {}
    for folder in ("results/tables", "results/figures", "results/notebooks"):
        for relative_path in committed_files(reference, folder):
            if not (REPOSITORY_ROOT / relative_path).exists():
                missing[relative_path] = "missing"
    return missing


def verify_results(config: StudyConfig, reference: str = "HEAD") -> dict[str, Any]:
    """Compare every result table and paper_numbers.json with the committed copies."""
    outcomes: dict[str, str] = {}
    for path in sorted(config.tables_dir.glob("*.csv")):
        if path.stem not in SKIPPED_TABLES:
            outcomes[path.name] = compare_table(path, reference, REPOSITORY_ROOT)
    if config.profile == "full":
        # Includes the configuration hash, so a stale document is caught.
        data_profile = REPOSITORY_ROOT / "docs" / "data_profile.md"
        outcomes["docs/data_profile.md"] = compare_text_file(data_profile, reference)
    numbers_path = config.results_dir / "paper_numbers.json"
    outcomes[numbers_path.name] = compare_paper_numbers(numbers_path, reference, REPOSITORY_ROOT)

    # Expected to be present but not generated by the comparisons above.
    outcomes.update(find_missing_outputs(config, reference))
    differing = [name for name, outcome in outcomes.items() if outcome in ("differs", "missing")]
    for name, outcome in outcomes.items():
        show(f"{outcome:<18} {name}")
    if differing:
        raise RuntimeError(f"Results differ from, or are missing against, {reference}: {differing}")
    return {
        "checked": len(outcomes),
        "matching": sum(outcome == "match" for outcome in outcomes.values()),
        "no_committed_copy": sum(outcome == "no committed copy" for outcome in outcomes.values()),
        "skipped_machine_dependent": len(SKIPPED_TABLES),
    }
