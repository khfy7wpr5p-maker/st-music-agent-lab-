# A26 — Rollback execution receipt and recovery

A26 records a rollback only after an external host/human action. The ST Music Agent does not expose
serving credentials, a deployment switch, or a rollback executor to the model.

## Rollback execution receipt

`RollbackExecutionReceiptBuilder` recomputes the original A25 evidence before a receipt can exist:

- exact Baseline Registry record;
- exact drift observation windows;
- exact drift report;
- exact rollback review request.

A successful `rolled_back` receipt additionally requires:

- a non-empty host authorization reference;
- a non-empty external execution reference;
- supporting evidence references;
- observed serving model equal to the request's exact rollback target;
- observed checkpoint equal to the request's exact rollback checkpoint.

The receipt always keeps `auto_rollback=false` and `auto_switch=false`. It records what an external
host already did; it never performs the action.

## Post-rollback recovery

A successful receipt does not make the restored model a stable baseline by itself.
`PostRollbackRecoveryGate` requires at least two ordered observation rounds. Every round contains
exactly:

- `serving_identity`;
- `health`;
- `recovery`.

Serving identity must be the rollback target in every round. Health and recovery must both succeed.
Failure or unavailable evidence rejects baseline registration. A pass yields only
`eligible_for_baseline_registration` and preserves `auto_register_baseline=false`,
`auto_switch=false`, and `auto_rollback=false`.

## Baseline Registry rollback generation

`BaselineRegistry.register_rollback()` rechecks the A25 request, A26 rollback receipt, and A26
recovery report. It also requires the registry's current record to still be the degraded baseline
and requires the rollback target to be the exact predecessor already present in registry history.

A successful rollback is appended as a new `rollback` generation. The degraded canonical
generation remains in history. The rollback generation records:

- restored model/checkpoint;
- degraded source model/checkpoint;
- rollback execution receipt fingerprint;
- recovery report fingerprint;
- host registration reference and supporting evidence.

The rollback generation intentionally does not invent a new automatic fallback target. Future
production changes require fresh evidence and host review.

## Operational watch resume

The A25 operational state is extended through:

`baseline_bound -> drift_reviewed -> rollback_review_requested -> rollback_execution_recorded
-> post_rollback_recovery_reviewed -> rollback_baseline_registered`

A healthy watch can still stop at `drift_reviewed`. Rollback stages exist only when a separately
authorized rollback actually occurs.
