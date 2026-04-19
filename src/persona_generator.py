"""Persona helpers for FormPilot."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
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
    weight: float = 1.0
    value_biases: dict[str, float] = field(default_factory=_default_traits)
    keyword_biases: dict[str, float] = field(default_factory=_default_traits)
    traits: dict[str, Any] = field(default_factory=_default_traits)


class PersonaGenerator:
    """Manage a small set of manual personas."""

    def __init__(
        self, personas: list[Persona] | None = None, random_seed: int | None = None
    ) -> None:
        self._personas = personas or self._build_default_personas()
        self._random = random.Random(random_seed)

    @staticmethod
    def _build_default_personas() -> list[Persona]:
        return [
            Persona(
                "persona_1",
                "Pragmatyczny Analityk",
                "Preferuje wywazone odpowiedzi i umiarkowana zmiennosc.",
                weight=0.45,
                value_biases={
                    "tak": 1.1,
                    "nie": 0.9,
                    "3": 1.2,
                    "4": 1.15,
                    "5": 1.05,
                },
                keyword_biases={
                    "raczej": 1.15,
                    "umiark": 1.2,
                    "sred": 1.2,
                    "czasami": 1.1,
                },
                traits={"style": "stable", "risk": "medium"},
            ),
            Persona(
                "persona_2",
                "Entuzjastyczny Uczestnik",
                "Czesciej wybiera odpowiedzi pozytywne i zdecydowane.",
                weight=0.35,
                value_biases={
                    "tak": 1.3,
                    "nie": 0.75,
                    "4": 1.25,
                    "5": 1.35,
                },
                keyword_biases={
                    "zdecydowanie": 1.3,
                    "bardzo": 1.25,
                    "polecam": 1.3,
                    "czesto": 1.2,
                },
                traits={"style": "positive", "risk": "high"},
            ),
            Persona(
                "persona_3",
                "Ostrozny Recenzent",
                "Preferuje odpowiedzi neutralne, ostrozne i mniej skrajne.",
                weight=0.20,
                value_biases={
                    "nie": 1.15,
                    "tak": 0.85,
                    "2": 1.15,
                    "3": 1.3,
                    "5": 0.8,
                },
                keyword_biases={
                    "neutral": 1.35,
                    "trudno": 1.35,
                    "nie wiem": 1.4,
                    "czasami": 1.2,
                },
                traits={"style": "careful", "risk": "low"},
            ),
        ]

    def list_personas(self) -> list[dict[str, Any]]:
        """Return personas as plain dictionaries for display or debugging."""

        return [asdict(persona) for persona in self._personas]

    def choose_persona(
        self, weighted: bool = True, random_seed: int | None = None
    ) -> Persona:
        """Select one persona randomly, optionally using persona weights."""

        generator = (
            random.Random(random_seed) if random_seed is not None else self._random
        )
        if not weighted:
            return generator.choice(self._personas)

        normalized_weights = [max(0.0, persona.weight) for persona in self._personas]
        total_weight = sum(normalized_weights)
        if math.isclose(total_weight, 0.0):
            return generator.choice(self._personas)

        return generator.choices(self._personas, weights=normalized_weights, k=1)[0]

    def build_persona_adjusted_weights(
        self,
        persona: Persona,
        options: list[str],
        base_weights: list[float],
    ) -> list[float]:
        """Apply persona-specific multipliers to a base distribution."""

        adjusted: list[float] = []
        for index, option in enumerate(options):
            base_weight = float(base_weights[index])
            normalized_option = option.strip().lower()

            multiplier = 1.0
            if normalized_option in persona.value_biases:
                multiplier *= max(0.0, float(persona.value_biases[normalized_option]))

            for keyword, keyword_multiplier in persona.keyword_biases.items():
                normalized_keyword = keyword.strip().lower()
                if normalized_keyword and normalized_keyword in normalized_option:
                    multiplier *= max(0.0, float(keyword_multiplier))

            adjusted.append(base_weight * multiplier)

        if any(weight > 0 for weight in adjusted):
            return adjusted
        return base_weights
