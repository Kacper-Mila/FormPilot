"""Probability model helpers for FormPilot."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import json

import pandas as pd


def _default_marginals() -> dict[str, dict[str, float]]:
    return {}


def _default_dependencies() -> dict[str, dict[str, dict[str, float]]]:
    return {}


@dataclass(slots=True)
class ProbabilityModel:
    """Inspectable container for marginal and conditional probabilities."""

    marginals: dict[str, dict[str, float]] = field(default_factory=_default_marginals)
    dependencies: dict[str, dict[str, dict[str, float]]] = field(
        default_factory=_default_dependencies
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_probability_model(dataframe: pd.DataFrame) -> ProbabilityModel:
    """Compute simple marginal probabilities for each column."""

    marginals: dict[str, dict[str, float]] = {}
    for column_name in dataframe.columns:
        series = dataframe[column_name].dropna().astype(str)
        if series.empty:
            continue
        value_counts = series.value_counts(normalize=True, dropna=True)
        marginals[column_name] = {
            str(index): float(probability)
            for index, probability in value_counts.items()
        }

    return ProbabilityModel(marginals=marginals)


def save_probability_model(model: ProbabilityModel, output_path: str | Path) -> Path:
    """Persist the learned model as JSON."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(model.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def load_probability_model(input_path: str | Path) -> ProbabilityModel:
    """Load a previously saved probability model."""

    path = Path(input_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    return ProbabilityModel(
        marginals={
            str(column): {
                str(value): float(probability) for value, probability in values.items()
            }
            for column, values in data.get("marginals", {}).items()
        },
        dependencies=data.get("dependencies", {}),
    )
