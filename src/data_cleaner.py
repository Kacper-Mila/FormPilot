"""Data cleaning utilities for FormPilot."""

from __future__ import annotations

import re
import warnings
from pathlib import Path
from typing import Sequence

import pandas as pd


_DEFAULT_TIMESTAMP_PATTERNS: tuple[str, ...] = (
    "timestamp",
    "time_stamp",
    "czas",
    "data",
    "godzina",
    "datetime",
    "date_time",
    "submitted_at",
    "submission_time",
)


def _contains_datetime_token(value: str) -> bool:
    """Check whether one value has common datetime markers."""

    return bool(
        re.search(r"\d{1,4}[./:-]\d{1,2}[./:-]\d{1,4}", value)
        or re.search(r"\d{1,2}:\d{2}", value)
        or "t" in value.lower()
    )


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


def _looks_like_timestamp_series(series: pd.Series) -> bool:
    """Detect columns that mostly contain parseable timestamps."""

    non_null = series.dropna()
    if non_null.empty:
        return False

    text_values = non_null.astype(str).map(str.strip)
    text_values = text_values[text_values != ""]
    if text_values.empty:
        return False

    sample = text_values.head(20).astype(str)
    has_datetime_tokens = sample.map(_contains_datetime_token).mean()
    if float(has_datetime_tokens) < 0.4:
        return False

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        parsed = pd.to_datetime(text_values, errors="coerce", dayfirst=True, utc=False)
    parse_ratio = float(parsed.notna().mean())
    return parse_ratio >= 0.8


def _find_timestamp_columns(
    dataframe: pd.DataFrame, timestamp_patterns: Sequence[str] | None = None
) -> list[str]:
    """Return columns likely representing timestamps."""

    patterns = [
        normalize_column_name(pattern)
        for pattern in (timestamp_patterns or _DEFAULT_TIMESTAMP_PATTERNS)
        if str(pattern).strip()
    ]

    timestamp_columns: list[str] = []
    for column_name in dataframe.columns:
        normalized_name = normalize_column_name(str(column_name))
        matches_name = any(pattern in normalized_name for pattern in patterns)
        matches_values = _looks_like_timestamp_series(dataframe[column_name])
        if matches_name or matches_values:
            timestamp_columns.append(column_name)

    return timestamp_columns


def clean_dataframe(
    dataframe: pd.DataFrame,
    drop_timestamp_columns: bool = False,
    timestamp_patterns: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Normalize labels and missing values in a survey dataframe."""

    cleaned = dataframe.copy()

    if drop_timestamp_columns:
        timestamp_columns = _find_timestamp_columns(
            cleaned, timestamp_patterns=timestamp_patterns
        )
        if timestamp_columns:
            cleaned = cleaned.drop(columns=timestamp_columns)

    cleaned.columns = make_unique_columns([str(column) for column in cleaned.columns])

    for column in cleaned.columns:
        if (
            pd.api.types.is_string_dtype(cleaned[column])
            or cleaned[column].dtype == object
        ):
            cleaned[column] = cleaned[column].map(_normalize_cell_value)
    return cleaned


def _normalize_cell_value(value: object) -> object:
    """Normalize text cells while keeping non-string values unchanged."""

    if not isinstance(value, str):
        return value

    normalized = re.sub(r"\s+", " ", value.strip())
    if normalized == "":
        return pd.NA
    return normalized


def save_cleaned_csv(dataframe: pd.DataFrame, output_path: str | Path) -> Path:
    """Persist a cleaned dataframe to disk."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(path, index=False, encoding="utf-8-sig")
    return path
