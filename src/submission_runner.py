"""Submission orchestration for FormPilot."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from form_mapper import MappingEntry
from google_form_filler import FillResult, GoogleFormFiller
from response_generator import GeneratedResponse, ResponseGenerator
from logger import setup_logging

logger = setup_logging()


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
        self,
        response_generator: ResponseGenerator,
        form_filler: GoogleFormFiller,
        output_csv_path: str | Path | None = None,
        stop_on_error: bool = False,
    ) -> None:
        self.response_generator = response_generator
        self.form_filler = form_filler
        self.output_csv_path = Path(output_csv_path) if output_csv_path else None
        self.stop_on_error = stop_on_error

    def _save_response(self, response: GeneratedResponse) -> None:
        """Save a generated response to the local CSV file."""
        if not self.output_csv_path:
            return

        self.output_csv_path.parent.mkdir(parents=True, exist_ok=True)
        file_exists = self.output_csv_path.exists()

        try:
            with self.output_csv_path.open("a", encoding="utf-8", newline="") as f:
                # Determine fieldnames from the generated response answers
                fieldnames = ["response_id", "persona_id", "generated_at"] + list(
                    response.answers.keys()
                )
                writer = csv.DictWriter(f, fieldnames=fieldnames)

                if not file_exists:
                    writer.writeheader()

                row_data = {
                    "response_id": response.response_id,
                    "persona_id": response.persona_id or "",
                    "generated_at": response.generated_at,
                }
                row_data.update(response.answers)
                writer.writerow(row_data)
        except Exception as e:
            logger.error(
                "Failed to save response %s to CSV: %s", response.response_id, e
            )

    def run(
        self, form_url: str, count: int, mappings: list[MappingEntry]
    ) -> list[SubmissionRun]:
        """Generate, fill and map count times."""
        results: list[SubmissionRun] = []
        with self.form_filler:
            for i in range(count):
                logger.info("Starting run %d of %d", i + 1, count)

                try:
                    response = self.response_generator.generate_response()
                    logger.info("Generated response ID: %s", response.response_id)

                    # Save generated row locally for traceability
                    self._save_response(response)

                    result = self.form_filler.fill_and_submit(
                        form_url, response, mappings
                    )
                    results.append(SubmissionRun(response=response, fill_result=result))

                    if not result.success:
                        logger.error("Run %d failed: %s", i + 1, result.message)
                        if self.stop_on_error:
                            logger.warning("Stopping early due to stop_on_error=True")
                            break
                    else:
                        logger.info("Run %d succeeded.", i + 1)

                except Exception as e:
                    logger.exception("Unexpected error during run %d: %s", i + 1, e)
                    if self.stop_on_error:
                        logger.warning(
                            "Stopping early due to fatal error and stop_on_error=True"
                        )
                        break

        return results
