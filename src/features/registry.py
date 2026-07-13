from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.features.exceptions import FeatureNotFoundError, FeatureRegistryError
from src.features.models import FeatureDefinition, FeatureStatus


DEFAULT_REGISTRY_PATH = Path("configs/features/feature_registry.yaml")
REGISTRY_SCHEMA_VERSION = "v1"


class FeatureRegistry:
    """Read-only, config-backed catalog of governed Feature definitions."""

    def __init__(self, definitions: list[FeatureDefinition], *, schema_version: str) -> None:
        if schema_version != REGISTRY_SCHEMA_VERSION:
            raise FeatureRegistryError(
                f"unsupported feature registry schema_version {schema_version!r}; "
                f"expected {REGISTRY_SCHEMA_VERSION!r}"
            )
        self.schema_version = schema_version
        self._definitions: dict[str, FeatureDefinition] = {}
        for definition in definitions:
            if definition.feature_id in self._definitions:
                raise FeatureRegistryError(f"duplicate feature_id: {definition.feature_id}")
            self._definitions[definition.feature_id] = definition

    @classmethod
    def load(cls, path: str | Path = DEFAULT_REGISTRY_PATH) -> "FeatureRegistry":
        registry_path = Path(path)
        if not registry_path.is_file():
            raise FeatureRegistryError(f"feature registry does not exist: {registry_path}")
        try:
            payload = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise FeatureRegistryError(f"invalid feature registry YAML: {exc}") from exc
        if not isinstance(payload, dict):
            raise FeatureRegistryError("feature registry root must be an object")
        allowed = {"schema_version", "features"}
        missing = sorted(allowed - payload.keys())
        unknown = sorted(payload.keys() - allowed)
        if missing:
            raise FeatureRegistryError(f"feature registry missing required fields: {missing}")
        if unknown:
            raise FeatureRegistryError(f"feature registry contains unknown fields: {unknown}")
        raw_features: Any = payload["features"]
        if not isinstance(raw_features, list):
            raise FeatureRegistryError("feature registry features must be a list")
        definitions = []
        for index, raw_definition in enumerate(raw_features):
            if not isinstance(raw_definition, dict):
                raise FeatureRegistryError(f"features[{index}] must be an object")
            try:
                definitions.append(FeatureDefinition.from_dict(raw_definition))
            except (TypeError, ValueError) as exc:
                if isinstance(exc, FeatureRegistryError):
                    raise FeatureRegistryError(f"features[{index}]: {exc}") from exc
                raise FeatureRegistryError(f"features[{index}]: invalid field type: {exc}") from exc
        return cls(definitions, schema_version=str(payload["schema_version"]))

    def list_features(
        self,
        *,
        status: FeatureStatus | str | None = None,
        group: str | None = None,
    ) -> list[FeatureDefinition]:
        normalized_status = FeatureStatus(status) if status is not None else None
        definitions = self._definitions.values()
        return sorted(
            (
                definition for definition in definitions
                if (normalized_status is None or definition.status == normalized_status)
                and (group is None or definition.group == group)
            ),
            key=lambda definition: (definition.group, definition.feature_id),
        )

    def get_feature(self, feature_id: str) -> FeatureDefinition:
        try:
            return self._definitions[feature_id]
        except KeyError as exc:
            raise FeatureNotFoundError(f"feature is not registered: {feature_id}") from exc
