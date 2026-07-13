from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


CORRELATION_METHOD = "spearman"


def apply_correlation_pruning_and_budget(
    ordered_candidates: list[dict[str, Any]],
    validation_features: pd.DataFrame,
    *,
    maximum_abs_correlation: float,
    feature_budget: int,
    minimum_pairwise_samples: int,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Apply deterministic validation-only correlation pruning, then budget.

    ``ordered_candidates`` must already use the frozen evidence ranking. This
    function performs no Experiment gate or Artifact IO.
    """
    survivors: list[dict[str, Any]] = []
    outcomes: dict[str, dict[str, Any]] = {}
    correlation_summary: list[dict[str, Any]] = []

    for candidate in ordered_candidates:
        identity = str(candidate["feature_id"])
        name = str(candidate["feature"])
        comparisons: list[dict[str, Any]] = []
        for kept in survivors:
            kept_name = str(kept["feature"])
            pair = validation_features[[name, kept_name]].dropna()
            sample_count = len(pair)
            correlation: float | None = None
            if (
                sample_count >= minimum_pairwise_samples
                and pair[name].nunique() > 1
                and pair[kept_name].nunique() > 1
            ):
                raw = pair[name].corr(pair[kept_name], method=CORRELATION_METHOD)
                if np.isfinite(raw):
                    correlation = float(abs(raw))
            comparison = {
                "feature_id": identity,
                "kept_feature_id": str(kept["feature_id"]),
                "pairwise_sample_count": sample_count,
                "absolute_correlation": correlation,
            }
            comparisons.append(comparison)
            correlation_summary.append(comparison)

        invalid = [item for item in comparisons if item["absolute_correlation"] is None]
        finite = [item for item in comparisons if item["absolute_correlation"] is not None]
        maximum = max(
            (float(item["absolute_correlation"]) for item in finite),
            default=None,
        )
        if invalid:
            outcomes[identity] = {
                "decision": "rejected",
                "primary_reason": "insufficient_correlation_samples",
                "reason_codes": ["insufficient_correlation_samples"],
                "correlation_pruned_by": None,
                "maximum_observed_correlation": maximum,
                "rank": None,
            }
            continue

        violations = [
            item for item in finite
            if float(item["absolute_correlation"]) > maximum_abs_correlation
        ]
        if violations:
            blocker = sorted(
                violations,
                key=lambda item: (
                    -float(item["absolute_correlation"]),
                    str(item["kept_feature_id"]),
                ),
            )[0]
            outcomes[identity] = {
                "decision": "rejected",
                "primary_reason": "correlation_pruned",
                "reason_codes": ["correlation_pruned"],
                "correlation_pruned_by": str(blocker["kept_feature_id"]),
                "maximum_observed_correlation": float(blocker["absolute_correlation"]),
                "rank": None,
            }
            continue
        survivors.append(candidate)
        outcomes[identity] = {
            "decision": "pending_budget",
            "primary_reason": "accepted",
            "reason_codes": ["accepted"],
            "correlation_pruned_by": None,
            "maximum_observed_correlation": maximum,
            "rank": None,
        }

    for survivor_rank, candidate in enumerate(survivors, start=1):
        identity = str(candidate["feature_id"])
        outcome = outcomes[identity]
        outcome["rank"] = survivor_rank
        if survivor_rank <= feature_budget:
            outcome["decision"] = "accepted"
        else:
            outcome.update({
                "decision": "rejected",
                "primary_reason": "feature_budget_exhausted",
                "reason_codes": ["feature_budget_exhausted"],
            })
    return outcomes, correlation_summary
