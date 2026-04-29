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
        retry_failed_submissions: bool = False,
        max_submission_retries: int = 0,
    ) -> None:
        self.response_generator = response_generator
        self.form_filler = form_filler
        self.output_csv_path = Path(output_csv_path) if output_csv_path else None
        self.stop_on_error = stop_on_error
        self.retry_failed_submissions = retry_failed_submissions
        self.max_submission_retries = max(0, int(max_submission_retries))

    def _clear_output_csv(self) -> None:
        """Clear generated responses from previous submission batches."""
        if not self.output_csv_path:
            return

        try:
            self.output_csv_path.parent.mkdir(parents=True, exist_ok=True)
            self.output_csv_path.write_text("", encoding="utf-8")
            logger.info("Cleared generated responses CSV: %s", self.output_csv_path)
        except Exception as e:
            logger.error("Failed to clear generated responses CSV: %s", e)

    def _save_response(self, response: GeneratedResponse) -> None:
        """Save a generated response to the local CSV file."""
        if not self.output_csv_path:
            return

        self.output_csv_path.parent.mkdir(parents=True, exist_ok=True)
        file_exists = self.output_csv_path.exists()
        file_is_empty = not file_exists or self.output_csv_path.stat().st_size == 0

        try:
            with self.output_csv_path.open("a", encoding="utf-8", newline="") as f:
                # Determine fieldnames from the generated response answers
                fieldnames = ["response_id", "persona_id", "generated_at"] + list(
                    response.answers.keys()
                )
                writer = csv.DictWriter(f, fieldnames=fieldnames)

                if file_is_empty:
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

    def _submit_with_retries(
        self, form_url: str, response: GeneratedResponse, mappings: list[MappingEntry]
    ) -> SubmissionRun:
        """Submit one generated response, retrying failed fill attempts if enabled."""

        attempts_allowed = 1
        if self.retry_failed_submissions:
            attempts_allowed += self.max_submission_retries

        fill_result: FillResult | None = None
        for attempt in range(1, attempts_allowed + 1):
            if attempt > 1:
                logger.info(
                    "Retrying response %s (attempt %d of %d)",
                    response.response_id,
                    attempt,
                    attempts_allowed,
                )

            try:
                fill_result = self.form_filler.fill_and_submit(
                    form_url, response, mappings
                )
            except Exception as e:
                logger.exception(
                    "Submission attempt %d of %d raised for response %s: %s",
                    attempt,
                    attempts_allowed,
                    response.response_id,
                    e,
                )
                fill_result = FillResult(success=False, message=str(e))

            if fill_result.success:
                return SubmissionRun(
                    response=response,
                    fill_result=fill_result,
                    metadata={"attempts": attempt},
                )

            logger.error(
                "Submission attempt %d of %d failed for response %s: %s",
                attempt,
                attempts_allowed,
                response.response_id,
                fill_result.message,
            )

        if fill_result is None:
            raise RuntimeError("Submission did not produce a fill result.")

        return SubmissionRun(
            response=response,
            fill_result=fill_result,
            metadata={"attempts": attempts_allowed},
        )

    def run(
        self, form_url: str, count: int, mappings: list[MappingEntry]
    ) -> list[SubmissionRun]:
        """Generate, fill and map count times."""
        results: list[SubmissionRun] = []
        self._clear_output_csv()
        with self.form_filler:
            for i in range(count):
                logger.info("Starting run %d of %d", i + 1, count)

                try:
                    response = self.response_generator.generate_response()
                    logger.info("Generated response ID: %s", response.response_id)

                    # Save generated row locally for traceability
                    self._save_response(response)

                    run_result = self._submit_with_retries(
                        form_url, response, mappings
                    )
                    results.append(run_result)
                    result = run_result.fill_result

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
