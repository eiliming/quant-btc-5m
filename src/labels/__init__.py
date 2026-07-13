"""Config-driven, immutable Label Artifact construction."""

from src.labels.builder import build_label_dataset
from src.labels.schema import LabelBuildConfig, TargetDefinition, validate_label_frame

__all__ = [
    "LabelBuildConfig",
    "TargetDefinition",
    "build_label_dataset",
    "validate_label_frame",
]
