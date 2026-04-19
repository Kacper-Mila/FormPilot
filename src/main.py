"""Command-line entrypoint for FormPilot."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, cast

import yaml

from data_cleaner import clean_dataframe, save_cleaned_csv
from data_loader import load_csv
from logger import setup_logging
from persona_generator import PersonaGenerator
from probability_model import (
    ProbabilityModel,
    build_probability_model,
    load_probability_model,
    save_probability_model,
)
from response_generator import ResponseGenerator
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
    parser.add_argument(
        "--list-personas",
        action="store_true",
        help="Print available personas and exit",
    )
    parser.add_argument(
        "--generate-response",
        action="store_true",
        help="Generate one sample synthetic response",
    )
    parser.add_argument(
        "--persona-mode",
        choices=["weighted", "uniform"],
        default=None,
        help="Persona selection mode for --generate-response",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional random seed for reproducible persona and response sampling",
    )
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
    persona_settings = settings.get("persona", {})

    list_personas_enabled = args.list_personas or bool(
        persona_settings.get("list_personas", False)
    )
    generate_response_enabled = args.generate_response or bool(
        persona_settings.get("generate_response", False)
    )

    configured_mode = str(persona_settings.get("mode", "weighted")).lower()
    if configured_mode not in {"weighted", "uniform"}:
        raise ValueError(
            "Invalid persona.mode in settings. Expected one of: weighted, uniform"
        )
    persona_mode = args.persona_mode or configured_mode

    seed_value = args.seed
    if seed_value is None and persona_settings.get("seed") is not None:
        seed_value = int(persona_settings.get("seed"))

    probability_model: ProbabilityModel | None = None

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

    persona_generator = PersonaGenerator(random_seed=seed_value)
    if list_personas_enabled:
        print("Available personas:")
        print(
            json.dumps(persona_generator.list_personas(), ensure_ascii=False, indent=2)
        )

    if generate_response_enabled:
        if probability_model is None:
            model_path = Path(model_output)
            if not model_path.exists():
                raise FileNotFoundError(
                    "No probability model available. Provide --csv first or ensure "
                    f"model exists at: {model_path}"
                )
            probability_model = load_probability_model(model_path)
            logger.info("Loaded probability model from %s", model_path)

        generator = ResponseGenerator(
            model=probability_model,
            random_seed=seed_value,
            persona_generator=persona_generator,
        )

        if persona_mode == "uniform":
            persona = persona_generator.choose_persona(weighted=False)
            generated = generator.generate_response(persona=persona)
        else:
            generated = generator.generate_response()

        print("Generated response:")
        print(json.dumps(generated.to_dict(), ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
