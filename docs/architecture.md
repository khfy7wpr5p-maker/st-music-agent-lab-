# ST Music Agent Lab — Architecture Map

Status: A1-A21 guarded agent + verified planning/learning/evaluation/data/training/model-lifecycle foundation
Date: 2026-09-11

## Purpose

ST Music Agent Lab is a model-agnostic engineering and music-intelligence agent layer. Models,
OpenHands, GitHub and ST music projects attach through explicit adapters while ST-owned policy,
tool, budget, approval, evidence, verification, learning, evaluation, execution, dataset,
training, model-candidate, orchestration and activation-request boundaries remain authoritative.

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

## A14 — Deterministic portfolio planner + verifier

`CrossProjectPlanner` consumes the complete four-project evidence set under explicit versioned
policy. `CrossProjectVerifier` independently recomputes the plan. Source drift, changed actions or
execution-authorized claims fail closed. `execution_authorized=false` is invariant.

## A15 — Verified experience learning

`ExperienceStore` is trusted-host-write-only and hash chained. Only outcomes tied to the exact
PASS-verified plan enter history. `ExperienceAdvisor` emits advisory `prefer`, `observe` or
`review`; `auto_apply=false` always.

## A16 — Paired learning evaluation

`LearningEvaluationGate` compares baseline and candidate on identical paired cases. Current policy
requires >=8 cases, >=2 critical cases, identical case/severity definitions, zero regressions, zero
candidate critical failures and at least one strict improvement. Outcome order is
`failure < abstained < success`. Passing means only `eligible_for_host_review`.

## A17 — Exact execution outcome evidence

`ExecutionOutcomeStore` binds a completed action to exact plan candidate, project/action,
evidence hash, repository, branch, full commit SHA, CI and validator checks. `SUCCESS` requires all
supplied CI/validators to succeed. Records are historical evidence, not new authority.

## A18 — Curated dataset boundary

`CuratedDatasetBuilder` exports only explicitly selected verified execution record IDs. Structured
operational facts are allowed; free-form notes and hidden reasoning are excluded. Dataset manifests
always keep `training_authorized=false`, `auto_train=false`, `auto_promote=false`.

## A19 — Reproducible training run

`TrainingRunSpec` binds a verified fine-tuning-candidate dataset manifest to exact base-model
identity/revision/artifact SHA-256, trainer name/version/config, seed and training-code Git commit.
The complete input contract becomes one deterministic `input_fingerprint`.

A separately authorized completed run binds that fingerprint to authorization reference,
checkpoint SHA-256 and training evidence. Completed runs still require evaluation and carry no
promotion authority.

## A20 — Immutable model candidate + promotion review

`ModelCandidateRegistry` derives a deterministic `model:<lineage_sha256>` identity from verified
A19 training/checkpoint lineage. Candidates have `evaluation_required=true`,
`activation_authorized=false`, `auto_activate=false`.

`ModelPromotionReviewGate` independently reruns A16 from baseline/candidate benchmark runs and
requires the claimed report to match recomputation. A passing result becomes only
`eligible_for_activation_review`; human review remains required and activation remains false.

## A21 — Resumable orchestration state

`OrchestrationStateStore` persists only structured evidence identities/fingerprints through the
existing SHA-256 hash-chained journal. It stores no prompts, provider messages or hidden reasoning.

Ordered stages are:

1. `plan_verified`
2. `execution_verified`
3. `dataset_curated`
4. `training_completed`
5. `model_registered`
6. `promotion_reviewed`
7. `activation_requested`

The state can also attach verified experience/evaluation references after execution. Stage skips
are rejected, earlier evidence cannot be replaced, and reopening the store re-verifies the journal
before resuming from the latest state.

## A21 — Explicit activation request with rollback binding

`ActivationRequestBuilder` requires an immutable A20 model candidate plus an
`eligible_for_activation_review` A20 review. It independently verifies candidate/review
fingerprints and binds:

- exact candidate id/checkpoint;
- promotion-review fingerprint;
- exact current-baseline id/checkpoint;
- rollback id/checkpoint;
- bounded target environment.

Rollback must equal the current baseline identity and checkpoint. Every request is content-addressed
and always has:

- `human_approval_required=true`;
- `activation_authorized=false`;
- `auto_activate=false`;
- `canonicalization_authorized=false`.

Creating a request does not deploy, activate, canonicalize or switch a serving model.

## Current lifecycle

```text
music evidence snapshots
        |
        v
Planner -> independent Verifier
        |
       PASS
        v
guarded execution -> exact commit + CI + validators
        |
        v
ExecutionOutcomeStore
        |
        +--> Experience / paired evaluation evidence
        |
        v
CuratedDatasetBuilder
        |
        v
TrainingRunSpec -- separate host authorization --> TrainingRunCompletion
        |
        v
ModelCandidateRegistry
        |
        v
A16 baseline/candidate benchmark
        |
        v
ModelPromotionReviewGate
        |
 eligible_for_activation_review
        |
        v
ActivationRequestBuilder
        |
 human approval required; activation still false

OrchestrationStateStore hash-chains evidence pointers across the lifecycle for resume.
```

## A22 continuation

1. Add post-activation shadow/health evidence contracts before any candidate can become canonical.
2. Define a separately authorized host activation receipt that binds exact A21 request + deployed
   artifact + environment + rollback target, without exposing deployment credentials to models.
3. Require rollback/health evidence before canonical-baseline replacement.
4. Keep canonicalization and production serving changes outside model-callable tools.
5. Extend resumable state only with structured receipts/fingerprints, never hidden reasoning.

## Architectural invariants

1. Models cannot grant themselves privileges, approvals, training, promotion or activation.
2. Unknown tools never execute and external frameworks cannot bypass ST policy/budget/isolation.
3. Music evidence remains source-provenanced and authority-bounded.
4. Plans are deterministic/versioned and independently recomputed.
5. Execution success requires exact commit/CI/validator evidence.
6. Experience history is verified and advisory only; hidden reasoning is not learning data.
7. Candidate improvements require paired non-regressing evaluation.
8. Dataset export never authorizes training/promotion.
9. Training specs bind exact reproducibility inputs and do not auto-start.
10. Model candidate identities derive from immutable training/checkpoint lineage.
11. Promotion review recomputes evaluation and does not activate candidates.
12. Orchestration state is resumable, hash chained and cannot silently replace prior evidence.
13. Activation requests require exact current baseline + rollback binding.
14. Activation-request creation never activates, deploys or canonicalizes a model.
15. Tests define safety behavior before capability is widened.
