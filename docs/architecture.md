# ST Music Agent Lab — Architecture Map

Status: A1-A25 guarded agent + verified planning/learning/evaluation/data/training/model-runtime/canonical-baseline-stability/drift foundation
Date: 2026-09-11

## Purpose

ST Music Agent Lab is a model-agnostic engineering and music-intelligence agent layer. Models,
OpenHands, GitHub and ST music projects attach through explicit adapters while ST-owned policy,
tool, budget, approval, evidence, verification, learning, evaluation, execution, dataset,
training, model-candidate, orchestration, activation, canonical-baseline, stable-baseline registry
and operational-drift boundaries remain authoritative.

## A1-A11 — Guarded execution

- task/model/action contracts and deterministic privilege policy;
- provider/OpenHands boundaries, repository-confined workspace and hardened sandbox;
- explicit `ToolRegistry`, bounded/redacted output and SHA-256 hash-chained journal;
- reversible feature-branch mutation only, run budgets and exact one-shot host approvals;
- restricted OpenHands bridge with no raw terminal/editor authority.

## A12-A13 — Four-project music evidence

Read-only source-provenanced snapshots cover Score Restore, MusicXML/Guitar TAB, Score Editor and
Real-Time Score Following. Evidence is authority-bounded: evaluation does not imply production,
REVIEW_REQUIRED does not imply canonical export, editor completion does not imply release/cutover
and research evidence does not imply pedagogical or production authority.

## A14-A18 — Planning, learning and curated data

- A14: deterministic portfolio planner + independent recomputation verifier;
- A15: host-write-only verified experience store with advisory learning only;
- A16: paired baseline/candidate benchmark gate with zero-regression policy;
- A17: exact execution evidence bound to plan, repository, branch, commit, CI and validators;
- A18: curated structured dataset export with training/promotion authority kept false.

## A19-A20 — Training and model candidate lineage

A19 binds an exact dataset manifest, base-model artifact, trainer config, seed and training-code
commit into one reproducible training input fingerprint. A separately authorized completed run
binds a checkpoint SHA-256 to that exact input.

A20 registers immutable model candidate lineage and independently recomputes A16 before a model can
become `eligible_for_activation_review`. Activation remains unauthorized.

## A21 — Activation request + resumable orchestration

A21 adds a hash-chained `OrchestrationStateStore` and an explicit activation request. The request
binds exact candidate, current baseline and rollback identities but always keeps
`activation_authorized=false`, `auto_activate=false` and `canonicalization_authorized=false`.

## A22 — Activation receipt + runtime health

A22 records separately executed host activation outcomes and requires four runtime checks:

- serving identity;
- health;
- shadow quality;
- rollback readiness.

All four must succeed to become only `eligible_for_canonical_review`. No deployment, rollback or
canonicalization executor is model-callable.

## A23 — Canonical baseline review + canonicalization receipt

`CanonicalBaselineReviewGate` receives the exact A22 activation receipt, exact runtime checks and
claimed shadow-health report, then reruns A22 verification. It also verifies that the currently
authoritative canonical baseline and rollback target still equal the pre-activation baseline.

A pass yields only `eligible_for_host_canonicalization`. The review always has:

- `human_approval_required=true`;
- `canonicalization_authorized=false`;
- `auto_canonicalize=false`.

`CanonicalizationReceiptBuilder` records a separately authorized host canonical-baseline action.
Before recording it, the builder recomputes the A23 review from the original A22 evidence.

The receipt binds exact old/new baseline identities, rollback identity, environment, host approval,
canonicalization reference and evidence. Outcomes are `canonicalized`, `failed` and `rolled_back`.
A successful canonicalization requires the observed canonical id/checkpoint to exactly equal the
candidate and sets `post_canonical_health_required=true`.

Automatic canonicalization and automatic rollback remain false.

## A24 — Post-canonical stability + Baseline Registry

A24 does not treat a successful A23 canonicalization as a stable endpoint. The
`PostCanonicalStabilityGate` requires at least three ordered observation rounds. Each round must
contain the exact evidence-bearing checks:

- `serving_identity`;
- `health`;
- `quality`;
- `rollback_readiness`.

Observation references must be unique, sequences must be contiguous from one, and the observed
model/checkpoint must equal the canonicalized candidate exactly. Any failed or unavailable check,
wrong identity, missing check or altered report rejects stability.

A pass yields only `eligible_for_baseline_registration` and preserves:

- `host_registration_required=true`;
- `auto_register_baseline=false`;
- `auto_rollback=false`.

`BaselineRegistry` is an append-only SHA-256 hash-chained host record for one environment. It must
be explicitly bootstrapped with the already-existing canonical model. A later generation can be
appended only when the exact A23 receipt and A24 stability report recompute successfully and the
registry's current model/checkpoint equal the A23 previous canonical baseline and rollback target.

Each transition records exact new/previous/rollback model identities, checkpoints,
canonicalization receipt fingerprint, stability report fingerprint, host registration reference
and supporting evidence. The registry records state only; it cannot deploy, switch or roll back a
model.

## A25 — Long-term drift watch + rollback review request

A25 adds operational monitoring for an already-registered canonical baseline. `DriftWatchGate`
requires at least four ordered observation windows. Every window contains exactly one:

- `serving_identity`;
- `health`;
- `quality`;
- `distribution`;
- `rollback_readiness`.

Serving identity must remain the exact Baseline Registry model/checkpoint. Unavailable evidence
cannot open rollback review. A single degraded window is insufficient: the default versioned
policy requires at least two consecutive degraded windows and requires the latest window to remain
degraded. Rollback readiness must remain stable across the complete watch evidence.

Possible decisions are `healthy`, `observe` and `eligible_for_rollback_review`. Even the last state
keeps `rollback_authorized=false` and `auto_rollback=false`.

`RollbackReviewRequestBuilder` independently recomputes the drift report and then binds the request
to the exact Baseline Registry predecessor model/checkpoint. The request always keeps
`human_approval_required=true`, `rollback_authorized=false` and `auto_rollback=false`. No rollback
executor or serving credential is exposed to the model.

A25 deliberately uses a separate SHA-256 hash-chained `OperationalWatchStateStore` rather than
extending the model-training lifecycle indefinitely:

`baseline_bound -> drift_reviewed -> rollback_review_requested`

A healthy watch can stop at `drift_reviewed`. Future watch cycles can bind the same still-current
baseline under new watch ids. Stage skipping, baseline replacement and evidence replacement fail
closed.

## Resumable lifecycle

```text
music evidence
  -> planner
  -> independent verifier
  -> guarded execution + CI/validators
  -> execution evidence
  -> curated dataset
  -> training contract + authorized training completion
  -> immutable model candidate
  -> paired benchmark
  -> promotion review
  -> activation request
  -> separately authorized activation
  -> activation receipt
  -> shadow/health gate
  -> canonical baseline review
  -> separately authorized canonicalization
  -> canonicalization receipt
  -> repeated post-canonical stability evidence
  -> append-only baseline registry

registered baseline
  -> operational drift watch
  -> healthy / observe
  -> or rollback review request
  -> host/human review only
```

`OrchestrationStateStore` records structured fingerprints through:

`plan_verified -> execution_verified -> dataset_curated -> training_completed -> model_registered
-> promotion_reviewed -> activation_requested -> activation_recorded -> shadow_health_reviewed
-> canonical_reviewed -> canonicalization_recorded -> post_canonical_stability_reviewed
-> baseline_registered`

Operational watch cycles are separate hash-chained state and do not rewrite model-lifecycle
history.

## A26 continuation

1. Define separately authorized host rollback execution receipts bound to an A25 request.
2. Add post-rollback serving identity, health and recovery verification before registry mutation.
3. Record an explicit rollback generation in baseline history without deleting the failed baseline.
4. Keep rollback credentials and execution outside all model-callable tools.
5. Require host/human authorization for every production-impacting rollback.

## Architectural invariants

1. Models cannot grant themselves privileges, approvals, training, promotion, activation,
   canonicalization or rollback authority.
2. Unknown/unregistered tools never execute.
3. External frameworks cannot bypass ST policy, budget, approval or isolation boundaries.
4. Music evidence remains source-provenanced and authority-bounded.
5. Plans are deterministic/versioned and independently recomputed.
6. Execution success requires exact commit/CI/validator evidence.
7. Learning history is verified and advisory; hidden reasoning is not learning data.
8. Candidate improvements must survive paired non-regressing evaluation.
9. Dataset export never authorizes training or promotion.
10. Training/checkpoint lineage is reproducible and immutable.
11. Promotion review never activates a candidate.
12. Activation requests and receipts preserve exact rollback identity.
13. Runtime-health evidence is required before canonical review.
14. Canonical review independently rechecks A22 evidence and current-baseline identity.
15. Canonicalization receipt requires separate host authorization and exact observed baseline.
16. Post-canonical stability requires repeated exact-identity health evidence before registry
    recording.
17. Baseline Registry lineage is append-only and cannot switch or roll back serving state.
18. Drift watch requires sustained evidence and exact current-baseline identity before rollback
    review can open.
19. Rollback review requests bind only the registered predecessor and never authorize execution.
20. Automatic canonicalization, baseline switching and rollback remain disabled.
21. Tests define safety behavior before capability is widened.
