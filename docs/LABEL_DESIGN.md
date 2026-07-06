# Label Design

本文档解释 Label 的设计概念。执行规范与系统约束统一见 `AGENTS.md`。

## Concept

Label 定义了监督学习中的目标变量。

在本项目中，Label 用于表达未来一段时间内的收益、方向或经过过滤后的分类目标。

## Raw Label Example

```text
future_return = close[t+1] / close[t] - 1
```

## V1 Label Idea

V1 可以使用过滤横盘后的二分类思想：

```text
future_return > threshold => 1
future_return < -threshold => 0
abs(future_return) <= threshold => dropped
```

## Research Role

Label 决定了模型正在学习的问题。

不同 horizon、threshold 和过滤方式会形成不同研究问题，也会显著影响模型指标和交易解释。
