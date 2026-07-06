# Data Contract

## V1 Data Scope

- Exchange: Binance
- Market Type: Spot
- Symbol: BTCUSDT, ETHUSDT
- Timeframe: 1m, 5m, 15m, 30m, 1h, 4h
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
| exchange | binance_spot |
| symbol | BTCUSDT or ETHUSDT |
| timeframe | 1m, 5m, 15m, 30m, 1h, or 4h |
| timezone | UTC |
| source | binance_spot_klines_api |
| start_time | 分区下载区间开始时间，UTC ISO-8601，左闭 |
| end_time | 分区下载区间结束时间，UTC ISO-8601，右开 |
| partition | 分区标识，例如 2024/01 |
| status | 下载状态，例如 completed 或 failed |
| rows_downloaded | 下载写入行数 |
| created_at | 下载完成时间，UTC ISO-8601 |
| force | 是否为强制重新下载 |
| data_file | 数据文件名，当前为 klines.parquet |
| schema_version | 数据结构版本，例如 v1 |
| downloader_version | Downloader 版本，例如 v1 |
| error_message | 失败原因，仅失败时记录 |
| failed_at | 下载失败时间，仅失败时记录 |

`schema_version` 表示字段结构版本，例如 `v1`。

V1 Downloader 的 metadata 只描述下载过程，不记录 QA、Feature、Label 或训练信息。

## Primary Key

在同一个 exchange / symbol / timeframe 数据文件中：

- timestamp 是唯一主键
- timestamp 表示 K线 open time
- 不允许存在重复 timestamp
- QA 阶段必须检查重复 timestamp

## Raw Data Immutability

Raw Data 必须不可修改。

任何清洗、修正、补全、过滤、异常处理，都不能覆盖 raw data。

所有处理结果必须生成新的 processed dataset。

Raw Data 的作用是保留最接近原始市场事实的数据来源。

## Data Lifecycle

数据生命周期如下：

```text
Raw
↓
Validated
↓
Processed
↓
Feature Ready
↓
Archived
```

每个阶段含义：

- Raw：原始下载数据
- Validated：通过 QA 检查的数据
- Processed：经过清洗或标准化的数据
- Feature Ready：可用于生成 Feature 和 Label 的数据
- Archived：冻结归档的数据版本

## Data Quality Responsibility

数据质量职责边界如下：

- Downloader 只负责下载和保存 raw data
- QA 模块负责检查完整性、一致性、重复、异常、时间间隔
- Process 模块负责生成 processed dataset
- Feature 模块只能消费 validated / processed 数据，不应该修复 raw data 问题
- Label 模块不能直接修改 raw data

## Directory Convention

原始数据目录采用：

```text
data/raw/{exchange}/{symbol}/{timeframe}/YYYY/MM/
```

例如：

```text
data/raw/binance_spot/BTCUSDT/5m/2024/01/
```

V1 Downloader 对应的临时写入目录采用：

```text
data/tmp/{exchange}/{symbol}/{timeframe}/YYYY/MM/
```

Downloader 必须先写入 tmp 分区，成功写入数据文件和 completed metadata 后，再将整个月分区移动到 raw。

V1 raw partition 必须代表完整月份数据。Downloader API 和 CLI 只接受 UTC 月初边界：

- `start_time` 必须是 UTC 月初 `00:00:00`
- `end_time` 必须是 UTC 月初 `00:00:00`
- `start_time < end_time`

禁止将部分月份数据写入 `YYYY/MM` raw 分区。

## File Naming Convention

每个月 raw 分区固定包含：

```text
klines.parquet
metadata.json
```

例如：

```text
data/raw/binance_spot/BTCUSDT/5m/2024/01/klines.parquet
data/raw/binance_spot/BTCUSDT/5m/2024/01/metadata.json
```

## Important Rules

1. timestamp 必须使用 UTC milliseconds。
2. timestamp 表示 K线 open time。
3. 不允许使用本地时区作为主时间字段。
4. 不允许在未闭合K线上生成训练样本。
5. 不允许在 raw data 中加入 feature 或 label 字段。
6. exchange、symbol、timeframe 等元信息放在路径和 metadata 中，不在每行重复保存。
7. Raw data 必须保持尽可能接近原始市场数据。
8. Raw Data is immutable.
9. schema_version 必须记录在 metadata 中。
10. Feature 和 Label 不允许直接依赖未经 QA 的 raw data。
11. 所有数据修正必须生成新的数据版本，而不是覆盖旧文件。
12. Downloader 不负责 QA，不在 raw data 或 metadata 中写入 qa_passed、missing_bars、feature_version、label_version 等字段。
13. 已完成 raw 分区默认跳过；需要重新下载时必须删除整月分区后重下，不能局部修改 raw 文件。
14. `metadata.status = completed` 只有在 `metadata.json` 存在、`klines.parquet` 存在且文件大小大于 0 时才视为可跳过。
15. `force=True` 必须先完成 tmp 下载与 completed metadata 写入，再替换 raw 分区；如果下载或 tmp 写入失败，必须保留原 raw 分区。
