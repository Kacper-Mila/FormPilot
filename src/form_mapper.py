"""Mapping helpers between survey schema and Google Forms."""

from __future__ import annotations

from dataclasses import dataclass, field

from form_parser import FormQuestion
from schema_detector import SurveyQuestion


def _default_answer_mapping_table() -> dict[str, str]:
    return {}


@dataclass(slots=True)
class MappingEntry:
    """Mapping between a dataset question and a form question."""

    dataset_question_id: str
    form_question_id: str
    match_confidence: float
    answer_mapping_table: dict[str, str] = field(
        default_factory=_default_answer_mapping_table
    )


class FormMapper:
    """Placeholder mapper used until fuzzy matching is implemented."""

    def map_questions(
        self, survey_questions: list[SurveyQuestion], form_questions: list[FormQuestion]
    ) -> list[MappingEntry]:
        raise NotImplementedError(
            "Form mapping is not implemented in the skeleton phase."
        )
