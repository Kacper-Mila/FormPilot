from __future__ import annotations

from src.probability_model import ProbabilityModel
from src.response_generator import ResponseGenerator
from src.schema_detector import FieldType, SurveyQuestion, SurveySchema


def test_response_generation_skips_inapplicable_conditional_followup():
    schema = SurveySchema(
        questions=[
            SurveyQuestion(
                question_id="q_1",
                column_name="wykształcenie",
                question_text="Wykształcenie",
                field_type=FieldType.SINGLE_CHOICE,
                allowed_values=["średnie", "wyższe"],
            ),
            SurveyQuestion(
                question_id="q_2",
                column_name="wyższe_jakie",
                question_text=(
                    "W przypadku zaznaczenia odpowiedzi wykształcenie wyższe."
                ),
                field_type=FieldType.SINGLE_CHOICE,
                allowed_values=["wyższe medyczne", "wyższe niemedyczne"],
                optional=True,
                dependency_metadata={
                    "missing_ratio": 0.0,
                    "conditional_on": {
                        "column_name": "wykształcenie",
                        "expected_values": ["wyższe"],
                    },
                },
            ),
        ]
    )
    model = ProbabilityModel(
        marginals={
            "wykształcenie": {"średnie": 1.0},
            "wyższe_jakie": {"wyższe medyczne": 1.0},
        }
    )

    response = ResponseGenerator(
        model, random_seed=1, schema=schema
    ).generate_response()

    assert response.answers["wykształcenie"] == "średnie"
    assert "wyższe_jakie" not in response.answers
    assert response.metadata["validation"]["is_valid"] is True


def test_required_answer_fallback_can_override_optional_skip():
    schema = SurveySchema(
        questions=[
            SurveyQuestion(
                question_id="q_1",
                column_name="wykształcenie",
                question_text="Wykształcenie",
                field_type=FieldType.SINGLE_CHOICE,
                allowed_values=["średnie", "wyższe"],
            ),
            SurveyQuestion(
                question_id="q_2",
                column_name="wyższe_jakie",
                question_text=(
                    "W przypadku zaznaczenia odpowiedzi wykształcenie wyższe."
                ),
                field_type=FieldType.SINGLE_CHOICE,
                allowed_values=["wyższe medyczne", "wyższe niemedyczne"],
                optional=True,
                dependency_metadata={
                    "missing_ratio": 1.0,
                    "conditional_on": {
                        "column_name": "wykształcenie",
                        "expected_values": ["wyższe"],
                    },
                },
            ),
        ]
    )
    model = ProbabilityModel(
        marginals={
            "wykształcenie": {"średnie": 1.0},
            "wyższe_jakie": {"wyższe medyczne": 1.0},
        }
    )
    generator = ResponseGenerator(model, random_seed=1, schema=schema)
    answers = {"wykształcenie": "średnie"}

    assert generator.generate_required_answer("wyższe_jakie", answers) == (
        "wyższe medyczne"
    )


def test_response_generation_represents_multiselect_as_list():
    schema = SurveySchema(
        questions=[
            SurveyQuestion(
                question_id="q_1",
                column_name="kanały",
                question_text="Kanały",
                field_type=FieldType.MULTI_SELECT,
                allowed_values=["TV", "radio", "internet"],
            )
        ]
    )
    model = ProbabilityModel(marginals={"kanały": {"TV, radio": 1.0}})

    response = ResponseGenerator(
        model, random_seed=1, schema=schema
    ).generate_response()

    assert response.answers["kanały"] == ["TV", "radio"]
