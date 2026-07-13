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

数据文件保存可计算内容，metadata 文件保存上下文信息，例如输入 Artifact 引用、配置、生成过程和统计摘要。

对于会重复生成的产物，目录通常先按业务身份分组，再以 `artifact_id` 作为具体版本目录：

```text
artifacts/raw/{exchange}/{symbol}/{timeframe}/{artifact_id}/
artifacts/research/datasets/{exchange}/{symbol}/{timeframe}/{artifact_id}/
artifacts/feature/datasets/{exchange}/{symbol}/{timeframe}/{artifact_id}/
artifacts/qa/reports/{exchange}/{symbol}/{timeframe}/YYYY/MM/{artifact_id}/
```

Raw 层也必须 artifact 化，不能直接写入 `YYYY/MM/data.parquet` 作为正式结果。年月分区信息保存在 metadata 的 `config.partition`、`config.start_time` 和 `config.end_time` 中。

所有正式 Artifact 都必须包含：

```text
data.parquet
metadata.json
```

`metadata.inputs` 只允许保存 Artifact 引用列表：

	```json
	[
	  {
	    "artifact_id": "raw_kline",
	    "artifact_type": "raw_kline_partition"
	  }
	]
	```

路径、交易所、symbol、timeframe、时间范围等运行上下文必须进入 `config` 或 `stats`，不能作为 dependency 写入 `inputs`。

## Artifact Identity

**非版本化类型**（`raw_kline_partition`、`qa_report`）使用固定 `artifact_id`（如 `raw_kline`、`qa_report`），无版本号、无 `_current.json`。数据不可覆盖，重跑需手动删除。

**版本化类型**（`qa_summary`、`research_dataset` 等）：
```text
{type_prefix}_v{N}
```
- `N` 为自增整数，由系统扫描目标 collection 目录自动分配。
- `content_hash`（SHA-256 前 16 位 hex）和 `run_id`（UUID4）记录在 `metadata.json` 顶层。
- 版本由 `_current.json` pointer 管理，每个 collection 目录下一个。

详细数据结构说明见 `docs/data/DATA_CONTRACT.md`。

Feature collection 使用相同版本模型：

```text
artifacts/feature/datasets/{exchange}/{symbol}/{timeframe}/
  _current.json
  _registry.json
  feature_dataset_v1/
    data.parquet
    metadata.json
```

`_current.json` 是可变指针，`_registry.json` 是可重建的依赖索引；二者不是研究结果 Artifact。具体契约见 `docs/features/FEATURE_CONTRACT.md`。
