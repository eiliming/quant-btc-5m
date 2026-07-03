# Label 设计

## Raw Label

```text
future_return = close[t+1] / close[t] - 1
```

## V1 Label

V1 采用过滤横盘后的二分类。

```text
future_return > threshold 标记为 1
future_return < -threshold 标记为 0
abs(future_return) <= threshold 的样本丢弃
```

## Threshold

threshold 后续通过数据分布和交易成本共同决定。
