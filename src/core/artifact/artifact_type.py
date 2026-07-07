from __future__ import annotations

from enum import StrEnum


class ArtifactType(StrEnum):
    RAW_KLINE_PARTITION = "raw_kline_partition"
    QA_REPORT = "qa_report"
    QA_SUMMARY = "qa_summary"
    RESEARCH_DATASET = "research_dataset"
    FEATURE_DATASET = "feature_dataset"
    LABEL_DATASET = "label_dataset"
    SPLIT = "split"
    EXPERIMENT = "experiment"
    MODEL = "model"
