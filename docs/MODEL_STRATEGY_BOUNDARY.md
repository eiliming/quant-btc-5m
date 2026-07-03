# 模型与策略边界

## 模型层

模型层只负责输出 `p_up`。

模型不直接决定买卖。

## 策略层

策略层根据 `p_up` 阈值决定开多、开空或不交易。

示例：

```text
p_up > upper_threshold 做多
p_up < lower_threshold 做空
中间不交易
```

## 评估指标

模型指标包括：

1. Precision
2. LogLoss
3. AUC

交易指标包括：

1. Return
2. Sharpe
3. MaxDrawdown
4. WinRate
5. Profit Factor
