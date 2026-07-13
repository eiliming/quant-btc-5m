# Feature Schema

## Definition Schema

每个 Feature Definition 必须回答研究含义和工程执行两类问题。

| Field | Purpose |
|---|---|
| `name`, `version`, `feature_id` | 稳定身份，`feature_id = name:version` |
| `group` | 市场信息分类 |
| `description` | Feature 的简要含义 |
| `market_phenomenon` | 描述的市场现象 |
| `research_hypothesis` | 为什么值得观察 |
| `calculation_method` | 可审阅的计算定义 |
| `expected_effect` | 预期表达的信息，不是承诺收益 |
| `potential_risks` | 解释、数据和稳定性风险 |
| `inputs`, `outputs` | Calculator 数据契约 |
| `dependencies` | 上游 Feature 名称 |
| `parameters`, `lookback` | 可复现参数和历史窗口 |
| `calculator` | 实现类 |
| `status` | 生命周期状态 |

Schema 可表达：`experimental`、`validated`、`approved`、`deprecated`、`archived`。
但 Phase 5 Review 的最高可达状态是 `validated`；`approved` 仅作为跨阶段保留状态，
必须等待 Model OS 的增量贡献证据和成本后交易证据，不能由 Phase 5 写入。

Feature Definition 由 `src/feature/registry/features.yaml` 管理；Calculator 修改公式时必须新增 Feature version，禁止静默修改历史定义。

Registry 加载时拒绝未知字段、空值/重复的 inputs、outputs、dependencies、非 mapping
parameters、自依赖，以及多个 Feature 声明同一个 output。一个输出列只能有一个
Definition owner，避免 DAG 执行时发生隐式覆盖。

## Feature Dataset Metadata

Feature metadata 在标准 Artifact 字段之外包含：

```json
{
  "type": "feature_dataset",
  "version": "feature_dataset_v1",
  "source_dataset": {
    "artifact_id": "research_dataset_v1",
    "artifact_type": "research_dataset"
  },
  "features": []
}
```

`features` 记录实际执行的请求和依赖，包括 version、parameters、calculator version、输入输出、lookback 和研究治理字段。

## V1 Feature Set

| Feature | Phenomenon | Formula | Lookback |
|---|---|---|---:|
| `return_1` | 单周期价格运动 | `close / close.shift(1) - 1` | 1 |
| `body_ratio` | K 线方向控制 | `abs(close-open)/(high-low)` | 0 |
| `upper_wick_ratio` | 上方价格拒绝 | `(high-max(open,close))/(high-low)` | 0 |
| `lower_wick_ratio` | 下方价格拒绝 | `(min(open,close)-low)/(high-low)` | 0 |
| `volume_ratio_20` | 相对市场参与度 | `volume/rolling_mean(volume,20)` | 20 |
| `volatility_20` | 短期波动水平 | `rolling_std(return_1,20)` | 20 |

零振幅 K 线的 candle ratios 定义为 `0.0`。Rolling Feature 的 warm-up 缺失值必须只出现在序列开头，且不得超过声明 lookback。
