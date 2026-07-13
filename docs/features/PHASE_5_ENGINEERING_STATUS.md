# Phase 5 Feature Engineering Status

## Design Progression

| Phase | Decision | Status |
|---|---|---|
| 5.1 | Market Phenomenon Taxonomy | Design complete |
| 5.2 | Phenomenon-to-Feature Mapping | Design complete |
| 5.3 | Feature Schema and bundle Artifact | Contract frozen for V1 |
| 5.4 | Registry, Engine, Calculator, Builder pipeline | V1 implemented |
| 5.5 | Feature QA layers | Designed; deterministic subset implemented |
| 5.6 | Research lifecycle and approval workflow | Documented; experiment gates pending |
| 5.7 | Engineering architecture | Frozen as `src/feature` |
| 5.8 | MVP implementation plan | Complete |
| 5.9.1–5.9.6 | Framework implementation specification | V1 implemented |
| 5.9.7 | Implementation review | Real BTCUSDT 5m Smoke Test passed |

## Current Engineering Capability

```text
Research Dataset Artifact
  -> Feature Registry
  -> Dependency Resolution
  -> Pure Calculators
  -> Deterministic Feature QA
  -> Immutable Feature Dataset Artifact
  -> Artifact Registry lineage
```

Available Feature set: `return_1`, `body_ratio`, `upper_wick_ratio`, `lower_wick_ratio`, `volume_ratio_20`, `volatility_20`.

## Evidence

- Registry and governance schema: `src/feature/registry/`
- Calculator and dependency engine: `src/feature/calculator/`
- Artifact builder and deterministic QA: `src/feature/dataset/`
- Unified orchestration: `src/core/pipeline/pipeline.py` and `cli.py`
- Automated tests: `tests/feature/`

Automated synthetic end-to-end tests cover immutable version creation, metadata, dependency lineage and Registry lookup. The real BTCUSDT 5m Smoke Test generated `feature_dataset_v2` from 341,856 Research Dataset rows and passed full-series formula, timestamp, metadata, immutability and lineage checks. Evidence is recorded in `docs/research/PHASE_5_9_7_FEATURE_FRAMEWORK_REVIEW.md`.

## Not Yet Complete

- Label-aware information value and stability QA
- Feature approval enforcement in Training Dataset Builder
- Feature inspect/list/qa lifecycle CLI
- Baseline Feature Set research experiment
- Trading-value evaluation

These items belong to the next research loop and must not be reported as completed by Framework V1.
