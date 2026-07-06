# Backtest Design Notes

本文档解释回测设计背景。执行规范与系统约束统一见 `AGENTS.md`。

## Purpose

回测用于评估模型概率信号和策略设定能否转化为交易表现。

模型指标描述预测质量，交易指标描述执行后的收益、风险和稳定性。

## Trading Factors

常见回测因素包括：

1. 手续费
2. 滑点
3. 持仓设定
4. 止盈止损

## Metrics

交易评估常见指标包括：

1. Return
2. Sharpe
3. MaxDrawdown
4. WinRate
5. Profit Factor
