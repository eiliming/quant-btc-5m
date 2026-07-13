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
| Stability analysis | Not implemented | 需要 Label、Split 和跨期 Experiment |
| Information value | Not implemented | 需要 Label Artifact，不能在 Feature Builder 内完成 |
| Redundancy analysis | Not implemented | 属于 Feature research/evaluation 阶段 |

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

## Future QA Artifacts

完整 QA 应作为独立版本化 Artifact，消费 Feature、Label 和 Split Artifact，输出可追溯指标与结论。不得把 IC、稳定性或预测效果混入 Feature 计算阶段。
