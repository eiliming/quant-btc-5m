# Artifact Storage Design

本文档解释 Artifact 存储设计。执行规范与系统约束统一见 `AGENTS.md`。

## Layout

Research OS 使用 `artifacts/` 作为本地研究产物根目录：

```text
artifacts/
  raw/
  qa/
    reports/
    summary/
  research/
    datasets/
  feature/
    datasets/
  label/
    datasets/
  split/
  experiments/
  models/
```

## Storage Roles

`raw/` 表示原始市场事实。

`qa/` 表示数据质量检查结果。

`research/datasets/` 表示经过标准化处理、可供后续 Feature 与 Label 阶段使用的数据集。

`feature/`、`label/`、`split/`、`experiments/`、`models/` 对应研究生命周期中的后续产物。

## File Model

Artifact 的文件模型由数据文件和 metadata 文件组成。

数据文件保存可计算内容，metadata 文件保存上下文信息，例如输入来源、配置、生成过程和统计摘要。

对于会重复生成的产物，目录通常先按业务身份分组，再以 `artifact_id` 作为具体版本目录：

```text
artifacts/research/datasets/{exchange}/{symbol}/{timeframe}/{artifact_id}/
artifacts/qa/reports/{exchange}/{symbol}/{timeframe}/YYYY/MM/{artifact_id}/
```

详细数据结构说明见 `docs/data/DATA_CONTRACT.md`。
