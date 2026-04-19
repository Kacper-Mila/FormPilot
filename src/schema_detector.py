"""Survey schema detection for FormPilot.

Phase 3 responsibilities:
- classify each column into a survey-friendly field type,
- mark optional fields,
- export and reload schema JSON artifacts for downstream modules.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import pandas as pd
import json
import re


def _default_allowed_values() -> list[str]:
    return []


def _default_dependency_metadata() -> dict[str, Any]:
    return {}


class FieldType(str, Enum):
    """Supported survey field categories."""

    SINGLE_CHOICE = "single_choice"
    MULTI_SELECT = "multi_select"
    LIKERT_SCALE = "likert_scale"
    SHORT_TEXT = "short_text"
    LONG_TEXT = "long_text"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class SurveyQuestion:
    """Metadata for one survey question."""

    question_id: str
    column_name: str
    question_text: str
    field_type: FieldType
    allowed_values: list[str] = field(default_factory=_default_allowed_values)
    optional: bool = False
    dependency_metadata: dict[str, Any] = field(
        default_factory=_default_dependency_metadata
    )


@dataclass(slots=True)
class SurveySchema:
    """Container for all detected survey questions."""

    questions: list[SurveyQuestion]

    def to_dict(self) -> dict[str, Any]:
        return {
            "questions": [
                asdict(question) | {"field_type": question.field_type.value}
                for question in self.questions
            ]
        }


_MULTI_SELECT_SPLIT_PATTERN = re.compile(r"\s*(?:[;,|]|\s{2,})\s*")
_LIKERT_TOKEN_PATTERN = re.compile(
    r"^(?:"
    r"\d{1,2}"
    r"|zdecydowanie\s+nie"
    r"|raczej\s+nie"
    r"|ani\s+tak,?\s+ani\s+nie"
    r"|trudno\s+powiedziec"
    r"|neutral(?:ne|ny)?"
    r"|raczej\s+tak"
    r"|zdecydowanie\s+tak"
    r"|very\s+unlikely"
    r"|unlikely"
    r"|neutral"
    r"|likely"
    r"|very\s+likely"
    r")$",
    re.IGNORECASE,
)


def _split_multi_select_value(value: str) -> list[str]:
    """Split one encoded multi-select response into individual options."""

    if not value:
        return []
    return [token for token in _MULTI_SELECT_SPLIT_PATTERN.split(value) if token]


def _normalized_text_series(series: pd.Series) -> pd.Series:
    """Return lowercased, trimmed text values from non-null cells."""

    return series.dropna().astype(str).map(str.strip).map(str.casefold)


def _is_multi_select(non_null_text: pd.Series, unique_count: int) -> bool:
    """Detect encoded multi-select answers based on separators and diversity."""

    if non_null_text.empty:
        return False

    contains_separator_ratio = non_null_text.str.contains(r"[,;|]", regex=True).mean()
    if contains_separator_ratio < 0.2:
        return False

    tokenized = non_null_text.map(_split_multi_select_value)
    flat_tokens = [token for tokens in tokenized for token in tokens]
    if not flat_tokens:
        return False

    token_unique_count = len({token.casefold() for token in flat_tokens})
    return token_unique_count >= max(3, min(unique_count, 5))


def _is_likert_scale(series: pd.Series, non_null_text: pd.Series) -> bool:
    """Detect numeric or text-style Likert / scale fields."""

    if series.dropna().empty:
        return False

    if pd.api.types.is_numeric_dtype(series):
        numeric = pd.to_numeric(series.dropna(), errors="coerce").dropna()
        if numeric.empty:
            return False
        unique_values = sorted(set(numeric.astype(float).tolist()))
        if len(unique_values) < 3 or len(unique_values) > 11:
            return False
        min_value = min(unique_values)
        max_value = max(unique_values)
        return (max_value - min_value) <= 10

    if non_null_text.empty:
        return False

    likert_match_ratio = non_null_text.map(
        lambda value: bool(_LIKERT_TOKEN_PATTERN.match(str(value)))
    ).mean()
    return likert_match_ratio >= 0.75 and non_null_text.nunique() <= 11


def _is_single_choice(unique_count: int, non_null_count: int) -> bool:
    """Detect low-cardinality categorical fields."""

    if non_null_count == 0:
        return False
    if unique_count <= 1:
        return False
    return unique_count <= max(8, int(non_null_count * 0.2))


def _is_long_text(
    non_null_text: pd.Series, unique_count: int, non_null_count: int
) -> bool:
    """Detect free-text columns with long and diverse responses."""

    if non_null_text.empty:
        return False

    avg_length = non_null_text.str.len().mean()
    uniqueness_ratio = unique_count / max(non_null_count, 1)
    return avg_length >= 60 or (avg_length >= 35 and uniqueness_ratio >= 0.7)


def _extract_allowed_values(
    field_type: FieldType, non_null_text: pd.Series
) -> list[str]:
    """Build a compact set of allowed values for categorical fields."""

    if non_null_text.empty:
        return []

    if field_type == FieldType.MULTI_SELECT:
        token_set: set[str] = set()
        for value in non_null_text.tolist():
            token_set.update(_split_multi_select_value(value))
        return sorted(token_set)[:50]

    if field_type in {FieldType.SINGLE_CHOICE, FieldType.LIKERT_SCALE}:
        return [str(value) for value in non_null_text.drop_duplicates().tolist()[:50]]

    return []


def detect_schema(dataframe: pd.DataFrame) -> SurveySchema:
    """Infer a reusable survey schema from a cleaned dataframe."""

    questions: list[SurveyQuestion] = []
    total_rows = max(len(dataframe), 1)

    for index, column_name in enumerate(dataframe.columns, start=1):
        series = dataframe[column_name]
        non_null = series.dropna()
        non_null_text = non_null.astype(str).map(str.strip)
        unique_count = int(non_null_text.nunique())
        non_null_count = int(len(non_null_text))
        missing_ratio = 1 - (len(non_null) / total_rows)

        if _is_multi_select(non_null_text, unique_count):
            field_type = FieldType.MULTI_SELECT
        elif _is_likert_scale(series, _normalized_text_series(series)):
            field_type = FieldType.LIKERT_SCALE
        elif _is_single_choice(unique_count, non_null_count):
            field_type = FieldType.SINGLE_CHOICE
        elif _is_long_text(non_null_text, unique_count, non_null_count):
            field_type = FieldType.LONG_TEXT
        elif non_null_count > 0:
            field_type = FieldType.SHORT_TEXT
        else:
            field_type = FieldType.UNKNOWN

        allowed_values = _extract_allowed_values(field_type, non_null_text)

        questions.append(
            SurveyQuestion(
                question_id=f"q_{index}",
                column_name=column_name,
                question_text=column_name,
                field_type=field_type,
                allowed_values=allowed_values,
                optional=missing_ratio > 0,
                dependency_metadata={
                    "missing_ratio": round(float(missing_ratio), 6),
                    "non_null_count": non_null_count,
                    "unique_count": unique_count,
                },
            )
        )

    return SurveySchema(questions=questions)


def export_schema(schema: SurveySchema, output_path: str | Path) -> Path:
    """Write a schema export to JSON for debugging."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(schema.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def load_schema(schema_path: str | Path) -> SurveySchema:
    """Load a previously exported schema JSON artifact."""

    path = Path(schema_path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    questions_payload = payload.get("questions", [])
    questions: list[SurveyQuestion] = []
    for question in questions_payload:
        questions.append(
            SurveyQuestion(
                question_id=str(question["question_id"]),
                column_name=str(question["column_name"]),
                question_text=str(
                    question.get("question_text", question["column_name"])
                ),
                field_type=FieldType(str(question["field_type"])),
                allowed_values=[
                    str(value) for value in question.get("allowed_values", [])
                ],
                optional=bool(question.get("optional", False)),
                dependency_metadata=dict(question.get("dependency_metadata", {})),
            )
        )

    return SurveySchema(questions=questions)
