"""Data cleaning utilities for FormPilot."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


def normalize_column_name(column_name: str) -> str:
    """Convert a column name into a stable snake_case identifier."""

    normalized = column_name.strip().lower()
    normalized = re.sub(r"\s+", "_", normalized)
    normalized = re.sub(r"[^0-9a-ząćęłńóśźż_]+", "", normalized)
    normalized = re.sub(r"_+", "_", normalized)
    return normalized.strip("_")


def make_unique_columns(columns: list[str]) -> list[str]:
    """Ensure repeated labels are made unique while preserving order."""

    counts: dict[str, int] = {}
    unique_columns: list[str] = []
    for column in columns:
        base_name = normalize_column_name(column) or "column"
        counts[base_name] = counts.get(base_name, 0) + 1
        if counts[base_name] == 1:
            unique_columns.append(base_name)
        else:
            unique_columns.append(f"{base_name}_{counts[base_name]}")
    return unique_columns


def clean_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Normalize labels and missing values in a survey dataframe."""

    cleaned = dataframe.copy()
    cleaned.columns = make_unique_columns([str(column) for column in cleaned.columns])
    cleaned = cleaned.replace({"": pd.NA, " ": pd.NA, "  ": pd.NA})
    for column in cleaned.columns:
        if (
            pd.api.types.is_string_dtype(cleaned[column])
            or cleaned[column].dtype == object
        ):
            cleaned[column] = cleaned[column].map(
                lambda value: value.strip() if isinstance(value, str) else value
            )
    return cleaned


def save_cleaned_csv(dataframe: pd.DataFrame, output_path: str | Path) -> Path:
    """Persist a cleaned dataframe to disk."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(path, index=False, encoding="utf-8-sig")
    return path
