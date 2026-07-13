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
  -> Approved or Rejected
  -> Deprecated
  -> Archived
```

当前 Registry 中的首批 Feature 全部是 `experimental`。框架通过测试只证明它们计算正确、可复现、可追溯，不代表具有预测能力，也不允许直接被宣称为 Approved Alpha。

## Review Gate

状态提升至少需要：

- `experimental -> validated`：定义冻结、确定性 QA 通过、无已知未来信息、初步实验有结构化记录
- `validated -> approved`：跨时间切分稳定性、增量信息价值和交易意义经过正式 Experiment/Evaluation
- `approved -> deprecated`：新证据表明失效、风险变化或已有替代版本

任何状态变化都必须新增研究记录；Feature Artifact 和历史 Experiment 不得删除或覆盖。

## Change Rules

- 公式、输入、窗口或含义变化：创建新 Feature version
- 只改变一组 Feature 的组合：创建新 Feature Dataset Artifact version
- Calculator 重构但输出语义不变：通过回归测试证明结果一致，并由 git commit 追踪
- 失败的 Feature：保留证据和结论，不从历史中抹除
