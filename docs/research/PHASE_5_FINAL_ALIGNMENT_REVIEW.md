# Phase 5（5.1–5.20）课程归纳与实现验收

## 1. 验收边界

本次按项目确认后的真实边界验收：

```text
Market Observation
  -> Feature Research Record
  -> Feature Definition / Registry
  -> Feature Calculator DAG
  -> Feature Dataset Artifact
  -> Feature Experiment Artifact
  -> Feature Set Artifact
```

Phase 5 的最终正式数据产物是 `feature_set_vN`。Feature Experiment 可以消费
独立 Label/Split Artifact。为完成第一个真实 Feature Research 闭环，Phase 5 Closure
实现了最小 LabelBuilder 和 chronological SplitBuilder，但不负责生成
Training Dataset、Model 或 Backtest Artifact。

课程原文在 5.17、5.20 中讨论了 Training Dataset 接口，这是架构设计和后续接口
预留，不等于当前工程准入。Closure 仅新增 Label/Split Artifact 责任边界，
没有引入 Training Dataset Builder 或统一 Model Pipeline。

## 2. Phase 5 总体归纳

Phase 5 不是“指标开发阶段”，而是把市场假设转换为可复现研究证据的 Feature OS：

1. 5.1–5.3 建立市场语言、Feature 映射和 Artifact 契约。
2. 5.4–5.9 建立 Registry、Calculator、DAG、QA、Builder 和工程验收。
3. 5.10–5.13 建立研究记录、实验、筛选和版本化 Feature Set。
4. 5.14–5.16 增加时间/Regime 稳定性、生命周期和实验治理。
5. 5.17–5.19 规定存储边界、生产化原则与 Alpha 发现方法。
6. 5.20 收敛职责并冻结 Feature Set 作为当前交付边界。

## 3. 分章节复盘

| 章节 | 课程核心 | 代码实现 | 文档/设计 | 验收结论 |
|---|---|---|---|---|
| 5.1 | Market Phenomenon Taxonomy | Registry 的 `group`、`market_phenomenon` | `FEATURE_PRINCIPLES.md`、`FEATURE_SCHEMA.md` | 设计已落入定义字段；尚无独立 ontology 文件 |
| 5.2 | Phenomenon -> observable Feature | `research_hypothesis`、`expected_effect` | Feature principles/schema | 符合“先市场解释、后公式”要求 |
| 5.3 | Feature Schema、版本、lineage | `FeatureDefinition`、`FeatureMetadata`、Feature Dataset Artifact | `FEATURE_CONTRACT.md`、`FEATURE_SCHEMA.md` | 已实现 bundle Artifact；版本和输入引用符合 AGENTS.md |
| 5.4 | Registry、Engine、Calculator、Builder | `src/feature/registry`、`calculator`、`dataset` | `FEATURE_CONTRACT.md` | 已实现，职责分离清楚 |
| 5.5 | Correctness、leakage、missing、distribution、stability、information | build-time schema/timestamp/missing/inf QA；实验层 IC/stability | `FEATURE_QA_SPEC.md` | 部分完成；独立 QA Artifact 和自动代码级 leakage 检测未实现 |
| 5.6 | Feature lifecycle 和研究准入 | Registry status、`FeatureResearchRecord`、`feature_review_vN` | `FEATURE_WORKFLOW.md` | 生命周期证据可保存；Registry 状态不会被隐式改写 |
| 5.7 | 工程模块边界 | `src/feature/{registry,calculator,features,dataset,metadata}` | 工程状态文档 | 与冻结结构一致 |
| 5.8 | MVP、首批 Feature、Smoke Test | 六个基础 Feature、合成/真实 smoke evidence | implementation status/research log | MVP 已完成，没有扩张到复杂 Feature |
| 5.9.1 | Core models/Registry/metadata | Definition、Registry、Metadata | Feature contract | 已实现 |
| 5.9.2 | Calculator interface/Engine | pure calculators、dynamic discovery | framework review | 已实现 |
| 5.9.3 | 原子 Feature 和依赖策略 | return/candle/volume/volatility | Registry YAML | 已实现六个基础 Feature |
| 5.9.4 | API、DAG、Builder 规格冻结 | `FeatureEngine.calculate`、Builder API | contract/schema | 已实现 |
| 5.9.5 | 实施顺序和测试 | formula/dependency/immutability/lineage tests | engineering log | 已实现 |
| 5.9.6 | Codex implementation specification | 对应模块均存在 | 课程规格由仓库契约收敛 | 已实现 |
| 5.9.7 | Framework Review Gate | 实际 BTCUSDT smoke test | `PHASE_5_9_7_FEATURE_FRAMEWORK_REVIEW.md` | 已通过 |
| 5.10 | Feature Library、Family、生命周期 | enriched Registry、Feature Set/Review types | `PHASE_5_10_5_13_FEATURE_RESEARCH_OS.md` | V1 知识目录已实现；Feature family 目前用 `group` 表达 |
| 5.11 | Observation/Hypothesis/Failure criteria | `FeatureResearchRecord` | 5.10–5.13 设计文档 | 已实现结构化契约，尚无单独 Research Record Builder/Artifact |
| 5.12 | Config-driven Feature Experiment | `FeatureExperimentConfig`、runner | 5.10–5.13 设计文档 | 已实现；只消费 Artifact，不临时生成 Feature/Label |
| 5.13 | Filtering、redundancy、budget、Feature Set | `FeatureSelectionConfig`、selector、`feature_set_vN` | selection protocol in design doc | 已实现 V1；未实现 clustering/wrapper/model-based selection |
| 5.14 | Temporal/Regime stability | temporal segments、fixed numeric regime bins、stability summary | `PHASE_5_14_5_19_IMPLEMENTATION.md` | 评估能力已实现；Regime Feature Calculator 本身未实现 |
| 5.15 | Lifecycle、decay、retirement | immutable Feature Review；deprecate/archive decisions | workflow/implementation docs | 基础生命周期已实现；持续监控和 decay detector 未实现 |
| 5.16 | Feature addition/removal/replacement/interaction experiments | univariate information experiment | implementation doc 明确边界 | 部分完成；涉及模型的 A/B contribution 属于后续 Model OS |
| 5.17 | Offline Feature Store、snapshot、Training integration | `feature_dataset_vN` 作为 immutable snapshot | 仅保留接口设计 | 截止 Feature Set；Training integration 明确未实现 |
| 5.18 | DAG、incremental、cache、validation、CLI、tests | DAG、dependency reuse、QA、CLI、tests | implementation doc | 核心离线能力完成；incremental/cache/online/CI 未实现且不阻塞当前边界 |
| 5.19 | Human+machine Alpha discovery、multiple testing | Research Record、p/q-value、BH correction | implementation doc | 人工研究入口和 false-discovery gate 已实现；自动公式搜索未实现 |
| 5.20 | Final architecture review | 无新增越界模块 | 本文与 status 文档 | 已按 Feature Set 边界收敛 |

## 4. 当前代码产物与职责

### Feature Definition Layer

- `src/feature/registry/features.yaml`：Feature System of Record。
- `FeatureDefinition`：名称、版本、family/group、输入输出、依赖、参数、市场解释、
  风险、lookback 和状态。
- `FeatureResearchRecord`：Observation -> Hypothesis -> Feature proposal 契约。

### Computation Layer

- `FeatureCalculator`：无 IO、不修改输入 DataFrame。
- `FeatureEngine`：Registry 查询、依赖解析、拓扑执行、循环依赖拒绝。
- 六个 V1 Feature：`return_1`、`body_ratio`、`upper_wick_ratio`、
  `lower_wick_ratio`、`volume_ratio_20`、`volatility_20`。

### Artifact Layer

- `feature_dataset_vN`：具体 Feature values snapshot。
- `experiment_vN`：Feature/Label/Split 的结构化评估结果。
- `feature_set_vN`：通过筛选的 Feature identity 集合。
- `feature_review_vN`：生命周期判断和证据引用，不产生训练数据。

### Research Evaluation Layer

- Overall、时间分段和固定 Regime 边界评估。
- Pearson/Spearman IC、方向胜率、缺失率、样本量。
- 近似相关性 p-value 和 Benjamini-Hochberg q-value。
- IC sign consistency、dispersion 和平均绝对 IC。
- 缺失率/IC filter、相关性去冗余与 Feature Budget。

## 5. 与课程设计和 AGENTS.md 的符合性

### 通过项

- 所有正式结果均使用标准 Artifact metadata、版本目录和结构化 inputs。
- Builder 不覆盖已有 Artifact；Feature Dataset/Experiment/Feature Set 可追溯。
- Calculator 无 IO、无输入 mutation，Feature/Label 职责没有混合。
- Feature 实验由 YAML config 驱动，并记录 objective、hypothesis、seed、conclusion、
  next action。
- 时间序列不随机打乱；实验只消费预先存在的 Split Artifact。
- 模型贡献和交易收益没有被 Feature IC 冒充。
- Feature 状态只能由 immutable Review evidence 投影，Registry 不会被隐式改写。

### 部分符合项

- Feature QA 能验证输出结构和常见数值异常，但还没有独立版本化 QA Report。
- Leakage 通过纯 trailing 实现、lookback 声明和测试治理，没有通用静态/动态检测器。
- Regime stability runner 已存在，但 Feature Library 尚无 trend/compression/transition
  Regime Feature。
- Feature lifecycle 已支持从 Review Artifact 派生 current-state 只读投影。
- Alpha multiple testing 只有单次 Experiment 内 BH correction，没有 experiment-family
  级 search budget。

### 明确未实现且不应计为 Phase 5 完成项

- Training Dataset/manifest/snapshot join。
- Model training、hyperparameter search、Feature contribution A/B。
- Strategy、cost-aware backtest、online Feature Store。
- Incremental append/cache/distributed execution。
- Automated feature formula generation。

## 6. 发现的课程与工程歧义

1. 课程中 `Feature Dataset`、`Feature Bundle`、`Feature Set`、`Snapshot` 曾交替使用。
   当前仓库统一为：Feature Dataset 存值，Feature Set 存选择结果。
2. 5.12 与 5.16 都描述 Feature Experiment。当前只保留一个 runner；5.16 的模型
   contribution 部分延期到 Model OS。
3. 5.13 与 5.15 都描述 Feature Selection/Lifecycle。当前 selector 负责选择，Review
   Artifact 负责生命周期证据，避免重复模块。
4. 5.17/5.20 描述 Training Dataset 接口，但当前课程进度由用户确认截止 Feature Set，
   因此只保留设计边界，不提前实现。
5. “Production/approved” 不能仅凭 Feature 指标决定，仍必须等待模型增量贡献和交易
   成本证据。

## 7. 验收结论

Phase 5 在“Feature Set”边界内整体符合设计需求，核心计算、Artifact、研究实验、
稳定性和筛选链条已经具备可测试实现。

当前工程实现已具备生成 Label、Split、Experiment、Selection Decision、
Feature Set、Feature Review 与 lifecycle projection 的最小能力。最终是否通过
Phase 5 必须由 clean commit 上的真实 BTCUSDT 5m Artifact 链和 Closure Gate 证据决定。
独立 Feature QA Artifact 和 Regime Feature Library 属于非阻断扩展；Training/Model/Backtest
属于后续阶段，不得回填到 Phase 5。
