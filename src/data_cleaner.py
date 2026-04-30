"""Data cleaning utilities for FormPilot."""

from __future__ import annotations

import re
import warnings
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

_DEFAULT_TIMESTAMP_PATTERNS: tuple[str, ...] = (
    "timestamp",
    "time_stamp",
    "sygnatura_czasowa",
    "sygnatura czasowa",
    "data",
    "godzina",
    "datetime",
    "date_time",
    "submitted_at",
    "submission_time",
)


@dataclass(frozen=True, slots=True)
class ColumnMetadata:
    """Relationship between the stable cleaned id and source CSV header."""

    column_id: str
    original_text: str


def _contains_datetime_token(value: str) -> bool:
    """Check whether one value has common datetime markers."""

    stripped = value.strip()
    return bool(
        re.search(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b", stripped)
        or re.search(r"\b\d{4}[./-]\d{1,2}[./-]\d{1,2}\b", stripped)
        or re.search(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", stripped)
        or re.search(r"\b\d{4}-\d{2}-\d{2}t\d{2}:\d{2}", stripped.casefold())
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


def build_column_metadata(original_columns: Sequence[str]) -> list[ColumnMetadata]:
    """Build stable column ids while retaining the original question wording."""

    column_ids = make_unique_columns([str(column) for column in original_columns])
    return [
        ColumnMetadata(column_id=column_id, original_text=str(original_text))
        for column_id, original_text in zip(column_ids, original_columns, strict=True)
    ]


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

    parse_ratios: list[float] = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        for dayfirst in (True, False):
            parsed = pd.to_datetime(
                text_values, errors="coerce", dayfirst=dayfirst, utc=False
            )
            parse_ratios.append(float(parsed.notna().mean()))
    parse_ratio = max(parse_ratios, default=0.0)
    return parse_ratio >= 0.8


def find_timestamp_columns(
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


def _column_metadata_attr(metadata: list[ColumnMetadata]) -> dict[str, dict[str, str]]:
    """Return JSON-friendly metadata stored on cleaned dataframe attrs."""

    return {item.column_id: asdict(item) for item in metadata}


def clean_dataframe(
    dataframe: pd.DataFrame,
    drop_timestamp_columns: bool = False,
    timestamp_patterns: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Normalize labels and missing values in a survey dataframe."""

    cleaned = dataframe.copy()

    if drop_timestamp_columns:
        timestamp_columns = find_timestamp_columns(
            cleaned, timestamp_patterns=timestamp_patterns
        )
        if timestamp_columns:
            cleaned = cleaned.drop(columns=timestamp_columns)

    metadata = build_column_metadata([str(column) for column in cleaned.columns])
    cleaned.columns = [item.column_id for item in metadata]
    cleaned.attrs["column_metadata"] = _column_metadata_attr(metadata)
    cleaned.attrs["original_columns"] = {
        item.column_id: item.original_text for item in metadata
    }

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
