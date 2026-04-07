"""Survey schema detection for FormPilot."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import pandas as pd
import json


def _default_allowed_values() -> list[str]:
    return []


def _default_dependency_metadata() -> dict[str, Any]:
    return {}


class FieldType(str, Enum):
    """Supported survey field categories."""

    SINGLE_CHOICE = "single_choice"
    MULTI_CHOICE = "multi_choice"
    SCALE = "scale"
    TEXT = "text"
    OPTIONAL = "optional"
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


def detect_schema(dataframe: pd.DataFrame) -> SurveySchema:
    """Infer a lightweight survey schema from a dataframe."""

    questions: list[SurveyQuestion] = []
    total_rows = max(len(dataframe), 1)

    for index, column_name in enumerate(dataframe.columns, start=1):
        series = dataframe[column_name]
        non_null = series.dropna()
        unique_values = [str(value) for value in non_null.unique()[:25]]
        missing_ratio = 1 - (len(non_null) / total_rows)

        if series.dtype == object and non_null.astype(str).str.contains(r"[,;|]").any():
            field_type = FieldType.MULTI_CHOICE
        elif pd.api.types.is_numeric_dtype(series) and non_null.nunique() <= 10:
            field_type = FieldType.SCALE
        elif non_null.nunique() <= 6 and len(unique_values) > 0:
            field_type = FieldType.SINGLE_CHOICE
        elif series.dtype == object and non_null.nunique() > 6:
            field_type = FieldType.TEXT
        else:
            field_type = FieldType.UNKNOWN

        if missing_ratio > 0.3:
            field_type = (
                FieldType.OPTIONAL
                if field_type != FieldType.UNKNOWN
                else FieldType.OPTIONAL
            )

        questions.append(
            SurveyQuestion(
                question_id=f"q_{index}",
                column_name=column_name,
                question_text=column_name,
                field_type=field_type,
                allowed_values=unique_values,
                optional=missing_ratio > 0.0,
                dependency_metadata={"missing_ratio": missing_ratio},
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
