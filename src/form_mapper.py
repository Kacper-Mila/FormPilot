"""Form mapping module for FormPilot.

Phase 8 responsibilities:
- match CSV survey columns to Google Form questions,
- support fuzzy Polish text matching,
- map answer values to visible form options,
- generate a mapping table with confidence scores,
- flag unmatched or low-confidence mappings for manual review.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
import logging
from typing import Any

from rapidfuzz import fuzz

from schema_detector import FieldType, SurveySchema
from form_parser import FormQuestion
from logger import setup_logging

logger = setup_logging()


def _default_answer_mapping() -> dict[str, str]:
    """Default factory for answer mappings."""
    return {}


@dataclass(slots=True)
class MappingEntry:
    """Represents one matched pairing between a survey question and a form question."""

    dataset_question_id: str
    dataset_column_name: str
    dataset_question_text: str
    form_question_id: str
    form_question_text: str
    match_confidence: float
    answer_mapping: dict[str, str] = field(default_factory=_default_answer_mapping)
    notes: str = ""


@dataclass(slots=True)
class MappingTable:
    """Complete mapping of all survey questions to form questions."""

    mappings: list[MappingEntry]
    unmatched_survey_questions: list[str] = field(default_factory=list)
    unmatched_form_questions: list[str] = field(default_factory=list)
    low_confidence_threshold: float = 0.6

    def to_dict(self) -> dict[str, Any]:
        """Serialize mapping table to dict for JSON export."""
        return {
            "mappings": [asdict(m) for m in self.mappings],
            "unmatched_survey_questions": self.unmatched_survey_questions,
            "unmatched_form_questions": self.unmatched_form_questions,
            "low_confidence_threshold": self.low_confidence_threshold,
        }


def _normalize_for_matching(text: str) -> str:
    """Normalize text for fuzzy matching (lowercase, strip whitespace)."""
    return text.strip().casefold()


def _compute_text_similarity(text_a: str, text_b: str) -> float:
    """Compute similarity score between two strings using token set ratio."""
    norm_a = _normalize_for_matching(text_a)
    norm_b = _normalize_for_matching(text_b)

    if norm_a == norm_b:
        return 1.0

    # Use token set ratio for flexibility with word order
    score = fuzz.token_set_ratio(norm_a, norm_b) / 100.0
    return score


def _map_answer_values(
    dataset_allowed_values: list[str],
    form_options: list[str],
    field_type: FieldType,
) -> dict[str, str]:
    """
    Map dataset answer values to form option values.

    Returns:
        Dictionary mapping dataset values to form option values.
        Missing mappings are omitted.
    """
    if not dataset_allowed_values or not form_options:
        return {}

    mapping: dict[str, str] = {}

    for dataset_value in dataset_allowed_values:
        # Find best matching form option
        best_match = None
        best_score = 0.5  # Minimum threshold

        for form_option in form_options:
            score = _compute_text_similarity(dataset_value, form_option)
            if score > best_score:
                best_score = score
                best_match = form_option

        if best_match:
            mapping[dataset_value] = best_match

    return mapping


def match_survey_to_form(
    survey_schema: SurveySchema,
    form_questions: list[FormQuestion],
    min_confidence: float = 0.5,
) -> MappingTable:
    """
    Match all survey questions to form questions using fuzzy text matching.

    Uses a greedy bipartite matching algorithm to ensure each form question
    is matched to at most one survey question.

    Args:
        survey_schema: The detected survey schema from CSV data.
        form_questions: The list of questions parsed from the Google Form.
        min_confidence: Minimum confidence threshold for a match (0.0-1.0).
                       Matches below this threshold will still appear in the table
                       but will be flagged as low-confidence.

    Returns:
        A MappingTable with all matches, unmatched questions, and answer mappings.
    """
    logger.info(
        f"Starting to map {len(survey_schema.questions)} survey questions to {len(form_questions)} form questions."
    )

    # First, compute all pairwise similarity scores
    score_matrix: dict[tuple[str, str], float] = {}

    for survey_q in survey_schema.questions:
        for form_q in form_questions:
            # Compute similarity between question texts
            score = _compute_text_similarity(
                survey_q.question_text, form_q.visible_text
            )

            # Boost score if form field type matches survey field type
            type_match = _field_types_compatible(survey_q.field_type, form_q.field_type)
            if type_match:
                score = score * 1.1  # 10% boost for type compatibility

            score_matrix[(survey_q.question_id, form_q.form_question_id)] = score

    # Greedy bipartite matching: repeatedly find the best unmatched pair
    matched_survey_ids: set[str] = set()
    matched_form_ids: set[str] = set()
    mappings: list[MappingEntry] = []

    while True:
        # Find the best unmatched pair
        best_pair = None
        best_score = 0.0

        for (survey_id, form_id), score in score_matrix.items():
            if survey_id not in matched_survey_ids and form_id not in matched_form_ids:
                if score > best_score:
                    best_score = score
                    best_pair = (survey_id, form_id)

        if best_pair is None:
            break  # No more unmatched pairs

        survey_id, form_id = best_pair
        matched_survey_ids.add(survey_id)
        matched_form_ids.add(form_id)

        # Create the mapping entry
        survey_q = next(
            q for q in survey_schema.questions if q.question_id == survey_id
        )
        form_q = next(q for q in form_questions if q.form_question_id == form_id)

        answer_mapping = _map_answer_values(
            survey_q.allowed_values,
            form_q.options,
            survey_q.field_type,
        )

        notes = ""
        if best_score < min_confidence:
            notes += f"Low confidence match (score: {best_score:.2f}). "
        if survey_q.optional and form_q.required:
            notes += "Survey field is optional but form field is required. "
        if not answer_mapping and survey_q.allowed_values and form_q.options:
            notes += "No answer values could be mapped. "

        entry = MappingEntry(
            dataset_question_id=survey_q.question_id,
            dataset_column_name=survey_q.column_name,
            dataset_question_text=survey_q.question_text,
            form_question_id=form_q.form_question_id,
            form_question_text=form_q.visible_text,
            match_confidence=best_score,
            answer_mapping=answer_mapping,
            notes=notes.strip(),
        )

        logger.info(
            f"Matched '{survey_q.column_name}' → '{form_q.visible_text}' (Score: {best_score:.2f})"
        )
        if notes:
            logger.warning(f"Mapping flagged ({survey_q.column_name}): {notes.strip()}")

        mappings.append(entry)

    # Identify unmatched questions
    unmatched_survey_questions = [
        q.column_name
        for q in survey_schema.questions
        if q.question_id not in matched_survey_ids
    ]

    unmatched_form_questions = [
        q.visible_text
        for q in form_questions
        if q.form_question_id not in matched_form_ids
    ]

    if unmatched_survey_questions:
        logger.warning(
            f"Unmatched survey questions: {', '.join(unmatched_survey_questions)}"
        )
    if unmatched_form_questions:
        logger.warning(
            f"Unmatched form questions: {', '.join(unmatched_form_questions)}"
        )

    logger.info(
        f"Mapping complete. Created {len(mappings)} mappings. Unmatched: {len(unmatched_survey_questions)} survey, {len(unmatched_form_questions)} form questions."
    )

    # Sort mappings by the original form question order
    form_order = {q.form_question_id: i for i, q in enumerate(form_questions)}
    mappings.sort(key=lambda m: form_order.get(m.form_question_id, 9999))

    return MappingTable(
        mappings=mappings,
        unmatched_survey_questions=unmatched_survey_questions,
        unmatched_form_questions=unmatched_form_questions,
        low_confidence_threshold=min_confidence,
    )


def _field_types_compatible(survey_type: FieldType, form_type: str) -> bool:
    """
    Check if survey field type is compatible with form field type.

    Args:
        survey_type: FieldType from schema detection.
        form_type: Field type string from form parser (e.g., 'radio', 'checkbox', 'text').

    Returns:
        True if types are reasonably compatible.
    """
    # Normalize form field type
    form_type_lower = form_type.strip().casefold()

    if survey_type == FieldType.SINGLE_CHOICE:
        return form_type_lower in {"radio", "dropdown", "select"}

    if survey_type == FieldType.MULTI_SELECT:
        return form_type_lower in {"checkbox", "multi-select"}

    if survey_type == FieldType.LIKERT_SCALE:
        return form_type_lower in {"radio", "dropdown", "select", "scale"}

    if survey_type in {FieldType.SHORT_TEXT, FieldType.LONG_TEXT}:
        return form_type_lower in {"text", "short_text", "paragraph", "long_text"}

    return False


def export_mapping(mapping_table: MappingTable, output_path: str | Path) -> Path:
    """
    Write a mapping table export to JSON for review and validation.

    Args:
        mapping_table: The generated mapping table.
        output_path: Path to save the JSON file.

    Returns:
        The Path to the exported file.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Exporting complete mapping table to: {path}")
    path.write_text(
        json.dumps(mapping_table.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
