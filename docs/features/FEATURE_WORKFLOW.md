# Feature Research Workflow

Feature 是市场假设的可观测表达，不是任意数学变换。

## Lifecycle

```text
Market Observation
  -> Proposal
  -> Experimental Definition
  -> Calculator + Artifact
  -> Deterministic QA
  -> Label/Split Experiment
  -> Validated
  -> Model OS / Backtest evidence (outside Phase 5)
  -> Approved or Rejected
  -> Deprecated
  -> Archived
```

当前 Registry 中的首批 Feature 全部是 `experimental`。框架通过测试只证明它们计算正确、可复现、可追溯，不代表具有预测能力，也不允许直接被宣称为 Approved Alpha。

## Review Gate

状态提升至少需要：

- `experimental -> validated`：定义冻结、确定性 QA 通过、无已知未来信息、初步实验有结构化记录
- `validated -> approved`：Phase 5 不执行此迁移；必须由后续阶段同时提供模型增量贡献和成本后交易意义证据
- `approved -> deprecated`：新证据表明失效、风险变化或已有替代版本

任何状态变化都必须新增研究记录；Feature Artifact 和历史 Experiment 不得删除或覆盖。
Registry 中的声明状态是定义快照，当前研究状态从 immutable `feature_review_vN`
历史投影，不回写 YAML，也不修改旧 Artifact。

## Change Rules

- 公式、输入、窗口或含义变化：创建新 Feature version
- 只改变一组 Feature 的组合：创建新 Feature Dataset Artifact version
- Calculator 重构但输出语义不变：通过回归测试证明结果一致，并由 git commit 追踪
- 失败的 Feature：保留证据和结论，不从历史中抹除
