# Phase 5.9.7 Feature Framework Implementation Review

## Review Result

**Status: PASS**

Feature Framework V1 已通过真实 BTCUSDT 5m Research Dataset 的端到端 Smoke Test。框架具备进入 Phase 5.10 Feature Library Expansion 设计与工程工作的条件。

本结论只确认计算框架、Artifact、lineage 和确定性 QA 正确；首批 Feature 仍为 `experimental`，不代表已经证明预测价值或交易价值。

## Execution Context

- Review date: 2026-07-13
- Project: `quant-btc-5m Research OS`
- Source git commit recorded by Artifact: `721804d31ed9fc7ac3dcc687be8fa6caae0f6136`
- Unified entry: `python cli.py build-feature`

执行命令：

```bash
python cli.py build-feature \
  --dataset artifacts/research/datasets/binance_spot/BTCUSDT/5m/research_dataset_v1 \
  --features return_1,body_ratio,upper_wick_ratio,lower_wick_ratio,volume_ratio_20,volatility_20 \
  --output artifacts/feature/datasets/binance_spot/BTCUSDT/5m
```

## Input Artifact Review

Source Artifact：

```text
artifact_id: research_dataset_v1
artifact_type: research_dataset
content_hash: bf86cdc7d05ab0fd
run_id: e8781427b04547938a8aabfdecf7b28e
```

数据范围与质量：

| Check | Result |
|---|---:|
| Exchange / Symbol / Timeframe | binance_spot / BTCUSDT / 5m |
| Time range | 2023-04-01 00:00 UTC – 2026-06-30 23:55 UTC |
| Rows | 341,856 |
| Columns | timestamp, open, high, low, close, volume |
| Null values | 0 |
| Duplicate timestamps | 0 |
| Timestamp monotonic | PASS |
| Interval | 341,855 intervals are exactly 300,000ms |
| Source partitions | 39 |
| Monthly QA reports | 39 PASS / 0 FAIL |

## Output Artifact

```text
artifacts/feature/datasets/binance_spot/BTCUSDT/5m/feature_dataset_v2/
  data.parquet
  metadata.json
```

Identity：

```text
artifact_id: feature_dataset_v2
artifact_type: feature_dataset
content_hash: 3a64d0f2e7e210e2
run_id: 6f817b328f2f4d188c71bef2d555e19c
source_dataset: research_dataset_v1
```

File evidence：

| File | Bytes | SHA-256 |
|---|---:|---|
| `data.parquet` | 19,663,104 | `0843352334d2a5b2af263d5ae05e3673d005fc96ce8eadbafa8b8c858b1a70f6` |
| `metadata.json` | 15,153 | `38d60bde3f72aa29556375fa52c87bfe1ac071a79202088199ddebbf0c07f23e` |

## Parquet Validation

实际列：

```text
timestamp
return_1
body_ratio
upper_wick_ratio
lower_wick_ratio
volume_ratio_20
volatility_20
```

| Check | Result |
|---|---:|
| Feature rows | 341,856 |
| Row count equals source | PASS |
| Timestamp full-series equality | PASS |
| OHLCV excluded from Feature Dataset | PASS |
| Infinite values | 0 |
| Non-leading unexpected nulls | 0 |

Warm-up missing values：

| Feature | Missing | Expected |
|---|---:|---:|
| `return_1` | 1 | 1 |
| `body_ratio` | 0 | 0 |
| `upper_wick_ratio` | 0 | 0 |
| `lower_wick_ratio` | 0 | 0 |
| `volume_ratio_20` | 19 | 19 |
| `volatility_20` | 20 | 20 |

## Formula Validation

全部 341,856 行使用原始 OHLCV 独立重算并与 Feature Artifact 比较：

| Feature | Maximum absolute error | Result |
|---|---:|---|
| `return_1` | 0.0 | PASS |
| `body_ratio` | 0.0 | PASS |
| `upper_wick_ratio` | 0.0 | PASS |
| `lower_wick_ratio` | 0.0 | PASS |
| `volume_ratio_20` | 0.0 | PASS |
| `volatility_20` | 0.0 | PASS |

三个 candle ratio 的实际范围均为 `[0.0, 1.0]`。

## Metadata and Reproducibility

| Check | Result |
|---|---:|
| Standard Artifact metadata parsing | PASS |
| Recorded content hash | `3a64d0f2e7e210e2` |
| Independently recomputed content hash | `3a64d0f2e7e210e2` |
| Feature definitions and parameters recorded | PASS |
| Calculator class and version recorded | PASS |
| Market hypothesis and risks recorded | PASS |
| Source Artifact reference recorded | PASS |

## Immutability and Version Review

- Existing `feature_dataset_v1/data.parquet` and `metadata.json` remain present.
- 新执行生成 `feature_dataset_v2`，没有覆盖 v1。
- `_current.json.current == feature_dataset_v2`。
- `_current.json.history == [feature_dataset_v1, feature_dataset_v2]`。

Data OS 写保护证据：

```text
Scope: artifacts/raw + artifacts/research
File count before: 325
File count after: 325
Aggregate SHA-256 before: 65dee7a3aaca2203e205d274f388c92bb5b929fb346ced75040a0a776d174bb2
Aggregate SHA-256 after:  65dee7a3aaca2203e205d274f388c92bb5b929fb346ced75040a0a776d174bb2
Result: unchanged
```

## Lineage Review

Feature collection Registry 验证：

```text
feature_dataset_v2
  -> research_dataset_v1
```

- Direct upstream lookup: `research_dataset_v1`
- Downstream of Research Dataset: `feature_dataset_v1`, `feature_dataset_v2`
- Resolvable lineage: `research_dataset_v1`

Smoke Test 发现 collection-local Registry 在继续递归 Research Dataset 的 raw/QA 引用时，原实现会因未注册外部记录而抛出异常。本阶段已修正：

- 已注册的 lineage 正常返回
- 未注册的上游 ID 保留在 dependency graph
- `unresolved_upstream_ids()` 显式返回 `raw_kline`、`qa_report`

这些上游依赖可由 Research Dataset metadata 和 39 份 QA Report 继续审计。建立跨 collection 的全局 Registry identity 仍是 Core Artifact 层的后续改进项，不阻断 Feature Dataset 对正式 Research Dataset 的直接 lineage。

## Implementation Review

### Architecture

- Feature Definition 与 Calculator 分离：PASS
- Calculator 无文件 IO：PASS
- Calculator 不修改输入 DataFrame：PASS
- Engine 显式解析依赖：PASS
- Builder 独占 Artifact 写入职责：PASS
- Feature 不写 Data OS：PASS

### Code and Tests

- Formula、边界、dependency、cycle、no-mutation 测试：PASS
- Artifact version、metadata、Registry、reproducibility 测试：PASS
- 真实数据全量公式复核：PASS

## Required Fixes

本次 Review 无阻断 Phase 5.10 的必修问题。

后续非阻断事项：

1. 在 Core Artifact 阶段设计跨 collection 的全局 Registry identity，消除非版本化 `raw_kline/qa_report` ID 在不同 collection 间的歧义。
2. 在 Label、Split 可用后实现 Information Value、时间稳定性和冗余 QA。
3. 在 Training Dataset Builder 中实施只允许 Approved Feature 的状态门禁。

## Gate Decision

Phase 5.9.7 Review Gate：**PASS**。

项目可以进入 Phase 5.10 Feature Library Expansion。Phase 5.10 必须继续遵守：先提出市场现象与研究假设，再新增 Calculator、Registry Definition 和测试；不得把 Framework Smoke Test 结果解释为 Feature 的预测有效性证据。
