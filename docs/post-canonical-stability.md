# A24 — Post-Canonical Stability and Baseline Registry

A24 closes the evidence gap after A23 records an externally authorized canonical-baseline change.
It does not deploy, switch, canonicalize, or roll back a model.

## Post-canonical stability gate

A successful A23 canonicalization receipt must be followed by at least three independent observation
rounds before the new canonical model is eligible for baseline-registry recording. Each round must
contain the exact required checks:

- `serving_identity`
- `health`
- `quality`
- `rollback_readiness`

Every check carries explicit evidence references. Observation sequences must be contiguous from one,
observation references must be unique, and the observed model/checkpoint must match the A23
canonicalized candidate exactly.

Any failed or unavailable check, wrong model identity, wrong checkpoint, missing check, duplicate
check kind, insufficient round count, or altered report prevents a passing stability decision.

A pass yields only `eligible_for_baseline_registration`. It keeps:

- `host_registration_required=true`
- `auto_register_baseline=false`
- `auto_rollback=false`

## Baseline Registry

`BaselineRegistry` is an append-only, SHA-256 hash-chained host record of canonical baseline
lineage for one environment.

The registry must be explicitly bootstrapped with the already-existing canonical baseline and host
evidence. A later canonicalization can be appended only when:

1. the A23 receipt verifies and has outcome `canonicalized`;
2. the A24 stability report recomputes from the exact observation rounds;
3. the report is eligible for baseline registration;
4. the registry's current model/checkpoint exactly match the A23 previous canonical baseline; and
5. the A23 rollback target exactly matches that registered predecessor.

Each transition records the new model/checkpoint, previous model/checkpoint, rollback target,
canonicalization receipt fingerprint, stability report fingerprint, host registration reference and
supporting evidence references.

The registry exposes history/current state only. It has no deployment, model-switch, automatic
rollback, or automatic canonicalization capability.

## Resumable lifecycle

A24 extends the orchestration chain with two ordered stages:

`canonicalization_recorded -> post_canonical_stability_reviewed -> baseline_registered`

Only SHA-256 evidence fingerprints are persisted in the orchestration state. Existing evidence
remains immutable and stage skipping fails closed.
