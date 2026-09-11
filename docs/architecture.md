# ST Music Agent Lab — Architecture Map

Status: A1-A22 guarded agent + verified planning/learning/evaluation/data/training/model-runtime foundation
Date: 2026-09-11

## Purpose

ST Music Agent Lab is a model-agnostic engineering and music-intelligence agent layer. Models,
OpenHands, GitHub and ST music projects attach through explicit adapters while ST-owned policy,
tool, budget, approval, evidence, verification, learning, evaluation, execution, dataset,
training, model-candidate, orchestration, activation-request, activation-receipt and runtime-health
boundaries remain authoritative.

## A1-A11 — Guarded execution foundation

- A1-A3: task/model/action contracts, capability routing and deterministic privilege policy.
- A4-A6: provider/OpenHands boundaries, repository-confined workspace and hardened disposable
  sandbox execution.
- A7-A8: explicit ToolRegistry, bounded/redacted output, SHA-256 hash-chained journal, provider
  tool loop and bounded GitHub reads.
- A9-A10: reversible feature-branch mutations, cumulative run budgets and exact one-shot host
  approvals.
- A11: restricted OpenHands bridge; raw terminal/editor authority is absent.

## A12-A13 — Four-project music evidence plane

Read-only, source-provenanced snapshots cover Score Restore, MusicXML/Guitar TAB, Score Editor and
Real-Time Score Following. Evidence cannot silently inflate authority: evaluation does not imply
production, REVIEW_REQUIRED does not imply canonical export, editor feature completion does not
imply release/cutover and research evidence does not imply production/pedagogical authority.

## A14-A16 — Planning, experience and evaluation

`CrossProjectPlanner` uses explicit policy and `CrossProjectVerifier` independently recomputes the
plan. `ExperienceStore` is trusted-host-write-only and advisory. `LearningEvaluationGate` compares
baseline/candidate on identical paired cases and rejects regressions or critical failures.

Passing A16 means only `eligible_for_host_review`; no automatic policy/model promotion exists.

## A17-A18 — Exact execution evidence and dataset boundary

`ExecutionOutcomeStore` binds execution to exact plan candidate, repository, branch, commit SHA,
CI and validators. `CuratedDatasetBuilder` exports explicitly selected verified records only.
Free-form notes and hidden reasoning are excluded. Dataset manifests never authorize training or
promotion.

## A19 — Reproducible training run

`TrainingRunSpec` binds an exact fine-tuning-candidate dataset manifest to base-model identity,
artifact SHA-256, trainer config, seed and training-code commit. A separately authorized completed
run binds one resulting checkpoint SHA-256 to that exact input fingerprint. Training completion
never grants promotion authority.

## A20 — Immutable model candidate + promotion review

`ModelCandidateRegistry` derives deterministic `model:<lineage_sha256>` identities from verified
training/checkpoint lineage. `ModelPromotionReviewGate` reruns A16 itself and rejects claimed
reports that differ from recomputation.

Passing A20 means only `eligible_for_activation_review`; activation remains unauthorized.

## A21 — Resumable orchestration + activation request

`OrchestrationStateStore` persists only structured ids/fingerprints in the SHA-256 hash-chained
journal. It stores no prompts, provider messages or hidden reasoning.

A21 stages:

1. `plan_verified`
2. `execution_verified`
3. `dataset_curated`
4. `training_completed`
5. `model_registered`
6. `promotion_reviewed`
7. `activation_requested`

`ActivationRequestBuilder` binds exact candidate/checkpoint, current baseline, rollback target,
promotion-review fingerprint and target environment. Rollback must equal the exact current
baseline. Every request has `human_approval_required=true`, `activation_authorized=false`,
`auto_activate=false`, `canonicalization_authorized=false`.

## A22 — Activation receipt

`ActivationReceiptBuilder` records the result of an externally executed host activation action. It
does not perform deployment.

The receipt binds the exact A21 request to:

- candidate id/checkpoint;
- target environment;
- previous baseline and rollback id/checkpoint;
- host authorization reference;
- deployment reference;
- explicit evidence references;
- observed serving model/checkpoint.

`activated` requires observed serving identity to equal the requested candidate. `rolled_back`
requires observed identity to equal the rollback target. `failed` cannot claim a serving model.
Every receipt keeps `canonicalization_authorized=false` and `auto_canonicalize=false`.

## A22 — Shadow health and rollback readiness gate

`ShadowHealthGate` requires exactly four evidence-bearing runtime checks:

1. `serving_identity`
2. `health`
3. `shadow_quality`
4. `rollback_readiness`

Each is `success`, `failure` or `unavailable`. Any failure or unavailable result rejects the
candidate. Four successes yield only `eligible_for_canonical_review`.

The report remains human-gated with `canonicalization_authorized=false` and
`auto_canonicalize=false`. It is deterministic and independently recomputable.

A22 extends orchestration with:

8. `activation_recorded`
9. `shadow_health_reviewed`

Prior evidence remains immutable and only receipt/report fingerprints are persisted.

## Current lifecycle

```text
music evidence
    |
Planner -> Verifier
    |
verified execution -> exact commit/CI/validators
    |
ExecutionOutcomeStore -> Experience / paired evaluation
    |
CuratedDatasetBuilder
    |
TrainingRunSpec -> separately authorized host training -> TrainingRunCompletion
    |
ModelCandidateRegistry
    |
A16 benchmark -> ModelPromotionReviewGate
    |
eligible_for_activation_review
    |
ActivationRequestBuilder
    |
separate human/host activation
    |
ActivationReceiptBuilder
    |
serving identity + health + shadow quality + rollback readiness
    |
ShadowHealthGate
    |
rejected / eligible_for_canonical_review
    |
canonicalization still NOT authorized
```

## A23 continuation

1. Add an explicit canonical-baseline review contract consuming one exact A22 passing report.
2. Require a separate host/human canonicalization authorization and record the exact previous and
   new baseline identities.
3. Record canonicalization/rollback receipts without exposing serving credentials to models.
4. Add post-canonical stability evidence before the new baseline can be treated as durable history.
5. Keep actual serving changes, deployment credentials and rollback execution outside model tools.

## Architectural invariants

1. Models cannot grant themselves privileges, approvals, training, promotion, activation or canonicalization.
2. Unknown tools never execute and external frameworks cannot bypass ST policy/budget/isolation.
3. Music evidence remains source-provenanced and authority-bounded.
4. Plans are deterministic/versioned and independently recomputed.
5. Execution success requires exact commit/CI/validator evidence.
6. Hidden reasoning is never persisted as learning/training/orchestration data.
7. Candidate improvements require paired non-regressing evaluation.
8. Dataset export never authorizes training/promotion.
9. Training inputs bind exact reproducibility inputs and never auto-start.
10. Model identities derive from immutable training/checkpoint lineage.
11. Promotion review independently recomputes evaluation and never activates candidates.
12. Orchestration state is resumable, hash chained and cannot replace prior evidence.
13. Activation requests require exact current-baseline rollback binding.
14. Activation receipts record external host actions but cannot canonicalize models.
15. Runtime health requires exact serving, health, shadow-quality and rollback-readiness evidence.
16. Runtime success yields only canonical-review eligibility, never canonicalization authority.
17. Tests define safety behavior before capability is widened.
