"""Form mapping module for FormPilot.

Phase 8 responsibilities:
- match CSV survey columns to Google Form questions,
- support fuzzy Polish text matching,
- map answer values to visible form options,
- generate a mapping table with confidence scores,
- flag unmatched or low-confidence mappings for manual review.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

from .form_parser import FormQuestion
from .logger import setup_logging
from .schema_detector import FieldType, SurveySchema

logger = setup_logging()

_POLISH_ASCII_MAP = str.maketrans(
    {
        "ą": "a",
        "ć": "c",
        "ę": "e",
        "ł": "l",
        "ń": "n",
        "ó": "o",
        "ś": "s",
        "ź": "z",
        "ż": "z",
    }
)


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
    accepted: bool = True
    form_required: bool = False


@dataclass(slots=True)
class MappingTable:
    """Complete mapping of all survey questions to form questions."""

    mappings: list[MappingEntry]
    unmatched_survey_questions: list[str] = field(default_factory=list)
    unmatched_form_questions: list[str] = field(default_factory=list)
    low_confidence_matches: list[dict[str, Any]] = field(default_factory=list)
    option_mapping_issues: list[dict[str, Any]] = field(default_factory=list)
    blocked_required_form_questions: list[str] = field(default_factory=list)
    low_confidence_threshold: float = 0.6
    allow_low_confidence: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize mapping table to dict for JSON export."""
        return {
            "mappings": [asdict(m) for m in self.mappings],
            "unmatched_survey_questions": self.unmatched_survey_questions,
            "unmatched_form_questions": self.unmatched_form_questions,
            "low_confidence_matches": self.low_confidence_matches,
            "option_mapping_issues": self.option_mapping_issues,
            "blocked_required_form_questions": self.blocked_required_form_questions,
            "low_confidence_threshold": self.low_confidence_threshold,
            "allow_low_confidence": self.allow_low_confidence,
            "submission_safe": self.is_submission_safe(),
        }

    def accepted_mappings(self) -> list[MappingEntry]:
        """Return mappings allowed for filling/submission."""

        return [mapping for mapping in self.mappings if mapping.accepted]

    def is_submission_safe(self) -> bool:
        """Return whether this mapping can be submitted without manual override."""

        return not self.blocked_required_form_questions and all(
            mapping.accepted for mapping in self.mappings
        )


_YES_NO_CANONICAL = {
    "tak": "yes",
    "yes": "yes",
    "y": "yes",
    "true": "yes",
    "nie": "no",
    "no": "no",
    "n": "no",
    "false": "no",
}


def _strip_diacritics(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.translate(_POLISH_ASCII_MAP))
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _normalize_for_matching(text: str) -> str:
    """Normalize text for fuzzy matching across schema and form wording."""

    normalized = _strip_diacritics(text).casefold().replace("_", " ")
    normalized = re.sub(r"[/\\|]+", " ", normalized)

    # CSV column normalization can collapse useful separators from Google Forms
    # labels. Restore the common merged tokens before fuzzy scoring.
    normalized = re.sub(r"(?<=mammografii)(?=usg\b)", " ", normalized)
    normalized = re.sub(r"(?<=mammografia)(?=usg\b)", " ", normalized)
    normalized = re.sub(r"(?<=widocznych)(?=wyczuwalnych\b)", " ", normalized)
    normalized = re.sub(r"(?<=pani)(?=pan(?:a)?\b)", " ", normalized)
    normalized = re.sub(r"(?<=pana)(?=pani\b)", " ", normalized)
    normalized = re.sub(
        r"\b([a-ząćęłńóśźż]+?ła)([a-ząćęłńóśźż]+?ł)\b",
        r"\1 \2",
        normalized,
    )

    normalized = re.sub(r"[^0-9a-z%]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def canonicalize_answer_option(value: str) -> str:
    """Return a conservative canonical form for option matching."""

    normalized = _strip_diacritics(value).casefold().strip()
    normalized = re.sub(
        r"\b(ok|około|okolo|about|approx|approximately|circa)\b",
        "",
        normalized,
    )
    normalized = normalized.replace(",", ".")
    compact = re.sub(r"\s+", "", normalized).strip(".:~")

    if compact in _YES_NO_CANONICAL:
        return f"bool:{_YES_NO_CANONICAL[compact]}"

    percent_match = re.fullmatch(r"(?:ok\.?)?(\d+(?:[.,]\d+)?)%", compact)
    if percent_match:
        number = float(percent_match.group(1).replace(",", "."))
        return f"percent:{number:g}"

    range_plus = re.fullmatch(r"(\d+)\+", compact)
    if range_plus:
        return f"range:{int(range_plus.group(1))}+"

    range_match = re.fullmatch(r"(\d+)[-–—](\d+)", compact)
    if range_match:
        lower = int(range_match.group(1))
        upper = int(range_match.group(2))
        if lower <= upper:
            return f"range:{lower}-{upper}"

    return f"text:{_normalize_for_matching(value)}"


def _compute_text_similarity(text_a: str, text_b: str) -> float:
    """Compute similarity score between two strings using token set ratio."""
    norm_a = _normalize_for_matching(text_a)
    norm_b = _normalize_for_matching(text_b)

    if norm_a == norm_b:
        return 1.0

    # Use token set ratio for flexibility with word order
    score = fuzz.token_set_ratio(norm_a, norm_b) / 100.0
    return min(1.0, max(0.0, float(score)))


def compute_option_similarity(text_a: str, text_b: str) -> float:
    """Score answer options, preferring exact canonical matches over fuzzy ones."""

    canonical_a = canonicalize_answer_option(text_a)
    canonical_b = canonicalize_answer_option(text_b)
    if canonical_a == canonical_b:
        return 1.0

    family_a = canonical_a.split(":", 1)[0]
    family_b = canonical_b.split(":", 1)[0]
    if family_a in {"bool", "range", "percent"} or family_b in {
        "bool",
        "range",
        "percent",
    }:
        return 0.0

    return _compute_text_similarity(text_a, text_b)


def _map_answer_values(
    dataset_allowed_values: list[str],
    form_options: list[str],
    field_type: FieldType,
    min_option_confidence: float = 0.72,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """
    Map dataset answer values to form option values.

    Returns:
        Dictionary mapping dataset values to form option values.
        Missing mappings are omitted.
    """
    if not dataset_allowed_values or not form_options:
        return {}, []

    mapping: dict[str, str] = {}
    issues: list[dict[str, Any]] = []

    for dataset_value in dataset_allowed_values:
        canonical_dataset = canonicalize_answer_option(dataset_value)
        exact_matches = [
            form_option
            for form_option in form_options
            if canonicalize_answer_option(form_option) == canonical_dataset
        ]
        if exact_matches:
            mapping[dataset_value] = exact_matches[0]
            continue

        best_match: str | None = None
        best_score = 0.0

        for form_option in form_options:
            score = compute_option_similarity(dataset_value, form_option)
            if score > best_score:
                best_score = score
                best_match = form_option

        if best_match and best_score >= min_option_confidence:
            mapping[dataset_value] = best_match
        else:
            issues.append(
                {
                    "dataset_value": dataset_value,
                    "canonical_dataset_value": canonical_dataset,
                    "best_form_option": best_match,
                    "best_score": round(float(best_score), 6),
                    "form_options": form_options,
                    "field_type": field_type.value,
                }
            )

    return mapping, issues


def match_survey_to_form(
    survey_schema: SurveySchema,
    form_questions: list[FormQuestion],
    min_confidence: float = 0.6,
    *,
    min_option_confidence: float = 0.72,
    allow_low_confidence: bool = False,
) -> MappingTable:
    """
    Match all survey questions to form questions using fuzzy text matching.

    Uses a greedy bipartite matching algorithm to ensure each form question
    is matched to at most one survey question.

    Args:
        survey_schema: The detected survey schema from CSV data.
        form_questions: The list of questions parsed from the Google Form.
        min_confidence: Minimum confidence threshold for a match (0.0-1.0).
                       Matches below this threshold are flagged and not accepted
                       unless allow_low_confidence=True.

    Returns:
        A MappingTable with all matches, unmatched questions, and answer mappings.
    """
    logger.info(
        "Starting to map %d survey questions to %d form questions.",
        len(survey_schema.questions),
        len(form_questions),
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
                score = min(1.0, score * 1.1)  # 10% boost for type compatibility

            score_matrix[(survey_q.question_id, form_q.form_question_id)] = score

    # Greedy bipartite matching: repeatedly find the best unmatched pair
    matched_survey_ids: set[str] = set()
    matched_form_ids: set[str] = set()
    mappings: list[MappingEntry] = []
    low_confidence_matches: list[dict[str, Any]] = []
    option_mapping_issues: list[dict[str, Any]] = []

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
        # Create the mapping entry
        survey_q = next(
            q for q in survey_schema.questions if q.question_id == survey_id
        )
        form_q = next(q for q in form_questions if q.form_question_id == form_id)

        accepted = best_score >= min_confidence or allow_low_confidence
        if not accepted:
            low_confidence_matches.append(
                {
                    "dataset_question_id": survey_q.question_id,
                    "dataset_column_name": survey_q.column_name,
                    "dataset_question_text": survey_q.question_text,
                    "form_question_id": form_q.form_question_id,
                    "form_question_text": form_q.visible_text,
                    "match_confidence": round(float(best_score), 6),
                }
            )
            # Do not consume either side; remove this pair and keep looking for
            # reliable alternatives.
            score_matrix.pop((survey_id, form_id), None)
            if not any(
                score >= min_confidence
                for (candidate_survey, candidate_form), score in score_matrix.items()
                if candidate_survey == survey_id
                and candidate_form not in matched_form_ids
            ):
                matched_survey_ids.add(survey_id)
            continue

        matched_survey_ids.add(survey_id)
        matched_form_ids.add(form_id)

        answer_mapping, answer_issues = _map_answer_values(
            survey_q.allowed_values,
            form_q.options,
            survey_q.field_type,
            min_option_confidence=min_option_confidence,
        )
        for issue in answer_issues:
            option_mapping_issues.append(
                {
                    "dataset_question_id": survey_q.question_id,
                    "dataset_column_name": survey_q.column_name,
                    "form_question_id": form_q.form_question_id,
                    "form_question_text": form_q.visible_text,
                    **issue,
                }
            )

        notes = ""
        if best_score < min_confidence:
            notes += f"Low confidence match (score: {best_score:.2f}). "
        if survey_q.optional and form_q.required:
            notes += "Survey field is optional but form field is required. "
        if not answer_mapping and survey_q.allowed_values and form_q.options:
            notes += "No answer values could be mapped. "
        elif answer_issues:
            notes += (
                f"{len(answer_issues)} answer value(s) need manual option review. "
            )

        entry = MappingEntry(
            dataset_question_id=survey_q.question_id,
            dataset_column_name=survey_q.column_name,
            dataset_question_text=survey_q.question_text,
            form_question_id=form_q.form_question_id,
            form_question_text=form_q.visible_text,
            match_confidence=min(1.0, max(0.0, float(best_score))),
            answer_mapping=answer_mapping,
            notes=notes.strip(),
            accepted=accepted,
            form_required=form_q.required,
        )

        logger.info(
            "Matched '%s' → '%s' (Score: %.2f)",
            survey_q.column_name,
            form_q.visible_text,
            best_score,
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
    blocked_required_form_questions = [
        q.visible_text
        for q in form_questions
        if q.required and q.form_question_id not in matched_form_ids
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
        "Mapping complete. Created %d mappings. Unmatched: %d survey, %d form "
        "questions.",
        len(mappings),
        len(unmatched_survey_questions),
        len(unmatched_form_questions),
    )

    # Sort mappings by the original form question order
    form_order = {q.form_question_id: i for i, q in enumerate(form_questions)}
    mappings.sort(key=lambda m: form_order.get(m.form_question_id, 9999))

    return MappingTable(
        mappings=mappings,
        unmatched_survey_questions=unmatched_survey_questions,
        unmatched_form_questions=unmatched_form_questions,
        low_confidence_matches=low_confidence_matches,
        option_mapping_issues=option_mapping_issues,
        blocked_required_form_questions=blocked_required_form_questions,
        low_confidence_threshold=min_confidence,
        allow_low_confidence=allow_low_confidence,
    )


def _field_types_compatible(survey_type: FieldType, form_type: str) -> bool:
    """
    Check if survey field type is compatible with form field type.

    Args:
        survey_type: FieldType from schema detection.
        form_type: Field type string from the form parser.

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
