# ST Music Agent Lab — Architecture Map

Status: A1-A19 guarded agent + verified planning/learning/evaluation/data/training provenance
Date: 2026-09-11

## Purpose

ST Music Agent Lab is a model-agnostic engineering and music-intelligence agent layer. It
coordinates models and tools around ST repositories while keeping autonomy observable,
reversible, capability-driven and isolated from the host.

## Core design

The ST core stays small and framework-independent. Models, OpenHands, GitHub and music projects
attach through explicit adapters. No external framework may bypass ST-owned policy, tool, budget,
approval, evidence, verification, learning, evaluation, execution-evidence, dataset, training-run
or sandbox boundaries.

## A1-A6 — Core execution and isolation

- A1-A3: task/model/action contracts, capability routing and deterministic privilege policy.
- A4: provider-neutral execution, credentials/transport boundaries and OpenHands REST adapter.
- A5: repository-confined workspace and narrow command classifier.
- A6: disposable hardened Docker sandbox with network disabled and resource limits.

## A7-A11 — Tool boundary, controlled mutation and OpenHands

- A7: explicit `ToolRegistry`, bounded/redacted output and SHA-256 hash-chained run journal.
- A8: canonical provider tool loop and bounded read-only GitHub surface.
- A9: only reversible feature-branch GitHub mutations are model-callable; protected/destructive
  actions remain gated and merge is not a model tool.
- A10: cumulative run budgets and opaque one-shot exact host approvals.
- A11: OpenHands connects only through the restricted ST MCP bridge; raw TerminalTool and
  FileEditorTool are absent.

## A12-A13 — Four-project music evidence plane

`MusicEvidenceSnapshot` schema `1.1.0` carries project/authority/state, bounded claims/warnings,
next-safe-boundary and source provenance (`repository`, `ref`, `path`, Git blob SHA).

Read-only tools:

- `music.score_restore.snapshot`
- `music.tab_engine.capability_snapshot`
- `music.score_editor.snapshot`
- `music.score_following.snapshot`

Authority invariants:

- Score Restore evaluation/candidate success never implies production or Stage 12 authorization.
- REVIEW_REQUIRED never implies canonical TAB export.
- Score Editor feature completion never implies release or SesliTab cutover authorization.
- Score-following research never implies acoustic-mixture, production or pedagogical authority.

## A14 — Deterministic portfolio planning + verifier

`CrossProjectPlanner` consumes exactly the complete four-project evidence set under policy
`2026-09-11.v1`. Current order deliberately closes bounded validation/integration uncertainty
before feature/research expansion:

1. Score Restore consumer/inference integration validation;
2. MusicXML/TAB teacher-review integration;
3. Score Editor APP-11G bounded feature work;
4. Score Following SF-12 research.

Every candidate carries an evidence hash; the plan has an evidence-set hash and deterministic
`plan_id`. `execution_authorized` is always false.

`CrossProjectVerifier` independently recomputes the plan. Source-SHA drift, changed order/actions,
policy mismatch or any execution-authorized claim causes FAIL.

Read-only tool: `music.portfolio.plan`.

## A15 — Verified experience learning

`ExperienceStore` is trusted-host-write-only and uses the sanitized hash-chained journal. An
outcome can be recorded only for the exact PASS-verified plan id and recomputation id.

`ExperienceAdvisor` aggregates verified history into `prefer`, `review` or `observe`; all
recommendations have `auto_apply=false`.

Read-only tool: `learning.experience.summary`.

The model cannot write/rewrite experience history or automatically change prompts, policy,
privileges, code or model weights.

## A16 — Paired learning evaluation gate

A16 compares one baseline and one candidate on an identical paired benchmark corpus before the
candidate can reach host review.

Default policy `2026-09-11.v1` requires >=8 paired cases, >=2 critical cases, exact matching case
ids/severity, zero regressions, zero candidate critical failures and at least one strict
improvement. Outcome order is `failure < abstained < success`.

A report can return `eligible_for_host_review` or `rejected`; `auto_promote=false` always.

Read-only model tool: `learning.evaluation.policy`.

## A17 — Exact execution outcome evidence

A17 closes the gap between a verified plan and a later success claim.

`ExecutionOutcomeStore` is trusted-host-write-only and hash chained. An `ExecutionObservation`
must bind to the exact verified plan candidate through plan id, candidate rank, project, exact
action, candidate evidence hash, expected repository, branch, full commit SHA, CI checks and
validator checks.

The provided `PlanVerificationReport` must be PASS and its `plan_id` plus
`recomputed_plan_id` must equal the same plan.

`SUCCESS` requires every CI and validator check to be `success`. `FAILURE` or `ABSTAINED` must
retain non-green evidence and cannot masquerade as successful execution.

Execution records are historical evidence only. They do not grant production, release, export,
training or promotion authority.

## A18 — Curated dataset boundary

`CuratedDatasetBuilder` deterministically exports explicitly selected verified execution record
IDs for `offline_evaluation` or `fine_tuning_candidate` use.

Rows contain only structured operational facts: project/plan/candidate identity, planned action,
evidence hash, repository, branch, exact commit SHA, outcome and CI/validator evidence.

Free-form execution notes are excluded. Provider messages, hidden reasoning and chain-of-thought
are not dataset fields.

Every export contains a manifest SHA-256 and hard-coded authority fields:

- `training_authorized=false`;
- `auto_train=false`;
- `auto_promote=false`.

`fine_tuning_candidate` means only that the dataset may later be reviewed by a separately
authorized training stage.

## A19 — Reproducible training-run contract

`training_run.py` binds a reviewed `fine_tuning_candidate` dataset to the exact inputs that would
produce a trained checkpoint.

`TrainingRunSpec` includes:

- run id;
- dataset id + verified manifest SHA-256;
- base-model id + exact revision + base-model artifact SHA-256;
- trainer name/version;
- canonical trainer configuration + configuration SHA-256;
- deterministic seed;
- training-code repository + full Git commit SHA;
- deterministic `input_fingerprint` over the complete input contract.

The dataset manifest is recomputed before a spec is accepted. Offline-evaluation datasets,
forged manifests or dataset authority flags that claim training/promotion are rejected.

A spec always has:

- `execution_authorized=false`;
- `auto_start=false`.

If a separately authorized host performs training, `TrainingRunCompletion` binds the same exact
input fingerprint to:

- explicit host authorization reference;
- checkpoint SHA-256 for completed runs;
- explicit training evidence references;
- deterministic completion fingerprint.

Completed runs always have:

- `evaluation_required=true`;
- `promotion_authorized=false`;
- `auto_promote=false`.

Failed or abstained runs cannot claim a checkpoint hash. A19 exposes no model-callable training or
promotion tool.

## Current decision/learning/training chain

```text
four project snapshots
        |
        v
CrossProjectPlanner
        |
        v
CrossProjectVerifier ---- FAIL -> stop
        |
       PASS
        v
guarded host execution
        |
        v
exact branch/commit + CI + validators
        |
        v
ExecutionOutcomeStore
        |
        +-----------------------> ExperienceStore / Advisor
        |                                  |
        |                                  v
        |                         prefer / observe / review
        |                                  |
        |                         paired candidate benchmark
        |                                  |
        |                         LearningEvaluationGate
        |                                  |
        |                     rejected / eligible for host review
        |
        v
explicit record-id curation
        |
        v
CuratedDatasetBuilder
        |
        v
fine-tuning-candidate manifest
        |
 training_authorized=false / auto_train=false / auto_promote=false
        |
        v
TrainingRunSpec
(dataset + base model + trainer config + seed + code SHA)
        |
  execution_authorized=false / auto_start=false
        |
        | separate host authorization if training is actually run
        v
TrainingRunCompletion
(input fingerprint + checkpoint SHA + training evidence)
        |
 evaluation_required=true / promotion_authorized=false
        |
        v
A16 paired checkpoint evaluation before any promotion review
```

## A20 continuation

1. Add a checkpoint/model registry that records immutable model candidate identities and lineage
   from A19 completion evidence.
2. Bind every model candidate to its required A16 evaluation report and current baseline identity.
3. Add an explicit promotion-review contract that can only reference a non-regressing evaluated
   candidate; keep actual activation as a separate host/human action.
4. Add resumable orchestration state linking plan, approvals, execution, experience, evaluation,
   dataset, training and model-candidate evidence without hidden reasoning.
5. Keep deployment/production activation outside model-callable tools.

## Architectural invariants

1. Model choice is replaceable.
2. Models cannot grant themselves privileges or approvals.
3. Unknown/unregistered tools never execute.
4. Protected/destructive/external actions cannot silently escalate.
5. Credentials resolve only after policy permits a trusted adapter operation.
6. Host process execution is not a raw model capability.
7. Executable repository code runs only through an ST-approved sandbox backend.
8. Model-facing output/run traffic is bounded and redacted.
9. Persistent run, experience and execution evidence is sanitized and hash chained.
10. Provider schemas are not host authorization.
11. Run budgets fail closed before overflowing the next action.
12. OpenHands raw terminal/editor capability is absent from the bridged agent configuration.
13. Music evidence cannot silently overstate readiness or authority.
14. Portfolio planning is deterministic/versioned and never execution authority.
15. Portfolio verification independently recomputes accepted plans.
16. Evidence drift invalidates old plans.
17. Execution success requires exact candidate/repository/commit/CI/validator evidence.
18. A failed/skipped validator cannot be hidden inside a successful execution record.
19. Only exact verified outcomes may enter experience history.
20. Models cannot write experience history through registered tools.
21. Experience recommendations never auto-apply.
22. Hidden provider reasoning is not persisted as learning data.
23. Learning candidates must use the exact paired benchmark case set/severity as baseline.
24. Any paired regression or critical failure rejects a learning candidate.
25. Benchmark eligibility never auto-promotes a playbook/model.
26. Dataset curation is explicit by verified execution record ID.
27. Curated dataset export excludes hidden reasoning/free-form notes.
28. Dataset export never authorizes training or model promotion.
29. Training requires an exact verified fine-tuning-candidate dataset manifest.
30. Training inputs bind exact base-model artifact, trainer config, seed and code commit.
31. Creating a training spec never authorizes or auto-starts training.
32. Completed training binds one checkpoint hash to one exact input fingerprint and authorization
    reference.
33. A trained checkpoint requires independent A16 evaluation and is never auto-promoted.
34. Tests define safety behavior before capability is widened.
