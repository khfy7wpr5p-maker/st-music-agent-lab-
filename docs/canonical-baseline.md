# A23 — Canonical Baseline Review and Receipt

A23 closes the boundary between an A22 runtime-health pass and a real canonical-baseline change.
It does not expose a deployment, serving-switch, rollback-executor or canonicalization tool to a
model.

## Canonical baseline review

`CanonicalBaselineReviewGate` requires the exact A22 evidence set:

- activated `ActivationReceipt`;
- the exact four runtime checks;
- the claimed `ShadowHealthReport`;
- the currently authoritative canonical model id and checkpoint SHA-256.

The gate reruns `ShadowHealthGate.verify()` before making its own decision. This prevents a stale,
forged or altered A22 report from becoming a canonicalization path.

A review is eligible only when:

- A22 is `eligible_for_canonical_review`;
- the current canonical identity still equals the pre-activation baseline;
- the rollback model/checkpoint still equal that same canonical baseline.

An eligible review means only `eligible_for_host_canonicalization`. It always keeps:

- `human_approval_required=true`;
- `canonicalization_authorized=false`;
- `auto_canonicalize=false`.

## Canonicalization receipt

`CanonicalizationReceiptBuilder` records a separately authorized host action. Before recording the
result it independently recomputes the A23 review from the original A22 receipt/checks/report.

The receipt binds:

- exact A23 review fingerprint;
- target candidate id/checkpoint;
- previous canonical id/checkpoint;
- rollback id/checkpoint;
- target environment;
- host authorization reference;
- host canonicalization reference;
- explicit evidence references;
- observed canonical id/checkpoint.

Outcomes are `canonicalized`, `failed` or `rolled_back`.

For `canonicalized`, the observed canonical identity must exactly equal the candidate and
`post_canonical_health_required=true`. For `rolled_back`, the observed canonical identity must
exactly equal the previous baseline. A failed change may either have no reliable observed identity
or may observe only the unchanged previous baseline.

Receipts never enable automatic canonicalization or rollback.

## Resumable orchestration

A23 extends the hash-chained lifecycle after A22:

`shadow_health_reviewed -> canonical_reviewed -> canonicalization_recorded`

Only fingerprints are persisted. Existing evidence remains immutable and stage skipping fails
closed.

## Next boundary

A24 should add post-canonical health/stability evidence and a baseline registry snapshot so a newly
canonical model must prove sustained health before it becomes the unquestioned default for future
training/evaluation cycles.
