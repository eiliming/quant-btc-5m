# Phase 5.14–5.19 Implementation

## Scope decision

The source design contains useful research principles but overlaps earlier
phases and sometimes crosses the Feature/Model boundary. This implementation
keeps one executable contract per responsibility.

## 5.14 Stability and regime adaptation

Feature experiments now optionally declare:

- `temporal_frequency`: `year`, `quarter`, or `month`;
- `regime_segments`: fixed numeric boundaries for already-built regime
  Features.

The runner evaluates each Feature overall and within each segment. It records
IC dispersion, mean absolute IC and sign consistency in Experiment metadata.
Regime values remain FeatureBuilder outputs; the ExperimentRunner only groups
them and never creates a market-state Feature. Fixed boundaries are config,
not hand-edited results.

Cross-asset stability is deferred until a traceable multi-asset Research
Dataset contract exists.

## 5.15 Lifecycle management

Lifecycle decisions are immutable `feature_review_vN` Artifacts. A review
records the current registry identity, decision, proposed status, rationale,
reviewer and evidence Artifact references. It does not overwrite the Feature
Registry or rewrite history.

Promotion requires Experiment evidence. Promotion to `approved` is blocked
until Phase 6 supplies model contribution and cost-aware backtest evidence.
Deprecation and archiving preserve lineage.

## 5.16 Experiment platform

The Phase 5 experiment remains a univariate information/stability experiment.
It now adds an approximate two-sided correlation p-value and Benjamini-Hochberg
q-value inside each split/segment, reducing false discovery risk when many
Features are tested.

Addition/removal/replacement experiments with a model baseline belong to the
Model OS because they train models. They must reuse identical Training Dataset,
Split, parameters and seeds in Phase 6; they are not silently implemented in
the Feature layer.

## 5.17 Offline store boundary

The immutable `feature_dataset_vN` is the offline Feature snapshot. A separate
copy called `snapshot` would duplicate the same values and lineage, so V1 does
not introduce it.

Training Dataset integration is deliberately not implemented in the current
Phase 5 scope. The contract stops at `feature_set_vN`; later work must bind the
Feature Dataset, Feature Set, Label and Split without moving that responsibility
into the Feature layer.

## 5.18 Pipeline engineering

Already present before this phase: registry discovery, dependency DAG,
topological execution, cycle rejection, pure calculators, lookback metadata,
Feature QA, immutable writes, CLI and regression tests.

The Feature CLI exposes build, inspect/list, experiment, selection-decision,
selection, lifecycle review and lifecycle status commands. Minimal Label and
chronological Split builders provide explicit Artifact boundaries for the real
Feature research loop. Training builders remain outside this phase.

Incremental append is intentionally not implemented: append would violate the
current immutable Artifact model. A future incremental builder must read old
and new inputs and emit a new full or partitioned Artifact version. Online
cache/serving and CI deployment are operational concerns, not prerequisites for
offline Model Research.

## 5.19 Alpha discovery governance

`FeatureResearchRecord` remains the human-to-system entry point. It requires an
observation, falsifiable hypothesis, horizon, validation metrics and failure
criteria. Automated parameter or formula search is not added to V1: search
spaces require experiment-family identity, multiple-testing accounting and
out-of-sample reservation first. The new q-values provide the first statistical
gate, but economic meaning and trading evidence remain mandatory.

## Commands

```text
python -m src.feature.cli build ...
python -m src.feature.cli experiment ...
python -m src.feature.cli decide ...
python -m src.feature.cli select ...
python -m src.feature.cli review ...
python -m src.feature.cli status ...
```

Every mutating Feature command emits a new Artifact version and refuses to
overwrite an existing Artifact directory.
