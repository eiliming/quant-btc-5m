# Phase 5.10–5.13 Feature Research OS

## 1. Scope

This phase turns the existing Feature Calculator Framework into a small,
reproducible research loop:

```text
Market observation -> hypothesis -> registered Feature
  -> Feature Dataset Artifact
  -> Label Dataset Artifact + Split Artifact
  -> Experiment Artifact
  -> Feature Set Artifact
```

It does not promote any current Feature. Statistical evidence is an
intermediate gate; a later model and cost-aware backtest must still establish
trading value.

## 2. Phase 5.10: Library expansion

The Feature Library is a market-knowledge catalog, not an indicator list.
`src/feature/registry/features.yaml` remains its system of record. Every entry
declares its market phenomenon, hypothesis, calculation, expected effect,
risks, lookback, implementation version and lifecycle status. Families describe
market behavior (`price`, `candle`, `volume`, `volatility`, and later trend,
momentum, structure and regime).

Expansion rules:

1. Start from an observation and falsifiable hypothesis.
2. Prefer a continuous representation before threshold combinations.
3. Register the definition before building a Feature Dataset.
4. Keep new Features `experimental` until formal evidence exists.
5. Deprecate rather than delete historical definitions.

## 3. Phase 5.11: discovery workflow

`FeatureResearchRecord` is the review contract from observation to proposed
Feature. It requires IDs, market/timeframe, context, expected effect,
prediction horizon, validation metrics and explicit failure criteria. This is a
design record, not permission to train or promote a Feature.

Research review asks:

- Is the phenomenon economically interpretable?
- Can every input exist at decision time?
- Which Label and horizon test the claim?
- Which Split Artifact prevents temporal leakage?
- What result rejects the hypothesis?
- How will evidence and the next action be archived?

## 4. Phase 5.12: experiment framework

`python -m src.feature.cli experiment --config ... --output ...` executes a
declarative experiment. The runner only consumes immutable `feature_dataset`,
`label_dataset`, and `split` Artifacts. It never calculates a Feature or Label.
Inputs are joined one-to-one by timestamp and duplicate timestamps are rejected.

V1 produces per-Feature, per-split sample count, missing rate, Pearson IC,
Spearman IC, directional win rate and Label distribution statistics. The
result is an immutable, auto-versioned `experiment_vN` Artifact whose metadata
records objective, hypothesis, seed, conclusion, next action and full lineage.

V1 is deliberately a univariate information test. It is not model validation
or a trading simulation.

Example config:

```yaml
objective: Test whether price/volume observations contain out-of-sample information.
hypothesis_id: HYP_VOLUME_REVERSAL_001
feature_artifact: artifacts/feature/datasets/feature_dataset_v3
label_artifact: artifacts/label/datasets/label_dataset_v1
split_artifact: artifacts/split/split_v1
features: [lower_wick_ratio, volume_ratio_20]
label_column: future_return_1
split_column: split
evaluation_splits: [train, validation, test]
random_seed: 42
minimum_samples: 1000
conclusion: Pending evidence review.
next_action: Apply the declared Feature selection gate, then review trading relevance.
```

## 5. Phase 5.13: selection and dimensionality

`python -m src.feature.cli select --config ... --output ...` creates a
versioned `feature_set_vN` Artifact. Selection is deterministic and evidence
driven:

1. Filter by missing rate and absolute out-of-sample Spearman IC.
2. Rank remaining candidates by absolute Spearman IC.
3. Remove pairwise Spearman redundancy, keeping the higher-ranked Feature.
4. Enforce a declared Feature budget.
5. Store every accept/reject decision in metadata.

The selector verifies that the Experiment Artifact directly references the
configured Feature Dataset. A Feature Set contains identities and family names,
not recalculated values.

```yaml
objective: Build a compact non-redundant baseline Feature space.
feature_artifact: artifacts/feature/datasets/feature_dataset_v3
experiment_artifact: artifacts/experiments/experiment_v1
evaluation_split: test
candidates: [return_1, body_ratio, lower_wick_ratio, volume_ratio_20]
feature_budget: 20
minimum_abs_spearman_ic: 0.01
maximum_missing_rate: 0.05
maximum_abs_correlation: 0.90
```

Thresholds above are examples, not approved research decisions. Production
promotion additionally requires temporal stability, regime review, incremental
model contribution and cost-aware backtesting.

## 6. Acceptance and failure gates

An experiment is invalid if inputs are not typed Artifacts, timestamps are
duplicated, configured splits are absent, sample size is below the declared
minimum, or lineage is incomplete. A Feature must not be promoted merely
because it passes an IC threshold. Failure evidence remains an immutable
research fact and should inform deprecation or hypothesis revision.

## 7. Current boundary

Implemented: contracts, config loading, typed input validation, standardized
univariate evaluation, immutable Experiment Artifacts, deterministic reduction,
Feature budgets, immutable Feature Set Artifacts, CLI and tests.

Deferred: regime-specific evaluation, rolling stability score, conditional
analysis, wrapper/embedded selection, model training, strategy rules and
cost-aware backtesting. These require their own configs and Artifact builders.
