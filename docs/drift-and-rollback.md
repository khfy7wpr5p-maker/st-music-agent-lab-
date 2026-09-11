# A25 — Drift Watch and Rollback Review

A25 adds a guarded operational loop after A24 baseline registration. It does not execute rollback.

## Drift watch

`DriftWatchGate` binds every observation to the exact registered baseline model/checkpoint and
requires at least four ordered observation windows. Every window must contain exactly one:

- serving identity check;
- health check;
- quality check;
- distribution-drift check;
- rollback-readiness check.

A single degraded window does not open rollback review. The default policy requires degradation in
at least two consecutive windows and requires the latest window to remain degraded. Serving
identity must remain exact and rollback readiness must remain stable. Unavailable evidence yields
`observe`, not rollback eligibility.

Possible decisions are:

- `healthy`;
- `observe`;
- `eligible_for_rollback_review`.

Every report keeps `rollback_authorized=false` and `auto_rollback=false`.

## Rollback review request

`RollbackReviewRequestBuilder` recomputes the drift report from the original windows. A request can
only be created from `eligible_for_rollback_review` evidence and only when the registered baseline
contains an exact predecessor/rollback model and checkpoint.

The request binds:

- current baseline record fingerprint;
- drift report fingerprint;
- current model/checkpoint;
- exact predecessor rollback model/checkpoint;
- evidence references.

It always keeps `human_approval_required=true`, `rollback_authorized=false` and
`auto_rollback=false`. No model-facing rollback executor is added.

## Operational watch state

Drift monitoring is recurring operational work rather than another model-training stage. A25 uses
a separate hash-chained `OperationalWatchStateStore`:

```text
baseline_bound -> drift_reviewed -> rollback_review_requested
```

A healthy watch may stop at `drift_reviewed`. A future watch cycle may bind the same still-current
baseline under a new watch id. Stage skipping, baseline replacement and evidence replacement fail
closed.

## Safety boundary

A25 produces evidence and review eligibility only. Actual serving changes, rollback credentials,
rollback execution and post-rollback verification remain outside model-callable tools and require
a separate host-controlled boundary.
