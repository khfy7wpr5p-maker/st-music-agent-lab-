# A22 — Activation Receipt and Shadow Health

A22 records post-review runtime evidence without giving the model deployment or canonicalization authority.

## Activation receipt

`ActivationReceiptBuilder` does not deploy a model. It records the result of an externally executed,
separately authorized host action and binds it to the exact A21 activation request.

An activated receipt binds:

- activation request id + fingerprint;
- candidate id + checkpoint SHA-256;
- target environment;
- previous baseline id + checkpoint;
- exact rollback id + checkpoint;
- host authorization reference;
- deployment reference;
- explicit evidence references;
- observed serving model id + checkpoint.

For `activated`, the observed serving identity must equal the requested candidate. For
`rolled_back`, it must equal the rollback target. A `failed` receipt cannot claim a serving model.

Every receipt keeps:

- `canonicalization_authorized=false`;
- `auto_canonicalize=false`.

An activated receipt additionally requires post-activation shadow/health review.

## Shadow health gate

`ShadowHealthGate` requires exactly one evidence-bearing check for each category:

1. `serving_identity`
2. `health`
3. `shadow_quality`
4. `rollback_readiness`

Each check is `success`, `failure` or `unavailable`. Any failure or unavailable result rejects the
candidate. Only four successful checks yield `eligible_for_canonical_review`.

That result is still not permission to replace the canonical baseline. Reports always keep:

- `human_review_required=true`;
- `canonicalization_authorized=false`;
- `auto_canonicalize=false`.

The report is deterministic and may be independently recomputed from the same receipt and checks.

## Orchestration

A22 extends the resumable state after `activation_requested` with:

- `activation_recorded`
- `shadow_health_reviewed`

Only fingerprints are persisted. Prior lifecycle evidence remains immutable in the hash-chained
journal.

## Authority boundary

A22 adds no deployment credentials, serving switch tool, rollback executor or canonicalization tool.
Actual activation, rollback and canonical-baseline replacement remain separate host/human actions.
