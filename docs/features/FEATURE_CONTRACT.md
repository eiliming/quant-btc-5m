# Feature Framework Contract

本文档是 Feature Framework V1 的工程契约。执行冲突时以 `AGENTS.md` 为准。

## Scope

V1 负责：

- 从正式 `research_dataset` Artifact 生成 `feature_dataset` Artifact
- 加载 Feature Definition
- 解析依赖并按拓扑顺序执行 Calculator
- 执行确定性数据质量校验
- 写入不可变、版本化、可追溯的 Artifact

本契约中的 Framework V1 仅负责 Feature Dataset 构建，不在 Builder 内判断
Feature 有效性。Phase 5 的外围研究层另行负责 Label/Split 消费、Experiment、
Selection Decision、Feature Set 和 Review；模型训练与交易决策仍不属于 Phase 5。

## Module Boundaries

```text
src/feature/registry     定义 Feature 是什么
src/feature/calculator   解析与执行，不执行 IO
src/feature/features     纯函数 Calculator
src/feature/dataset      输入校验、QA、Artifact 构建
src/feature/metadata     Feature metadata 扩展
src/feature/experiment   只读消费 Feature/Label/Split 的单变量评估
src/feature/selection    筛选证据与 Feature Set 构建
src/feature/lifecycle    immutable Review 与状态投影
src/feature/cli.py       独立 CLI
src/core/pipeline        Research OS 统一编排入口
```

最终命名为单数 `src/feature`。早期设计中的 `src/features` 不再是正式模块。

## Input Contract

输入必须是目录形式的正式 Artifact：

```text
research_dataset_vN/
  data.parquet
  metadata.json
```

Builder 必须验证：

- 标准 Artifact metadata 完整
- `artifact_type == research_dataset`
- `content_hash` 和 `run_id` 存在
- Research Dataset identity、schema、时间戳连续性和 OHLCV 合法
- Feature Definition 必填字段、字段闭包、参数/依赖类型、单一 output owner

Feature Framework 只读输入，不得写入 `raw` 或 `research` collection。

## Output Contract

推荐 collection：

```text
artifacts/feature/datasets/{exchange}/{symbol}/{timeframe}/
```

每次执行生成新版本：

```text
feature_dataset_vN/
  data.parquet
  metadata.json
```

`data.parquet` 只包含 `timestamp` 和实际请求及其依赖产生的 Feature 列，不复制 OHLCV。

## Artifact Identity and Registry

`artifact_id` 使用 `feature_dataset_vN`。`content_hash` 由 Artifact type、Research Dataset 引用和完整 Feature config 决定；`run_id` 标识单次执行。

每个 collection 包含：

- `_current.json`：当前版本与历史版本指针
- `_registry.json`：上游、下游、lineage 和 impact 查询索引

Feature Artifact 的正式依赖必须是结构化 Research Artifact 引用，路径只能出现在 Registry record 或 config 中。

Feature Definition Registry 与 Artifact Registry 是两个不同概念：

- Feature Definition Registry：默认 `src/feature/registry/features.yaml`，定义 Feature 语义与计算契约；
- Artifact Registry：默认 collection 下 `_registry.json`，索引 Artifact lineage。

CLI 分别使用 `--feature-registry` 与 `--registry`。Builder 会把实际解析后的完整
Feature Definition snapshot 写入 metadata config，因此历史 Artifact 不依赖 YAML 的
当前内容来解释。

## CLI

统一入口：

```bash
python cli.py build-feature \
  --dataset artifacts/research/datasets/binance_spot/BTCUSDT/5m/research_dataset_v1 \
  --features return_1,body_ratio,volume_ratio_20,volatility_20 \
  --output artifacts/feature/datasets/binance_spot/BTCUSDT/5m
```

模块入口 `python -m src.feature.cli build` 提供相同构建能力。
