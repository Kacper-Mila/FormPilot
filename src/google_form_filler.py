"""Playwright form filling stubs for FormPilot."""

from __future__ import annotations

from dataclasses import dataclass

from form_mapper import MappingEntry
from response_generator import GeneratedResponse


@dataclass(slots=True)
class FillResult:
    """Outcome of one form-filling attempt."""

    success: bool
    message: str
    screenshot_path: str | None = None


class GoogleFormFiller:
    """Placeholder browser automation layer for Google Forms."""

    def fill_and_submit(
        self, form_url: str, response: GeneratedResponse, mappings: list[MappingEntry]
    ) -> FillResult:
        raise NotImplementedError(
            "Google Form automation is not implemented in the skeleton phase."
        )
