"""Synthetic response generation for FormPilot."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from uuid import uuid4
import random
from typing import Any

from probability_model import ProbabilityModel
from persona_generator import Persona


def _default_metadata() -> dict[str, Any]:
    return {}


@dataclass(slots=True)
class GeneratedResponse:
    """One generated survey response."""

    response_id: str
    persona_id: str | None
    answers: dict[str, Any]
    generated_at: str
    metadata: dict[str, Any] = field(default_factory=_default_metadata)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ResponseGenerator:
    """Generate a single synthetic respondent from a learned model."""

    def __init__(
        self, model: ProbabilityModel | None = None, random_seed: int | None = None
    ) -> None:
        self.model = model or ProbabilityModel()
        self.random = random.Random(random_seed)

    def generate_response(self, persona: Persona | None = None) -> GeneratedResponse:
        """Create one response using marginal probabilities when available."""

        answers: dict[str, Any] = {}
        for column_name, value_distribution in self.model.marginals.items():
            values = list(value_distribution.keys())
            weights = list(value_distribution.values())
            answers[column_name] = self.random.choices(values, weights=weights, k=1)[0]

        return GeneratedResponse(
            response_id=str(uuid4()),
            persona_id=persona.persona_id if persona else None,
            answers=answers,
            generated_at=datetime.now(timezone.utc).isoformat(),
            metadata={"persona": persona.name if persona else None},
        )
