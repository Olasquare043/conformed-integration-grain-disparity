"""One logging setup for every stage: rich console output plus a timestamped log file."""

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    DownloadColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TransferSpeedColumn,
)
from rich.table import Table

LOGGER_NAME = "cigd"
console = Console()
_log_file_console: Console | None = None
_quiet = False


def setup_logging(logs_dir: Path, quiet: bool) -> Path:
    """Send log records to the console and to logs/run_<UTC timestamp>.log."""
    global _log_file_console, _quiet
    _quiet = quiet
    logs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    log_path = logs_dir / f"run_{timestamp}.log"

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False

    console_handler = RichHandler(console=console, show_path=False, markup=False)
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )
    logger.addHandler(file_handler)

    # Tables and banners are written to the same file through a plain-text console.
    _log_file_console = Console(file=file_handler.stream, width=120, no_color=True)
    return log_path


def get_logger(module_name: str) -> logging.Logger:
    """Return a child of the pipeline logger for one module."""
    return logging.getLogger(f"{LOGGER_NAME}.{module_name.removeprefix('cigd.')}")


def show(renderable: Table | str) -> None:
    """Print a table or rule to the console and copy it into the log file."""
    console.print(renderable)
    if _log_file_console is not None:
        _log_file_console.print(renderable)


@contextmanager
def stage_banner(stage_name: str) -> Iterator[None]:
    """Print a start and end banner around one pipeline stage, with elapsed time."""
    started = time.perf_counter()
    show(f"[bold cyan]>>> stage {stage_name}: start[/]")
    try:
        yield
    finally:
        elapsed_seconds = time.perf_counter() - started
        show(f"[bold cyan]<<< stage {stage_name}: end ({elapsed_seconds:.1f} s)[/]")


def make_progress() -> Progress:
    """Return a progress bar, switched off when the run is quiet (CI and Docker logs)."""
    return Progress(
        TextColumn("{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        disable=_quiet,
        transient=False,
    )


def make_download_progress() -> Progress:
    """Return a byte-level progress bar for downloads, switched off when quiet."""
    return Progress(
        TextColumn("{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        console=console,
        disable=_quiet,
        transient=False,
    )
