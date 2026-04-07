"""Command-line entrypoint for FormPilot."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any, cast

import yaml

from logger import setup_logging


def load_settings(config_path: str | Path) -> dict[str, Any]:
    """Load YAML settings for the project."""

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        loaded: object = yaml.safe_load(handle)

    if loaded is None:
        return {}

    if not isinstance(loaded, dict):
        raise ValueError(f"Configuration file must contain a mapping: {path}")

    return cast(dict[str, Any], loaded)


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""

    parser = argparse.ArgumentParser(description="FormPilot project skeleton")
    parser.add_argument(
        "--config", default="config/settings.yaml", help="Path to the YAML config file"
    )
    parser.add_argument("--csv", default=None, help="Path to the input CSV file")
    parser.add_argument("--form", default=None, help="Google Form URL")
    parser.add_argument("--count", type=int, default=1, help="Number of submissions")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the skeleton CLI and verify config/logging bootstrap."""

    args = build_parser().parse_args(argv)
    settings = load_settings(args.config)
    log_dir = settings.get("paths", {}).get("logs_dir", "logs")
    log_level_name = str(settings.get("app", {}).get("log_level", "INFO")).upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    logger = setup_logging(log_dir=log_dir, level=log_level)

    logger.info("FormPilot skeleton initialized")
    logger.info("Config loaded from %s", args.config)
    if args.csv:
        logger.info("CSV argument received: %s", args.csv)
    if args.form:
        logger.info("Form URL received: %s", args.form)
    logger.info("Submission count requested: %s", args.count)

    print("FormPilot skeleton is ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
