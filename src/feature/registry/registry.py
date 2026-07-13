from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.feature.registry.schema import FeatureDefinition


class FeatureRegistry:
    REQUIRED_FIELDS = (
        "name",
        "version",
        "group",
        "calculator",
        "inputs",
        "outputs",
        "description",
        "market_phenomenon",
        "research_hypothesis",
        "calculation_method",
        "expected_effect",
        "potential_risks",
        "lookback",
        "status",
    )
    ALLOWED_STATUSES = {"experimental", "validated", "approved", "deprecated", "archived"}

    def __init__(self, config_path: str | Path | None = None) -> None:
        self.config_path = Path(config_path or Path(__file__).with_name("features.yaml"))
        self._features = self._load()

    def _load(self) -> dict[str, FeatureDefinition]:
        with self.config_path.open("r", encoding="utf-8") as stream:
            payload = yaml.safe_load(stream) or {}
        raw_features = payload.get("features")
        if not isinstance(raw_features, dict):
            raise ValueError("feature registry must contain a 'features' mapping")

        definitions: dict[str, FeatureDefinition] = {}
        for name, raw in raw_features.items():
            if not isinstance(raw, dict):
                raise ValueError(f"feature definition must be a mapping: {name}")
            normalized: dict[str, Any] = {"name": name, **raw}
            self.validate(normalized)
            definition = FeatureDefinition(
                name=str(name),
                version=str(raw["version"]),
                group=str(raw.get("group", "ungrouped")),
                calculator=str(raw["calculator"]),
                inputs=[str(value) for value in raw.get("inputs", [])],
                outputs=[str(value) for value in raw["outputs"]],
                dependencies=[str(value) for value in raw.get("dependencies", [])],
                parameters=dict(raw.get("parameters", {})),
                description=str(raw["description"]),
                market_phenomenon=str(raw["market_phenomenon"]),
                research_hypothesis=str(raw["research_hypothesis"]),
                calculation_method=str(raw["calculation_method"]),
                expected_effect=str(raw["expected_effect"]),
                potential_risks=[str(value) for value in raw["potential_risks"]],
                lookback=int(raw["lookback"]),
                status=str(raw["status"]),
            )
            definitions[name] = definition

        unknown_dependencies = sorted({
            dependency
            for definition in definitions.values()
            for dependency in definition.dependencies
            if dependency not in definitions
        })
        if unknown_dependencies:
            raise ValueError(f"unknown feature dependencies: {unknown_dependencies}")
        return definitions

    def get(self, name: str) -> FeatureDefinition:
        try:
            return self._features[name]
        except KeyError as exc:
            raise KeyError(f"unknown feature: {name}") from exc

    def list(self) -> list[FeatureDefinition]:
        return list(self._features.values())

    @classmethod
    def validate(cls, definition: dict[str, Any]) -> None:
        missing = [field for field in cls.REQUIRED_FIELDS if field not in definition]
        if missing:
            raise ValueError(f"feature definition missing required fields: {missing}")
        for field in ("inputs", "outputs", "potential_risks"):
            if not isinstance(definition[field], list):
                raise ValueError(f"feature definition {field} must be a list")
        for field in (
            "name", "version", "group", "calculator", "description",
            "market_phenomenon", "research_hypothesis", "calculation_method",
            "expected_effect", "status",
        ):
            if not isinstance(definition[field], str) or not definition[field].strip():
                raise ValueError(f"feature definition {field} must be a non-empty string")
        if not definition["outputs"]:
            raise ValueError("feature definition outputs must not be empty")
        if not isinstance(definition["lookback"], int) or definition["lookback"] < 0:
            raise ValueError("feature definition lookback must be a non-negative integer")
        if definition["status"] not in cls.ALLOWED_STATUSES:
            raise ValueError(f"unsupported feature status: {definition['status']}")
