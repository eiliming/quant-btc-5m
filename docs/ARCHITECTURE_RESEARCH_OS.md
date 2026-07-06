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

`artifact_id` 分为两层语义：

```text
{artifact_type}_{artifact_identity}_{run_id}
```

- `artifact_identity` 由 artifact type、输入 Artifact 引用和核心配置计算，表达可复现身份。
- `run_id` 表达一次唯一执行，允许同一 identity 重复运行并生成新版本。

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
research dataset artifact -> feature/label/split/experiment artifacts
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

当前代码实现了前三个基础阶段：

1. `build-dataset`: raw kline artifact
2. `run-qa`: QA report artifact
3. `build-research`: research dataset artifact

后续阶段可在同一 Artifact 模型下继续扩展。

当前数据流边界：

```text
Exchange API
  -> Downloader
  -> Raw Artifact
  -> QA Artifact
  -> Research Dataset Artifact
  -> Loader
```

Loader 只读取 research dataset artifact。QA 不访问交易所 API，Dataset Builder 不绕过 QA，后续 Feature / Label / Experiment 不应直接读取 raw artifact。

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
