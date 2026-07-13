# Research OS Architecture

本文档解释 Research OS 的架构概念。执行规范与系统约束统一见 `AGENTS.md`。

## Concept

Research OS 是一个以 Artifact 为中心的量化研究平台。

它将研究过程拆成一系列可命名、可保存、可追溯的研究产物，使数据、特征、标签、实验和评估可以被清晰地连接起来。

## Artifact System

Artifact 是一次计算或研究步骤的持久化结果。

典型结构：

```text
{artifact_root}/
  data.parquet
  metadata.json
```

`data.parquet` 保存结构化数据，`metadata.json` 描述身份、输入 Artifact、生成过程、配置和统计信息。

对于可重复生成的研究产物，`artifact_root` 通常是带 `artifact_id` 的版本目录。

`artifact_id` 根据类型是否版本化有两种方案：

**非版本化类型**（`raw_kline_partition`、`qa_report`）使用固定名称：
```text
{type_prefix}
```
例如 `raw_kline`、`qa_report`。

**版本化类型**（`research_dataset`、`feature_dataset` 等）使用自增版本号：
```text
{type_prefix}_v{N}
```
其中 `N` 由系统扫描目标 collection 目录自动分配，从 1 开始。

`content_hash`（SHA-256(artifact_type + inputs + config) 前 16 位 hex）和 `run_id`（UUID4 hex）不进入目录名，而是存储在 `metadata.json` 顶层字段中，分别用于可复现性标识和单次执行追踪。

`metadata.inputs` 是 Artifact dependency list，结构如下：

```json
[
  {
    "artifact_id": "...",
    "artifact_type": "..."
  }
]
```

路径、时间范围、交易对和 schema version 属于 `config` 或 `stats`，不能作为依赖写入 `inputs`。

## Artifact DAG

Artifact System 使用 DAG 表示全链路依赖：

```text
raw artifact -> QA report artifact -> QA summary artifact
raw artifact + QA report artifact -> research dataset artifact
research dataset artifact -> feature dataset artifact
research dataset artifact -> label dataset artifact -> split artifact
feature + label + split artifacts -> feature experiment -> selection decision -> feature set
experiment + decision + feature set -> feature review
```

Registry 是 Artifact System of Record，负责维护：

- dependency index
- reverse dependency index
- upstream lookup
- downstream lookup
- lineage tracing
- impact analysis

## Pipeline Lifecycle

Research OS 的概念生命周期是：

```text
Dataset -> Feature -> Label -> Split -> Experiment -> Evaluation
```

当前代码在 Phase 5 Research OS 闭环内实现：

1. `build-dataset`: raw kline artifact
2. `run-qa`: QA report artifact
3. `build-research`: research dataset artifact
4. `build-feature`: feature dataset artifact
5. `LabelBuilder`: label dataset artifact
6. `SplitBuilder`: chronological split artifact
7. Feature 子入口的研究实验：消费既有 Feature、Label、Split Artifact
8. Selection Decision：冻结机器筛选证据
9. Feature selection：生成版本化 Feature Set Artifact
10. Feature Review 与只读 lifecycle status projection

Training Dataset Builder 与 Model Runner 不属于当前 Phase 5 已实现边界。

当前数据流边界：

```text
Exchange API
  -> Downloader
  -> Raw Artifact
  -> QA Artifact
  -> Research Dataset Artifact
  -> Feature Registry + Dependency Engine
  -> Feature Dataset Artifact
  + Label Dataset Artifact
  + Split Artifact
  -> Feature Experiment Artifact
  -> Selection Decision Artifact
  -> Feature Set Artifact
  -> Feature Review Artifact
```

Loader 只读取 research dataset artifact。QA 不访问交易所 API，Dataset Builder 不绕过 QA，后续 Feature / Label / Experiment 不应直接读取 raw artifact。

Feature Builder 只接受包含完整标准 metadata 的 `research_dataset` Artifact，输出到独立的 `feature/datasets` collection。Calculator 不执行 IO，Engine 不写 Artifact，Builder 不定义计算公式。

Feature 设计和当前工程状态见 `docs/features/`。

## Builder vs Artifact

Builder 是生成 Artifact 的代码单元。

Artifact 是 Builder 执行后的研究产物。

二者分离后，代码可以持续演进，历史研究产物仍然可以通过 metadata 解释其来源。

## Experiment Concept

Experiment 表示一次假设验证过程。

在 Research OS 中，Experiment 可以被理解为对 Dataset、Feature、Label、Split 等输入产物的一次组合评估，并产出可复盘的结果。

## Versioning Model

Research OS 使用 metadata 将代码版本、输入产物、运行配置和输出统计连接起来。

这种模型使后续研究者可以理解一个结果来自哪里，以及它和其他结果之间有什么差异。
