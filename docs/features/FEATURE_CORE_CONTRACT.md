# Feature Core Contract

本文档描述 Phase 5.9.1 的工程边界。治理优先级始终以根目录 `AGENTS.md` 为准。

## Scope

本阶段只实现 Feature 的定义、生命周期状态、配置 Registry、标准 Artifact metadata 适配和只读 CLI。
Feature 计算、FeatureBuilder、Feature QA 与 Feature Dataset 写盘不属于本阶段。

## Feature Definition

每项 Feature 必须在 `configs/features/feature_registry.yaml` 中声明：

- `feature_id`: `{name}_v{N}`，版本从 1 开始且定义不可覆盖
- `name`、`version`、`group`、`status`
- `description`、`market_phenomenon`、`research_hypothesis`
- `calculation_method`、`expected_effect`、`potential_risks`
- `inputs`、`lookback`、`calculator`

生命周期状态为：`idea`、`experimental`、`validated`、`approved`、`deprecated`、`archived`。

## Artifact Metadata

Feature Dataset 必须使用核心 `ArtifactMetadata`，不得建立平行 metadata schema。其：

- `artifact_type` 必须为 `feature_dataset`
- `inputs` 必须且只能引用一个 `research_dataset` Artifact
- `config` 必须包含 `feature_set_id`、`feature_ids`、`schema_version`
- 实际生成时仍必须由 `ArtifactManager` 分配 `feature_dataset_v{N}` 并执行 immutable write

## CLI

```bash
python -m src.features.cli list
python -m src.features.cli inspect <feature_id>
python -m src.features.cli registry-check
```

三个命令均为只读操作，输出结构化 JSON。
