from __future__ import annotations

from src.form_mapper import (
    canonicalize_answer_option,
    compute_option_similarity,
    match_survey_to_form,
)
from src.form_parser import FormQuestion
from src.schema_detector import FieldType, SurveyQuestion, SurveySchema


def test_option_matching_canonicalizes_polish_english_yes_no_and_percentages():
    assert canonicalize_answer_option("Tak") == canonicalize_answer_option("yes")
    assert canonicalize_answer_option("Nie") == canonicalize_answer_option("no")
    assert canonicalize_answer_option("ok. 45%") == canonicalize_answer_option(
        "about 45%"
    )
    assert compute_option_similarity("tak", "Yes") == 1.0
    assert compute_option_similarity("ok. 45%", "45%") == 1.0


def test_option_matching_does_not_confuse_open_ended_ranges():
    assert canonicalize_answer_option("75+") != canonicalize_answer_option("66-75")
    assert compute_option_similarity("75+", "66-75") == 0.0


def test_mapping_rejects_low_confidence_required_fields_by_default():
    schema = SurveySchema(
        questions=[
            SurveyQuestion(
                question_id="q_1",
                column_name="wiek",
                question_text="Wiek",
                field_type=FieldType.SINGLE_CHOICE,
                allowed_values=["18-24", "75+"],
            )
        ]
    )
    form_questions = [
        FormQuestion(
            form_question_id="form_q_1",
            visible_text="Ulubiony kolor",
            field_type="radio",
            options=["czerwony", "niebieski"],
            required=True,
        )
    ]

    mapping = match_survey_to_form(schema, form_questions, min_confidence=0.8)

    assert mapping.mappings == []
    assert mapping.blocked_required_form_questions == ["Ulubiony kolor"]
    assert not mapping.is_submission_safe()


def test_mapping_caps_confidence_and_prefers_canonical_option_matches():
    schema = SurveySchema(
        questions=[
            SurveyQuestion(
                question_id="q_1",
                column_name="wiek",
                question_text="Wiek respondenta",
                field_type=FieldType.SINGLE_CHOICE,
                allowed_values=["66-75", "75+"],
            )
        ]
    )
    form_questions = [
        FormQuestion(
            form_question_id="form_q_1",
            visible_text="Wiek respondenta",
            field_type="radio",
            options=["66-75", "75+"],
            required=True,
        )
    ]

    mapping = match_survey_to_form(schema, form_questions)

    assert mapping.mappings[0].match_confidence == 1.0
    assert mapping.mappings[0].answer_mapping == {"66-75": "66-75", "75+": "75+"}
    assert mapping.is_submission_safe()

