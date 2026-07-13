# Feature Quality Assurance Specification

Phase 5.5 定义了完整 Feature QA。本文件明确哪些已经进入 V1，哪些仍属于后续研究工程。

## QA Layers

| Layer | V1 Status | Responsibility |
|---|---|---|
| Definition validation | Implemented | 必填字段、状态、依赖存在性 |
| Calculator contract | Implemented | version、inputs、outputs 与 Definition 一致 |
| Timestamp alignment | Implemented | 行数和 timestamp 与 Research Dataset 完全一致 |
| Missing/finite values | Implemented | warm-up 缺失边界、禁止无穷值、数值 dtype |
| Input Artifact validation | Implemented | 标准 metadata 和 Research schema 校验 |
| Formula unit tests | Implemented | 基础公式、边界和依赖测试 |
| Automated leakage proof | Not implemented | 需要更严格的时间依赖审计机制 |
| Distribution anomaly gates | Not implemented | 需要基准分布与阈值版本化 |
| Stability analysis | Implemented in Experiment | 按时间分段记录 IC dispersion、sign consistency 与有效分段 |
| Information value | Implemented in Experiment | 消费 Label/Split Artifact，不进入 Feature Builder |
| Redundancy analysis | Implemented in Selection Decision | 按预声明相关性门槛保存筛选证据 |

## V1 Failure Rules

以下任一情况构建失败：

- 输入不是完整的 Research Dataset Artifact
- 时间戳、行数或列契约不一致
- Feature 出现无穷值、非数值输出或非前缀缺失
- 缺失数量超过声明 lookback
- Calculator contract 与 Registry 不一致
- 依赖不存在或形成环
- 目标 Artifact 文件已经存在

当前所有 V1 Feature 使用当前及历史数据；这是一项经过代码审阅和公式测试支持的设计结论，不等同于通用自动 leakage detector。

## QA Artifact Boundary

IC、稳定性、多重检验与冗余筛选分别保存在版本化
Experiment 和 Selection Decision Artifact 中。独立历史 Feature QA Report
仍可作为后续扩展，但不得把这些指标混入 Feature 计算阶段。
