"""Google Form parsing stubs for FormPilot."""

from __future__ import annotations

from dataclasses import dataclass, field


def _default_options() -> list[str]:
    return []


@dataclass(slots=True)
class FormQuestion:
    """Representation of one visible Google Form question."""

    form_question_id: str
    visible_text: str
    field_type: str
    options: list[str] = field(default_factory=_default_options)
    page_index: int = 0
    required: bool = False


class GoogleFormParser:
    """Placeholder parser for Google Form question extraction."""

    def parse(self, form_url: str) -> list[FormQuestion]:
        raise NotImplementedError(
            "Google Form parsing is not implemented in the skeleton phase."
        )
