"""Persona helpers for FormPilot."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import random
from typing import Any


def _default_traits() -> dict[str, Any]:
    """Return an explicitly typed traits dictionary for dataclass defaults."""

    return {}


@dataclass(slots=True)
class Persona:
    """Simple respondent profile used to bias generation."""

    persona_id: str
    name: str
    description: str
    traits: dict[str, Any] = field(default_factory=_default_traits)


class PersonaGenerator:
    """Manage a small set of manual personas."""

    def __init__(self, personas: list[Persona] | None = None) -> None:
        self._personas = personas or self._build_default_personas()

    @staticmethod
    def _build_default_personas() -> list[Persona]:
        return [
            Persona(
                "persona_1",
                "Pragmatic Analyst",
                "Prefers consistent and moderate answers.",
                {"style": "stable"},
            ),
            Persona(
                "persona_2",
                "Fast Improviser",
                "Answers quickly and with more variation.",
                {"style": "varied"},
            ),
            Persona(
                "persona_3",
                "Careful Reviewer",
                "Often chooses neutral or cautious options.",
                {"style": "careful"},
            ),
        ]

    def list_personas(self) -> list[dict[str, Any]]:
        """Return personas as plain dictionaries for display or debugging."""

        return [asdict(persona) for persona in self._personas]

    def choose_persona(self, random_seed: int | None = None) -> Persona:
        """Select one persona at random."""

        generator = random.Random(random_seed)
        return generator.choice(self._personas)
