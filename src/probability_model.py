"""Probability model helpers for FormPilot."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, cast
import json
import math

import pandas as pd


def _default_marginals() -> dict[str, dict[str, float]]:
    return {}


def _default_dependencies() -> dict[str, dict[str, dict[str, dict[str, float]]]]:
    return {}


def _default_dependency_rules() -> dict[str, list[dict[str, Any]]]:
    return {}


@dataclass(slots=True)
class ProbabilityModel:
    """Inspectable container for marginal and conditional probabilities."""

    marginals: dict[str, dict[str, float]] = field(default_factory=_default_marginals)
    dependencies: dict[str, dict[str, dict[str, dict[str, float]]]] = field(
        default_factory=_default_dependencies
    )
    dependency_rules: dict[str, list[dict[str, Any]]] = field(
        default_factory=_default_dependency_rules
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean_series(dataframe: pd.DataFrame, column_name: str) -> pd.Series:
    """Return normalized non-empty text values for one column."""

    series = dataframe[column_name].dropna().astype(str).map(str.strip)
    return series[series != ""]


def _normalized_value_counts(series: pd.Series) -> dict[str, float]:
    """Return value probabilities that sum to 1.0."""

    if series.empty:
        return {}
    value_counts = series.value_counts(normalize=True, dropna=True)
    return {
        str(index): float(probability) for index, probability in value_counts.items()
    }


def _entropy(probabilities: list[float]) -> float:
    """Compute Shannon entropy with base 2."""

    total = 0.0
    for probability in probabilities:
        if probability > 0:
            total -= probability * math.log2(probability)
    return total


def _association_score(parent: pd.Series, target: pd.Series) -> float:
    """Estimate normalized mutual information score for two categorical series."""

    combined = pd.DataFrame({"parent": parent, "target": target}).dropna()
    if combined.empty:
        return 0.0

    total_count = len(combined)
    if total_count <= 1:
        return 0.0

    raw_parent_prob = (combined["parent"].value_counts() / total_count).to_dict()
    parent_prob: dict[str, float] = {
        str(key): float(value) for key, value in raw_parent_prob.items()
    }

    raw_target_prob = (combined["target"].value_counts() / total_count).to_dict()
    target_prob: dict[str, float] = {
        str(key): float(value) for key, value in raw_target_prob.items()
    }

    raw_joint_prob = cast(
        Mapping[object, object],
        combined.groupby(["parent", "target"]).size().div(total_count).to_dict(),
    )
    joint_prob: dict[tuple[str, str], float] = {}
    for key, value in raw_joint_prob.items():
        if not isinstance(key, tuple):
            continue

        tuple_key = cast(tuple[object, ...], key)
        if len(tuple_key) != 2:
            continue

        parent_value = str(tuple_key[0])
        target_value = str(tuple_key[1])
        converted = _as_float(value)
        if converted is None:
            continue
        joint_prob[(parent_value, target_value)] = converted

    mutual_information = 0.0
    for (parent_value, target_value), p_xy in joint_prob.items():
        p_x = parent_prob.get(parent_value, 0.0)
        p_y = target_prob.get(target_value, 0.0)
        if p_xy > 0 and p_x > 0 and p_y > 0:
            mutual_information += p_xy * math.log2(p_xy / (p_x * p_y))

    parent_entropy = _entropy(list(parent_prob.values()))
    target_entropy = _entropy(list(target_prob.values()))
    denominator = max(parent_entropy, target_entropy)
    if denominator <= 0:
        return 0.0

    return float(max(0.0, mutual_information / denominator))


def build_probability_model(
    dataframe: pd.DataFrame,
    max_dependencies_per_column: int = 2,
    max_categorical_cardinality: int = 20,
    min_support_rows: int = 15,
    min_association_score: float = 0.03,
) -> ProbabilityModel:
    """Compute marginals and selected conditional dependencies from survey data."""

    marginals: dict[str, dict[str, float]] = {}
    cleaned_columns: dict[str, pd.Series] = {}

    for column_name in dataframe.columns:
        series = _clean_series(dataframe, column_name)
        cleaned_columns[column_name] = series
        if series.empty:
            continue
        marginals[column_name] = _normalized_value_counts(series)

    dependencies: dict[str, dict[str, dict[str, dict[str, float]]]] = {}
    dependency_rules: dict[str, list[dict[str, Any]]] = {}

    columns = list(dataframe.columns)
    for target_column in columns:
        target_series = cleaned_columns[target_column]
        target_unique = int(target_series.nunique())
        if target_series.empty or target_unique > max_categorical_cardinality:
            continue

        scored_candidates: list[tuple[str, float, int]] = []
        for parent_column in columns:
            if parent_column == target_column:
                continue

            parent_series = cleaned_columns[parent_column]
            parent_unique = int(parent_series.nunique())
            if parent_series.empty or parent_unique > max_categorical_cardinality:
                continue

            pair_frame = pd.DataFrame(
                {"parent": parent_series, "target": target_series}
            ).dropna()
            if len(pair_frame) < min_support_rows:
                continue

            score = _association_score(pair_frame["parent"], pair_frame["target"])
            if score < min_association_score:
                continue
            scored_candidates.append((parent_column, score, len(pair_frame)))

        if not scored_candidates:
            continue

        scored_candidates.sort(key=lambda item: item[1], reverse=True)
        selected = scored_candidates[:max_dependencies_per_column]

        target_dependencies: dict[str, dict[str, dict[str, float]]] = {}
        target_rules: list[dict[str, Any]] = []

        for parent_column, score, support_rows in selected:
            pair_frame = pd.DataFrame(
                {
                    "parent": cleaned_columns[parent_column],
                    "target": cleaned_columns[target_column],
                }
            ).dropna()
            if pair_frame.empty:
                continue

            parent_value_distributions: dict[str, dict[str, float]] = {}
            for parent_value, grouped in pair_frame.groupby("parent"):
                parent_value_distributions[str(parent_value)] = (
                    _normalized_value_counts(grouped["target"])
                )

            if not parent_value_distributions:
                continue

            target_dependencies[parent_column] = parent_value_distributions
            target_rules.append(
                {
                    "parent_column": parent_column,
                    "score": round(float(score), 6),
                    "support_rows": int(support_rows),
                    "target_cardinality": int(target_unique),
                    "parent_cardinality": int(cleaned_columns[parent_column].nunique()),
                }
            )

        if target_dependencies:
            dependencies[target_column] = target_dependencies
            dependency_rules[target_column] = target_rules

    return ProbabilityModel(
        marginals=marginals,
        dependencies=dependencies,
        dependency_rules=dependency_rules,
    )


def save_probability_model(model: ProbabilityModel, output_path: str | Path) -> Path:
    """Persist the learned model as JSON."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(model.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def _as_float(value: object) -> float | None:
    """Convert loosely-typed JSON values to float when possible."""

    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def load_probability_model(input_path: str | Path) -> ProbabilityModel:
    """Load a previously saved probability model."""

    path = Path(input_path)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, Mapping):
        loaded = {}

    data = cast(Mapping[object, object], loaded)

    raw_dependencies_obj = data.get("dependencies", {})
    if not isinstance(raw_dependencies_obj, Mapping):
        raw_dependencies_obj = {}
    raw_dependencies = cast(Mapping[object, object], raw_dependencies_obj)

    parsed_dependencies: dict[str, dict[str, dict[str, dict[str, float]]]] = {}
    for target_column_obj, parent_map_obj in raw_dependencies.items():
        if not isinstance(parent_map_obj, Mapping):
            continue

        target_column = str(target_column_obj)
        parent_map = cast(Mapping[object, object], parent_map_obj)
        normalized_parent_map: dict[str, dict[str, dict[str, float]]] = {}
        for parent_column, parent_values_obj in parent_map.items():
            if not isinstance(parent_values_obj, Mapping):
                continue

            parent_values = cast(Mapping[object, object], parent_values_obj)

            normalized_parent_values: dict[str, dict[str, float]] = {}
            for parent_value, distribution_obj in parent_values.items():
                if isinstance(distribution_obj, Mapping):
                    distribution = cast(Mapping[object, object], distribution_obj)
                    parsed_distribution: dict[str, float] = {}
                    for value, probability in distribution.items():
                        converted = _as_float(probability)
                        if converted is None:
                            continue
                        parsed_distribution[str(value)] = converted
                    normalized_parent_values[str(parent_value)] = parsed_distribution
                else:
                    # Backward compatibility for older model shape.
                    normalized_parent_values[str(parent_value)] = {}

            normalized_parent_map[str(parent_column)] = normalized_parent_values

        parsed_dependencies[target_column] = normalized_parent_map

    raw_marginals_obj = data.get("marginals", {})
    if not isinstance(raw_marginals_obj, Mapping):
        raw_marginals_obj = {}

    parsed_marginals: dict[str, dict[str, float]] = {}
    for column_obj, values_obj in cast(
        Mapping[object, object], raw_marginals_obj
    ).items():
        if not isinstance(values_obj, Mapping):
            continue

        parsed_values: dict[str, float] = {}
        for value_obj, probability_obj in cast(
            Mapping[object, object], values_obj
        ).items():
            converted = _as_float(probability_obj)
            if converted is None:
                continue
            parsed_values[str(value_obj)] = converted

        parsed_marginals[str(column_obj)] = parsed_values

    raw_dependency_rules_obj = data.get("dependency_rules", {})
    if not isinstance(raw_dependency_rules_obj, Mapping):
        raw_dependency_rules_obj = {}

    parsed_dependency_rules: dict[str, list[dict[str, Any]]] = {}
    for target_obj, rules_obj in cast(
        Mapping[object, object], raw_dependency_rules_obj
    ).items():
        if not isinstance(rules_obj, list):
            continue

        typed_rules_obj = cast(list[object], rules_obj)
        parsed_dependency_rules[str(target_obj)] = [
            cast(dict[str, Any], rule)
            for rule in typed_rules_obj
            if isinstance(rule, dict)
        ]

    return ProbabilityModel(
        marginals=parsed_marginals,
        dependencies=parsed_dependencies,
        dependency_rules=parsed_dependency_rules,
    )
