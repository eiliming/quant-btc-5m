# Phase 5 Feature Engineering 工程对齐审计

## 1. 审计目标与边界

本审计按 `AGENTS.md` 检查 Phase 5 从研究定义到 Feature Review 的设计与落地。
验收边界停在 `feature_set` / `feature_review`；Training Dataset、模型训练、策略和
成本后回测不计入 Phase 5 完成度。

正式链路为：

```text
Observation / Hypothesis
  -> Feature Definition Registry
  -> Calculator DAG
  -> feature_dataset_vN
  + label_dataset_vN
  + split_vN
  -> experiment_vN
  -> selection_decision_vN
  -> feature_set_vN
  -> feature_review_vN -> read-only lifecycle projection
```

## 2. 逐环节核查

| 环节 | 设计责任 | 当前落地 | 结论 |
|---|---|---|---|
| 研究定义 | 市场现象、假设、预期、风险、失败标准 | Definition schema 与 `FeatureResearchRecord` 已存在；Research Record 尚无独立 Builder/Artifact | 部分完成，记录契约存在但未产物化 |
| Definition Registry | 冻结 Feature identity、语义、输入输出、参数和状态 | YAML System of Record；严格字段、类型、重复 output owner 与依赖校验 | 已实现 |
| Calculator | 纯计算、只用当前/历史数据、不做 IO | 抽象接口与六个 trailing/current-only Calculator；输入 mutation 测试 | 已实现 |
| Dependency Engine | 拓扑执行、依赖复用、循环拒绝 | 自动 discovery、DAG resolve、calculator cache、timestamp alignment | 已实现 |
| FeatureBuilder | 只消费 Research Dataset，执行 QA，生成 immutable Artifact | typed input、完整 Definition snapshot、自动版本、content hash、run id、lineage | 已实现 |
| Feature QA | 结构、数值、缺失、时间对齐、leakage、分布 | build-time deterministic QA 完成；通用 leakage detector 和版本化 drift baseline 未实现 | 部分完成，当前闭环非阻断 |
| Experiment | 配置驱动，只消费既有 Feature/Label/Split | train/validation 单变量 IC、时间分段、固定 regime bins、BH q-value；禁止 test 结果 | 已实现 |
| Selection | 预声明门槛、去冗余、预算、逐项原因 | immutable Selection Decision 与 Feature Set | 已实现 |
| Lifecycle | 状态变化必须有证据且不可回写历史 | immutable Review + read-only projection；Phase 5 禁止 `approved` | 已实现 |
| Model/Trading 边界 | 模型不是策略，交易结果为最终裁判 | 明确延期到后续 OS，不以 IC 代替收益 | 边界正确 |

## 3. 本轮发现与调整

### 3.1 两类 Registry 命名混淆

此前 Builder 的 `registry_path` 只表示 Artifact Registry，却没有显式的 Feature
Definition Registry 参数，容易误认为可替换 Definition 来源。本轮增加
`feature_registry_path` / `--feature-registry`，同时保留 `registry_path` /
`--registry` 表示 lineage Registry。完整 Definition snapshot 继续写入 metadata，
保证历史解释不依赖 YAML 当前状态。

### 3.2 Definition 契约闭包不足

此前必填字段完整，但未知字段、重复 input/output/dependency、非 mapping parameters
以及跨 Feature 重复 output owner 未被统一拒绝。本轮在 Registry load gate 处理，
避免拼写错误被静默忽略或同名列被隐式覆盖。

### 3.3 文档边界漂移

早期 Framework V1 文档称“不负责 Feature Selection”，而当前 Phase 5 已在独立模块
实现 Experiment、Decision、Feature Set 和 Review。本轮改为区分“Feature Dataset
Builder 的职责”与“Phase 5 外围研究闭环”，不把筛选逻辑塞进 Builder。

### 3.4 生命周期口径不一致

Schema 为跨阶段兼容保留 `approved`，但 Phase 5 Review 明确禁止写入该状态。本轮统一
文档：Phase 5 最高为 `validated`；`approved` 必须等待 Model OS 增量贡献与成本后交易
证据。

## 4. Artifact 与可复现性判定

Feature Dataset identity 由 Research Dataset 引用和完整执行 config 决定。metadata
包含 Definition snapshot、builder/version、git commit、统计、content hash 与 run id；
输出目录自动分配 `feature_dataset_vN`，已有文件拒绝覆盖，并维护 `_current.json` 与
Artifact Registry lineage。

Experiment、Selection Decision、Feature Set 和 Review 同样使用 typed Artifact inputs。
路径仅用于运行时定位，不作为正式 lineage。Experiment 不计算 Feature/Label，选择层
不重算 Feature，Review 不修改 Registry 或历史 Artifact。

## 5. 风险与后续准入

Phase 5 当前剩余项按边界分类：

- Phase 5 可选增强：Research Record Artifact、独立 Feature QA Artifact、动态前缀
  leakage 检测、版本化分布基线、正式 trend/range 与 volatility regime Feature；
- Model OS 必须负责：Training Dataset binding、增量模型贡献、概率校准；
- Strategy/Backtest 必须负责：交易门槛、成本、滑点、仓位、退出和正期望验证。

这些延期项不得被描述为已实现，也不应通过把职责混入 FeatureBuilder 来补齐。

## 6. 验证结论

本轮代码基线与调整后均通过完整自动测试。Phase 5 在 Feature Set/Review 边界内具备
可复现、不可变、可追溯、配置驱动的最小研究闭环。现有历史 BTCUSDT closure 结果是
版本化研究证据，不代表 Feature 已 `approved`，也不代表存在交易盈利能力。
