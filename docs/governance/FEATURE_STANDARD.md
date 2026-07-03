# Feature Standard

本文档定义 Feature 的生命周期和最低准入标准。

## 核心要求

任何 Feature 没有 Market Phenomenon 不允许进入项目。

Feature 不是数学变换的堆叠，而是对某种市场现象的结构化表达。每个 Feature 都必须能回答：它描述了市场中的什么行为。

## Feature 必备字段

每个 Feature 必须具有以下字段：

1. Feature ID
2. Feature Name
3. Market Phenomenon
4. Research Hypothesis
5. Calculation Method
6. Expected Effect
7. Potential Risks
8. Version
9. Status

## 字段说明

### Feature ID

Feature 的唯一编号，用于追踪、复现和实验引用。

### Feature Name

简洁、稳定、可读的 Feature 名称。

### Market Phenomenon

Feature 对应的市场现象。例如趋势延续、动量衰减、波动扩张、成交量异常、价格突破、市场状态切换。

没有该字段的 Feature 不允许进入项目。

### Research Hypothesis

该 Feature 背后的研究假设，必须能被数据和实验验证。

### Calculation Method

计算方法必须明确说明输入字段、窗口长度、时间对齐方式和是否使用滚动统计。

计算过程只能使用当前时刻及过去数据。

### Expected Effect

预期该 Feature 对模型或策略产生的影响，例如提高上涨样本 Precision、识别震荡区间、过滤低质量交易机会。

### Potential Risks

潜在风险包括但不限于 Leakage、过拟合、与已有 Feature 高度重复、对极端行情敏感、在不同市场状态下不稳定。

### Version

Feature 的版本号，用于记录计算方法或定义变化。

### Status

Feature 状态建议使用：

1. proposed
2. approved
3. implemented
4. tested
5. deprecated

## Feature 文档位置

未来 `docs/features/` 中每个 Feature 都应单独建档。

建议每个 Feature 文档以 Feature ID 和名称命名，例如：

```text
docs/features/FEAT001_return_momentum.md
```

## 准入规则

Feature 进入项目之前必须通过 Review。

Review 必须确认：

1. 是否描述明确市场现象
2. 是否只使用当前和过去数据
3. 是否存在未来函数风险
4. 是否与已有 Feature 重复
5. 是否有清晰实验目的
6. 是否能在失败后被解释和复盘
