"""Command-line entrypoint for FormPilot."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any, cast

import yaml

from data_cleaner import clean_dataframe, save_cleaned_csv
from data_loader import load_csv
from logger import setup_logging
from probability_model import build_probability_model, save_probability_model
from schema_detector import detect_schema, export_schema


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
    """Run CLI bootstrap and optionally execute CSV loading/cleaning flow."""

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

    csv_path = args.csv or settings.get("paths", {}).get("csv_path")
    cleaned_output = settings.get("paths", {}).get(
        "cleaned_data", "data/cleaned_surveys.csv"
    )
    schema_output = settings.get("paths", {}).get("schema_export", "data/schema.json")
    model_output = settings.get("paths", {}).get(
        "model_export", "data/probability_model.json"
    )
    cleaning_settings = settings.get("cleaning", {})
    drop_timestamp_columns = bool(
        cleaning_settings.get("drop_timestamp_columns", False)
    )
    timestamp_patterns_raw = cleaning_settings.get("timestamp_patterns", [])
    timestamp_patterns = (
        [str(pattern) for pattern in timestamp_patterns_raw]
        if isinstance(timestamp_patterns_raw, list)
        else None
    )

    if csv_path:
        logger.info("Loading CSV data from %s", csv_path)
        dataframe = load_csv(csv_path)
        cleaned = clean_dataframe(
            dataframe,
            drop_timestamp_columns=drop_timestamp_columns,
            timestamp_patterns=timestamp_patterns,
        )
        saved_path = save_cleaned_csv(cleaned, cleaned_output)
        schema = detect_schema(cleaned)
        schema_path = export_schema(schema, schema_output)
        probability_model = build_probability_model(cleaned)
        model_path = save_probability_model(probability_model, model_output)
        logger.info("Cleaned dataset saved to %s", saved_path)
        logger.info("Schema exported to %s", schema_path)
        logger.info("Probability model exported to %s", model_path)
        print(f"Cleaned CSV generated at: {saved_path}")
        print(f"Schema JSON generated at: {schema_path}")
        print(f"Probability model JSON generated at: {model_path}")
    else:
        logger.info("No CSV provided; skipping Phase 2 cleaning flow")
        print("FormPilot bootstrap is ready. Provide --csv to run data cleaning.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
