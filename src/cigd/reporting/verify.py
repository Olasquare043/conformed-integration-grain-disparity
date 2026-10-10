"""Check a rebuilt results/ folder against the committed one (a reproducibility check).

What "match" means is fixed here, before any rebuild:

- Exact: data profiles, warehouse row counts, validity counts, grain ratios, raw
  sizes from the manifest, and every non-numeric value (names, flags, wins).
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


def verify_results(config: StudyConfig, reference: str = "HEAD") -> dict[str, Any]:
    """Compare every result table and paper_numbers.json with the committed copies."""
    outcomes: dict[str, str] = {}
    for path in sorted(config.tables_dir.glob("*.csv")):
        if path.stem not in SKIPPED_TABLES:
            outcomes[path.name] = compare_table(path, reference, REPOSITORY_ROOT)
    numbers_path = config.results_dir / "paper_numbers.json"
    outcomes[numbers_path.name] = compare_paper_numbers(numbers_path, reference, REPOSITORY_ROOT)

    differing = [name for name, outcome in outcomes.items() if outcome == "differs"]
    for name, outcome in outcomes.items():
        show(f"{outcome:<18} {name}")
    if differing:
        raise RuntimeError(f"Results differ from {reference}: {differing}")
    return {
        "checked": len(outcomes),
        "matching": sum(outcome == "match" for outcome in outcomes.values()),
        "no_committed_copy": sum(outcome == "no committed copy" for outcome in outcomes.values()),
        "skipped_machine_dependent": len(SKIPPED_TABLES),
    }
