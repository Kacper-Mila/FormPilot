"""Submission orchestration for FormPilot."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from google_form_filler import FillResult, GoogleFormFiller
from response_generator import GeneratedResponse, ResponseGenerator


def _default_metadata() -> dict[str, Any]:
    return {}


@dataclass(slots=True)
class SubmissionRun:
    """One attempt to generate and submit a response."""

    response: GeneratedResponse
    fill_result: FillResult
    metadata: dict[str, Any] = field(default_factory=_default_metadata)


class SubmissionRunner:
    """Runner that will coordinate generation and submission."""

    def __init__(
        self, response_generator: ResponseGenerator, form_filler: GoogleFormFiller
    ) -> None:
        self.response_generator = response_generator
        self.form_filler = form_filler

    def run(
        self, form_url: str, count: int, mappings: list[Any]
    ) -> list[SubmissionRun]:
        """Generate, fill and map count times."""
        import logging

        logger = logging.getLogger(__name__)
        results = []
        for i in range(count):
            logger.info("Starting run %d of %d", i + 1, count)
            response = self.response_generator.generate_response()
            result = self.form_filler.fill_and_submit(form_url, response, mappings)
            results.append(SubmissionRun(response=response, fill_result=result))

        return results
