# Phase 5 Feature Engineering Status

## Design Progression

| Phase | Decision | Status |
|---|---|---|
| 5.1 | Market Phenomenon Taxonomy | Design complete |
| 5.2 | Phenomenon-to-Feature Mapping | Design complete |
| 5.3 | Feature Schema and bundle Artifact | Contract frozen for V1 |
| 5.4 | Registry, Engine, Calculator, Builder pipeline | V1 implemented |
| 5.5 | Feature QA layers | Designed; deterministic subset implemented |
| 5.6 | Research lifecycle and approval workflow | V1 evidence gates implemented |
| 5.7 | Engineering architecture | Frozen as `src/feature` |
| 5.8 | MVP implementation plan | Complete |
| 5.9.1–5.9.6 | Framework implementation specification | V1 implemented |
| 5.9.7 | Implementation review | Real BTCUSDT 5m Smoke Test passed |
| 5.10 | Feature Library expansion governance | V1 implemented |
| 5.11 | Observation-to-hypothesis research contract | V1 implemented |
| 5.12 | Config-driven univariate Feature experiments | V1 implemented |
| 5.13 | Evidence-driven Feature Set selection/versioning | V1 implemented |
| 5.14 | Temporal and fixed-boundary Regime stability | Evaluation V1 implemented; Regime Features pending |
| 5.15 | Selection and lifecycle evidence | V1 implemented through Feature Review |
| 5.16 | Feature experiment platform | Univariate V1 implemented; model A/B deferred |
| 5.17 | Feature Store and Training integration | Offline snapshot mapped to Feature Dataset; Training integration not implemented |
| 5.18 | Pipeline engineering | DAG/QA/CLI implemented; incremental/cache deferred |
| 5.19 | Alpha discovery methodology | Research contract and false-discovery gate implemented |
| 5.20 | Final architecture review | Complete at Feature Set boundary |

## Current Engineering Capability

```text
Research Dataset Artifact
  -> Feature Registry
  -> Dependency Resolution
  -> Pure Calculators
  -> Deterministic Feature QA
  -> Immutable Feature Dataset Artifact
  -> Artifact Registry lineage
  + Label Dataset Artifact
  + Chronological Split Artifact
  -> Feature Experiment Artifact
  -> Selection Decision Artifact
  -> Feature Set Artifact
  -> Feature Review Artifact and lifecycle status projection
```

Available Feature set: `return_1`, `body_ratio`, `upper_wick_ratio`, `lower_wick_ratio`, `volume_ratio_20`, `volatility_20`.

## Evidence

- Registry and governance schema: `src/feature/registry/`
- Calculator and dependency engine: `src/feature/calculator/`
- Artifact builder and deterministic QA: `src/feature/dataset/`
- Unified orchestration: `src/core/pipeline/pipeline.py` and `cli.py`
- Automated tests: `tests/feature/`

Automated synthetic end-to-end tests cover immutable version creation, metadata, dependency lineage and Registry lookup. The real BTCUSDT 5m Smoke Test generated `feature_dataset_v2` from 341,856 Research Dataset rows and passed full-series formula, timestamp, metadata, immutability and lineage checks. Evidence is recorded in `docs/research/PHASE_5_9_7_FEATURE_FRAMEWORK_REVIEW.md`.

The 5.10–5.13 implementation and its boundaries are specified in
`PHASE_5_10_5_13_FEATURE_RESEARCH_OS.md`.

## Formal Closure Evidence

- `label_dataset_v1` -> `split_v1` -> `experiment_v1` ->
  `selection_decision_v1` -> `feature_set_v1` -> `feature_review_v1..v6`
- Engineering Closure: PASS
- Research Acceptance: PASS
- Selected Feature: `return_1:v1`
- Full evidence: `docs/research/PHASE_5_CLOSURE_READINESS_AUDIT.md`

## Outside Closure or Non-blocking

- Model contribution and cost-aware backtest gates for approved status
- Training Dataset integration (Model OS boundary)
- Standalone historical Feature QA command beyond build-time validation
- Generic automated leakage detection and versioned distribution anomaly baselines
- Formal trend/range and high/low-volatility regime evidence
- Trading-value evaluation

These items do not block the completed Feature Research loop. Model contribution,
Training Dataset integration and trading-value evaluation remain outside the Feature OS
closure boundary and must not be reported as Phase 5 outputs.
