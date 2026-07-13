# Phase 5 Feature Engineering Research Log

## Objective

建立从市场现象到可复现 Feature Artifact 的最小闭环，同时避免把“可计算”误认为“有预测价值”。

## Key Decisions

- 使用 Market Phenomenon -> Hypothesis -> Feature Definition 的研究链路
- 采用 Feature Dataset bundle，而不是每列一个 Artifact
- Calculator 保持纯函数，IO 和 Artifact 写入由 Builder 负责
- Feature 依赖由 Engine 显式解析，禁止 Calculator 隐式重算依赖
- 复用统一 ArtifactManager 的版本、hash、run ID、metadata 和 current pointer
- 最终模块名冻结为 `src/feature`
- V1 首批 Feature 全部保持 `experimental`

## Why

这些决策使新增 Feature 不需要修改核心 Engine，同时保证历史数据、计算定义、参数和代码版本能够被追溯。Feature 状态与预测有效性分离，避免未经实验的变量直接进入正式模型研究。

## Alternatives Considered

- 单 Feature Artifact：lineage 更细，但 V1 文件数量和读取成本较高
- Calculator 修改共享 DataFrame：实现简单，但会产生隐式顺序依赖和污染
- Feature 内部计算依赖：局部方便，但破坏 DAG 和重复计算治理
- 完整 Feature Store 或在线 serving：超出离线 Research OS 当前目标
- 在 Builder 中计算 IC/稳定性：需要未来 Label，会混合职责并增加泄漏风险

## What Worked

- Registry 驱动的动态 Calculator 发现
- return -> volatility 依赖拓扑与循环检测
- Artifact 自动版本化和不可覆盖写入
- Research Dataset 到 Feature Dataset 的结构化 lineage
- Rolling warm-up 和 zero-range candle 的明确边界规则

## What Failed or Needed Correction

- 初始实现未接入统一 Pipeline/CLI
- 初始 Feature Definition 缺少市场假设和生命周期字段
- 初始输入校验允许伪造 Research Artifact
- 初始 Data OS 写保护只覆盖旧 `data/` 路径
- 初始 wick 注册会产生未请求列
- 初始项目文档仍把 Feature 阶段描述为未实现

## Lessons Learned

- Implementation Brief 是最小交付范围，不能覆盖 AGENTS.md 的治理要求
- metadata 中存在上游引用不等于 Registry lineage 已经落地
- 测试通过只能证明被测试行为，不能替代架构和研究治理 Review
- 历史设计讨论必须最终压缩为仓库内可执行契约

## Next Step

Phase 5.10–5.20 已形成从 Feature Dataset、Label Dataset、时间切分、稳定性实验、Selection Decision 到 Feature Set 和 Feature Review 的最小 Research OS 闭环。Label/Split 只作为正式 Artifact 边界支撑 Feature 研究；Training Dataset 和 Model Pipeline 仍不纳入本阶段。实现不预造正式研究结果，下一步是在 clean commit 上生成真实 BTCUSDT 5m v1 Artifact 链并执行 Closure Gate。
