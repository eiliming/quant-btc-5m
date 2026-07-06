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
artifacts/raw/{exchange}/{symbol}/{timeframe}/{artifact_id}/
```

年月分区不再作为正式 raw artifact 目录层级。分区身份保存在 `metadata.json`：

- `config.partition`: `YYYY/MM`
- `config.start_time`
- `config.end_time`
- `config.exchange`
- `config.symbol`
- `config.timeframe`

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

所有 Artifact metadata 必须包含标准字段：

```json
{
  "artifact_id": "...",
  "artifact_type": "...",
  "created_at": "...",
  "inputs": [
    {
      "artifact_id": "...",
      "artifact_type": "..."
    }
  ],
  "provenance": {
    "builder": "...",
    "version": "...",
    "git_commit": "..."
  },
  "config": {},
  "stats": {}
}
```

`inputs` 是 Artifact dependency list，只能保存上游 artifact reference，不能保存路径字符串或非结构化输入来源。路径、分区、schema version、交易对和时间范围属于 `config` 或 `stats`。

常见 config/stats 信息包括：

- exchange
- symbol
- timeframe
- schema version
- source partitions
- time range
- row count

Research dataset artifact 的 `inputs` 至少应包含被消费的 raw kline artifact 和对应 QA report artifact，形成可追溯 DAG。
