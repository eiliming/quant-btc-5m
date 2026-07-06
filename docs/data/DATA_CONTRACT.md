# Dataset Artifact Contract

本文档解释 Dataset Artifact 的结构。执行规范与系统约束统一见 `AGENTS.md`。

## Scope

- Exchange: Binance
- Market Type: Spot
- Symbols: BTCUSDT, ETHUSDT
- Timeframes: 1m, 5m, 15m, 30m, 1h, 4h
- Data Type: OHLCV kline
- Timezone: UTC

## Raw Kline Artifact

Raw kline artifact 表示直接来自交易所接口的市场事实。

路径形态：

```text
artifacts/raw/{exchange}/{symbol}/{timeframe}/YYYY/MM/
```

`data.parquet` 字段：

| Field | Type | Description |
|---|---|---|
| timestamp | int64 | Kline open time in UTC milliseconds |
| open | float64 | Open price |
| high | float64 | High price |
| low | float64 | Low price |
| close | float64 | Close price |
| volume | float64 | Base asset volume |
| is_closed | bool | Whether the candle is closed |

## Research Dataset Artifact

Research dataset artifact 表示面向研究阶段的标准 OHLCV 数据集。

路径形态：

```text
artifacts/research/datasets/{exchange}/{symbol}/{timeframe}/{artifact_id}/
```

`data.parquet` 字段：

```text
timestamp, open, high, low, close, volume
```

相比 raw kline，research dataset 更关注统一 schema、连续时间序列和后续 Feature / Label 阶段的输入便利性。

## Metadata Model

Dataset metadata 将数据身份、来源、生成方式、配置和统计摘要组织在一起。

常见信息包括：

- exchange
- symbol
- timeframe
- schema version
- source partitions
- time range
- row count
