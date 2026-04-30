from __future__ import annotations

import csv

from src.probability_model import ProbabilityModel
from src.response_generator import GeneratedResponse, ResponseGenerator
from src.submission_runner import SubmissionRunner


def test_generated_response_csv_uses_stable_model_columns(tmp_path):
    output_path = tmp_path / "generated.csv"
    generator = ResponseGenerator(
        ProbabilityModel(
            marginals={
                "wykształcenie": {"średnie": 0.5, "wyższe": 0.5},
                "wyższe_jakie": {"wyższe niemedyczne": 1.0},
            }
        )
    )
    runner = SubmissionRunner(
        response_generator=generator,
        form_filler=object(),  # type: ignore[arg-type]
        output_csv_path=output_path,
    )

    runner._save_response(
        GeneratedResponse(
            response_id="r1",
            persona_id=None,
            generated_at="2026-04-30T00:00:00+00:00",
            answers={"wykształcenie": "średnie"},
        )
    )
    runner._save_response(
        GeneratedResponse(
            response_id="r2",
            persona_id=None,
            generated_at="2026-04-30T00:00:01+00:00",
            answers={
                "wykształcenie": "wyższe",
                "wyższe_jakie": "wyższe niemedyczne",
            },
        )
    )

    with output_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert rows[0]["wyższe_jakie"] == ""
    assert rows[1]["wyższe_jakie"] == "wyższe niemedyczne"
