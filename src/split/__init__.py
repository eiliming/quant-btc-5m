"""Config-driven, immutable time-series Split Artifacts."""

from src.split.builder import build_split
from src.split.schema import EmbargoPolicy, PurgePolicy, SplitBuildConfig, TimeInterval

__all__ = ["EmbargoPolicy", "PurgePolicy", "SplitBuildConfig", "TimeInterval", "build_split"]
