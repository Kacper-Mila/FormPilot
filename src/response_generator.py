"""Synthetic response generation for FormPilot."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import csv
import json
import random
from typing import Any

from probability_model import ProbabilityModel
from persona_generator import Persona, PersonaGenerator


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
    """Generate synthetic respondents from marginals and dependencies."""

    def __init__(
        self,
        model: ProbabilityModel | None = None,
        random_seed: int | None = None,
        persona_generator: PersonaGenerator | None = None,
        exploration_rate: float = 0.1,
        conditional_strength: float = 0.8,
        temperature: float = 0.95,
        duplicate_retry_limit: int = 10,
    ) -> None:
        self.model = model or ProbabilityModel()
        self.random = random.Random(random_seed)
        self.persona_generator = persona_generator or PersonaGenerator(
            random_seed=random_seed
        )
        self.exploration_rate = max(0.0, min(1.0, float(exploration_rate)))
        self.conditional_strength = max(0.0, min(1.0, float(conditional_strength)))
        self.temperature = max(0.05, float(temperature))
        self.duplicate_retry_limit = max(1, int(duplicate_retry_limit))
        self._seen_signatures: set[tuple[tuple[str, str], ...]] = set()

    def _sample_distribution(
        self,
        distribution: dict[str, float],
        persona: Persona,
    ) -> str:
        values = list(distribution.keys())
        weights = [max(0.0, float(weight)) for weight in distribution.values()]
        if not values:
            return ""

        normalized_options = [str(value).strip().lower() for value in values]
        adjusted = self.persona_generator.build_persona_adjusted_weights(
            persona=persona,
            options=normalized_options,
            base_weights=weights,
        )

        softened = [
            pow(weight, 1.0 / self.temperature) if weight > 0 else 0.0
            for weight in adjusted
        ]
        if not any(weight > 0 for weight in softened):
            softened = [1.0 for _ in values]

        return str(self.random.choices(values, weights=softened, k=1)[0])

    @staticmethod
    def _mix_distributions(
        marginal: dict[str, float],
        conditional: dict[str, float],
        conditional_strength: float,
    ) -> dict[str, float]:
        all_values = set(marginal.keys()) | set(conditional.keys())
        if not all_values:
            return {}

        mixed: dict[str, float] = {}
        for value in all_values:
            marginal_weight = float(marginal.get(value, 0.0))
            conditional_weight = float(conditional.get(value, 0.0))
            weight = (1.0 - conditional_strength) * marginal_weight + (
                conditional_strength * conditional_weight
            )
            mixed[str(value)] = max(0.0, weight)

        total = sum(mixed.values())
        if total <= 0:
            uniform_weight = 1.0 / len(all_values)
            return {str(value): uniform_weight for value in all_values}

        return {value: (weight / total) for value, weight in mixed.items()}

    @staticmethod
    def _signature_for_answers(answers: dict[str, Any]) -> tuple[tuple[str, str], ...]:
        return tuple(
            sorted((str(column), str(value)) for column, value in answers.items())
        )

    def _dependency_parent_priority(self, target_column: str) -> list[str]:
        rules = self.model.dependency_rules.get(target_column, [])
        if rules:
            return [
                str(rule.get("parent_column"))
                for rule in rules
                if str(rule.get("parent_column", "")).strip()
            ]
        return list(self.model.dependencies.get(target_column, {}).keys())

    def _sample_for_column(
        self, column_name: str, persona: Persona, answers: dict[str, Any]
    ) -> str:
        marginal = self.model.marginals.get(column_name, {})
        if not marginal:
            return ""

        if self.random.random() < self.exploration_rate:
            return self._sample_distribution(marginal, persona)

        dependencies_for_target = self.model.dependencies.get(column_name, {})
        for parent_column in self._dependency_parent_priority(column_name):
            parent_value = answers.get(parent_column)
            if parent_value is None:
                continue

            parent_map = dependencies_for_target.get(parent_column, {})
            conditional = parent_map.get(str(parent_value), {})
            if not conditional:
                continue

            mixed = self._mix_distributions(
                marginal=marginal,
                conditional=conditional,
                conditional_strength=self.conditional_strength,
            )
            return self._sample_distribution(mixed, persona)

        return self._sample_distribution(marginal, persona)

    def _ordered_columns(self) -> tuple[list[str], list[str]]:
        all_columns = list(self.model.marginals.keys())
        dependent_targets = set(self.model.dependencies.keys())
        anchor_columns = [
            column for column in all_columns if column not in dependent_targets
        ]
        dependent_columns = [
            column for column in all_columns if column in dependent_targets
        ]
        return anchor_columns, dependent_columns

    @staticmethod
    def _validate_answers(answers: dict[str, Any]) -> tuple[bool, list[str]]:
        issues: list[str] = []
        if not answers:
            issues.append("generated response is empty")
            return False, issues

        for column, value in answers.items():
            if value is None:
                issues.append(f"column '{column}' has missing value")
                continue
            if isinstance(value, str) and value.strip() == "":
                issues.append(f"column '{column}' has blank value")
        return len(issues) == 0, issues

    def _generate_candidate(self, persona: Persona) -> dict[str, Any]:
        answers: dict[str, Any] = {}
        anchor_columns, dependent_columns = self._ordered_columns()

        for column_name in anchor_columns:
            answers[column_name] = self._sample_for_column(
                column_name=column_name,
                persona=persona,
                answers=answers,
            )

        pending = set(dependent_columns)
        max_passes = max(1, len(pending) + 1)
        for _ in range(max_passes):
            if not pending:
                break

            generated_this_pass: list[str] = []
            for column_name in list(pending):
                parent_priority = self._dependency_parent_priority(column_name)
                if parent_priority and not any(
                    parent in answers for parent in parent_priority
                ):
                    continue

                answers[column_name] = self._sample_for_column(
                    column_name=column_name,
                    persona=persona,
                    answers=answers,
                )
                generated_this_pass.append(column_name)

            for column_name in generated_this_pass:
                pending.discard(column_name)

            if not generated_this_pass:
                break

        for column_name in pending:
            answers[column_name] = self._sample_for_column(
                column_name=column_name,
                persona=persona,
                answers=answers,
            )

        return answers

    def generate_response(self, persona: Persona | None = None) -> GeneratedResponse:
        """Create one response with duplicate prevention and validation metadata."""

        active_persona = persona or self.persona_generator.choose_persona()

        answers: dict[str, Any] = {}
        is_valid = False
        issues: list[str] = []
        attempts = 0

        for attempts in range(1, self.duplicate_retry_limit + 1):
            candidate = self._generate_candidate(active_persona)
            signature = self._signature_for_answers(candidate)
            if signature in self._seen_signatures:
                continue

            valid, validation_issues = self._validate_answers(candidate)
            answers = candidate
            is_valid = valid
            issues = validation_issues
            self._seen_signatures.add(signature)
            break

        if not answers:
            answers = self._generate_candidate(active_persona)
            is_valid, issues = self._validate_answers(answers)
            self._seen_signatures.add(self._signature_for_answers(answers))
            attempts = self.duplicate_retry_limit

        return GeneratedResponse(
            response_id=str(uuid4()),
            persona_id=active_persona.persona_id,
            answers=answers,
            generated_at=datetime.now(timezone.utc).isoformat(),
            metadata={
                "persona": active_persona.name,
                "persona_traits": active_persona.traits,
                "validation": {
                    "is_valid": is_valid,
                    "issues": issues,
                },
                "generation": {
                    "attempts": attempts,
                    "exploration_rate": self.exploration_rate,
                    "conditional_strength": self.conditional_strength,
                    "temperature": self.temperature,
                },
            },
        )

    def generate_responses(
        self,
        count: int,
        weighted_persona: bool = True,
    ) -> list[GeneratedResponse]:
        """Generate multiple responses using weighted or uniform persona selection."""

        generated: list[GeneratedResponse] = []
        for _ in range(max(0, int(count))):
            if weighted_persona:
                generated.append(self.generate_response())
                continue

            persona = self.persona_generator.choose_persona(weighted=False)
            generated.append(self.generate_response(persona=persona))
        return generated

    def register_existing_responses(self, responses: list[dict[str, Any]]) -> None:
        """Register previously generated rows to avoid exact duplicates."""

        for response in responses:
            self._seen_signatures.add(self._signature_for_answers(response))

    def export_responses_json(
        self,
        responses: list[GeneratedResponse],
        output_path: str | Path,
    ) -> Path:
        """Export generated responses to a JSON file."""

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [response.to_dict() for response in responses]
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def export_responses_csv(
        self,
        responses: list[GeneratedResponse],
        output_path: str | Path,
    ) -> Path:
        """Export generated responses to a flat CSV debug artifact."""

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        all_columns: set[str] = set()
        for response in responses:
            all_columns.update(response.answers.keys())

        ordered_columns = sorted(all_columns)
        fieldnames = ["response_id", "persona_id", "generated_at"] + ordered_columns

        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for response in responses:
                row: dict[str, Any] = {
                    "response_id": response.response_id,
                    "persona_id": response.persona_id,
                    "generated_at": response.generated_at,
                }
                row.update(
                    {
                        column: response.answers.get(column, "")
                        for column in ordered_columns
                    }
                )
                writer.writerow(row)

        return path
