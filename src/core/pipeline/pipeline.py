from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.ingestion.downloader.downloader import download_klines
from src.validation.qa.validator import run_all
from src.transformation.research_dataset.builder import build_dataset


@dataclass(frozen=True)
class DatasetBuildConfig:
    exchange: str
    symbol: str
    timeframe: str
    start_time: str
    end_time: str
    force: bool = False
    artifact_root: Path = Path("artifacts")


@dataclass(frozen=True)
class ResearchBuildConfig:
    exchange: str
    symbol: str
    timeframe: str
    artifact_root: Path = Path("artifacts")


class ResearchPipeline:
    """Orchestrates the Research OS lifecycle: Dataset -> Feature -> Label -> Split -> Experiment."""

    def build_dataset(self, config: DatasetBuildConfig) -> dict[str, Any]:
        result = download_klines(
            config.exchange,
            config.symbol,
            config.timeframe,
            config.start_time,
            config.end_time,
            config.force,
            data_root=config.artifact_root,
        )
        return result.to_dict()

    def run_qa(self, *, artifact_root: str | Path = "artifacts") -> dict[str, Any]:
        root = Path(artifact_root)
        return run_all(root=root / "raw", report_root=root / "qa" / "reports")

    def build_research(self, config: ResearchBuildConfig) -> dict[str, Any]:
        metadata = build_dataset(
            exchange=config.exchange,
            symbol=config.symbol,
            timeframe=config.timeframe,
            raw_root=config.artifact_root / "raw",
            qa_report_root=config.artifact_root / "qa" / "reports",
            output_root=config.artifact_root / "research" / "datasets",
        )
        return metadata.to_dict()

    def build_feature(self) -> None:
        raise NotImplementedError("Feature builders are registered after dataset artifacts exist.")

    def build_label(self) -> None:
        raise NotImplementedError("Label builders are registered after feature artifacts exist.")

    def run_experiment(self) -> None:
        raise NotImplementedError("Experiments consume dataset, feature, label, and split artifacts.")
