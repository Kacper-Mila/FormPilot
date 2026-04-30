from __future__ import annotations

import pandas as pd

from src.data_cleaner import clean_dataframe, find_timestamp_columns
from src.data_loader import load_csv
from src.probability_model import build_probability_model
from src.schema_detector import FieldType, detect_schema


def test_load_csv_detects_semicolon_and_polish_text(tmp_path):
    csv_path = tmp_path / "survey.csv"
    csv_path.write_text("Płeć;Wiek\nkobieta;18-24\n", encoding="utf-8")

    dataframe = load_csv(csv_path)

    assert list(dataframe.columns) == ["Płeć", "Wiek"]
    assert dataframe.loc[0, "Płeć"] == "kobieta"


def test_clean_dataframe_preserves_original_headers_and_drops_timestamp():
    dataframe = pd.DataFrame(
        {
            "Sygnatura czasowa": ["2/11/2026 21:09:21", "2/17/2026 18:10:10"],
            "Płeć": [" kobieta ", "mężczyzna"],
            "Wiek": ["18-24", "25-34"],
        }
    )

    cleaned = clean_dataframe(dataframe, drop_timestamp_columns=True)

    assert "sygnatura_czasowa" not in cleaned.columns
    assert list(cleaned.columns) == ["płeć", "wiek"]
    assert cleaned.attrs["column_metadata"]["płeć"]["original_text"] == "Płeć"
    assert cleaned.loc[0, "płeć"] == "kobieta"


def test_timestamp_detection_supports_polish_labels_and_us_dates():
    dataframe = pd.DataFrame(
        {
            "Sygnatura czasowa": ["2/11/2026 21:09:21", "2/17/2026 18:10:10"],
            "godzina": ["21:09:21", "18:10:10"],
            "Wiek": ["18-24", "25-34"],
        }
    )

    assert find_timestamp_columns(dataframe) == ["Sygnatura czasowa", "godzina"]


def test_schema_uses_original_question_text_and_detects_multiselect():
    dataframe = pd.DataFrame(
        {
            "Które kanały?": ["TV, radio", "radio; internet", "TV, internet"],
            "Komentarz": ["krótko", "trochę dłuższy komentarz", "ok"],
        }
    )
    cleaned = clean_dataframe(dataframe)

    schema = detect_schema(cleaned)

    channels = schema.questions[0]
    assert channels.column_name == "które_kanały"
    assert channels.question_text == "Które kanały?"
    assert channels.field_type == FieldType.MULTI_SELECT
    assert set(channels.allowed_values) == {"TV", "radio", "internet"}


def test_schema_detects_polish_conditional_followup_with_diacritics():
    dataframe = pd.DataFrame(
        {
            "Wykształcenie": ["średnie", "wyższe", "wyższe"],
            "W przypadku zaznaczenia odpowiedzi wykształcenie wyższe.": [
                None,
                "wyższe medyczne",
                "wyższe niemedyczne",
            ],
        }
    )
    cleaned = clean_dataframe(dataframe)

    followup = detect_schema(cleaned).questions[1]

    assert followup.dependency_metadata["conditional_on"] == {
        "question_id": "q_1",
        "column_name": "wykształcenie",
        "expected_values": ["wyższe", "wyzsze", "higher", "university"],
    }


def test_probability_model_builds_marginals_and_dependencies():
    dataframe = pd.DataFrame(
        {
            "education": ["higher", "higher", "secondary", "secondary"] * 5,
            "followup": ["medical", "non-medical", "skip", "skip"] * 5,
        }
    )

    model = build_probability_model(dataframe, min_support_rows=2)

    assert model.marginals["education"]["higher"] == 0.5
    assert "followup" in model.dependencies


def test_probability_model_lowercases_answers_before_calculation():
    dataframe = pd.DataFrame(
        {
            "reason": ["Strach", "strach", "BRAK CZASU", "brak czasu"],
            "followup": ["TAK", "tak", "Nie", "nie"],
        }
    )

    model = build_probability_model(dataframe, min_support_rows=2)

    assert model.marginals["reason"] == {
        "strach": 0.5,
        "brak czasu": 0.5,
    }
    assert model.marginals["followup"] == {
        "tak": 0.5,
        "nie": 0.5,
    }
