# Data Contract

## V1 Data Scope

- Exchange: Binance
- Market Type: Spot
- Symbol: BTCUSDT
- Timeframe: 5m
- Data Type: OHLCV Kline
- Timezone: UTC

## Why Binance Spot

V1 选择 Binance Spot 的原因：

- 数据结构简单
- 交易逻辑简单
- 不涉及 funding rate、open interest、liquidation、mark price 等合约特有字段
- 更适合作为第一版研究闭环的数据基础
- 后续如果项目切换到 Futures，需要重新定义 Data Contract

注意：Binance Spot 适合作为 V1 基础数据源，但不应表述为 Binance Spot 一定代表真实价格。

## Raw Kline Fields

每一行 K 线数据只保存市场事实字段：

| Field | Type | Description |
|---|---|---|
| timestamp | int64 | K线开盘时间，UTC milliseconds |
| open | float | 开盘价 |
| high | float | 最高价 |
| low | float | 最低价 |
| close | float | 收盘价 |
| volume | float | 成交量，base asset volume |
| is_closed | bool | 该K线是否已经闭合 |

## Metadata Fields

以下字段属于文件级或数据集级 metadata，不应在每行K线中重复保存：

| Field | Description |
|---|---|
| exchange | binance |
| market_type | spot |
| symbol | BTCUSDT |
| timeframe | 5m |
| timezone | UTC |
| source | Binance Spot API or exported archive |
| download_time | 数据下载时间 |
| data_version | 数据版本编号，例如 DS0001 |

## Directory Convention

原始数据目录采用：

```text
data/raw/{exchange}/{market_type}/{symbol}/{timeframe}/
```

例如：

```text
data/raw/binance/spot/BTCUSDT/5m/
```

后续如果加入其他市场，可以扩展为：

```text
data/raw/binance/futures/BTCUSDT/5m/
data/raw/okx/spot/BTCUSDT/5m/
data/raw/bybit/futures/BTCUSDT/5m/
```

## File Naming Convention

原始K线文件建议命名为：

```text
BTCUSDT_5m_YYYY-MM-DD_YYYY-MM-DD.csv
```

例如：

```text
BTCUSDT_5m_2023-01-01_2026-01-01.csv
```

对应 metadata 文件：

```text
BTCUSDT_5m_2023-01-01_2026-01-01.meta.json
```

## Important Rules

1. timestamp 必须使用 UTC milliseconds。
2. timestamp 表示 K线 open time。
3. 不允许使用本地时区作为主时间字段。
4. 不允许在未闭合K线上生成训练样本。
5. 不允许在 raw data 中加入 feature 或 label 字段。
6. exchange、symbol、timeframe 等元信息放在路径和 metadata 中，不在每行重复保存。
7. Raw data 必须保持尽可能接近原始市场数据。
