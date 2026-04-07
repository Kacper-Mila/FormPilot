"""Logging helpers for FormPilot."""

from __future__ import annotations

from pathlib import Path
import logging

DEFAULT_LOG_DIR = Path("logs")
DEFAULT_LOG_FILE = "formpilot.log"


def setup_logging(
    log_dir: str | Path = DEFAULT_LOG_DIR, level: int = logging.INFO
) -> logging.Logger:
    """Configure console and file logging and return the project logger."""

    log_directory = Path(log_dir)
    log_directory.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("formpilot")
    logger.setLevel(level)
    logger.propagate = False

    if not logger.handlers:
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)

        file_handler = logging.FileHandler(
            log_directory / DEFAULT_LOG_FILE, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)

        logger.addHandler(stream_handler)
        logger.addHandler(file_handler)

    return logger
