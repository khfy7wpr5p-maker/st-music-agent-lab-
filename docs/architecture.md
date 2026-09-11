# ST Music Agent Lab — Architecture Map

Status: A1-A20 guarded agent + verified planning/learning/evaluation/data/training/model-candidate foundation
Date: 2026-09-11

## Purpose

ST Music Agent Lab is a model-agnostic engineering and music-intelligence agent layer. It
coordinates models and tools around ST repositories while keeping autonomy observable,
reversible, capability-driven and isolated from the host.

## Core design

The ST core stays small and framework-independent. Models, OpenHands, GitHub and music projects
attach through explicit adapters. No external framework may bypass ST-owned policy, tool, budget,
approval, evidence, verification, learning, evaluation, execution-evidence, dataset, training-run,
model-candidate or sandbox boundaries.

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

`ExecutionOutcomeStore` is trusted-host-write-only and hash chained. An `ExecutionObservation`
must bind to the exact verified plan candidate through plan id, candidate rank, project, exact
action, candidate evidence hash, expected repository, branch, full commit SHA, CI checks and
validator checks.

`SUCCESS` requires every CI and validator check to be `success`. `FAILURE` or `ABSTAINED` must
retain non-green evidence and cannot masquerade as successful execution.

Execution records are historical evidence only. They do not grant production, release, export,
training or promotion authority.

## A18 — Curated dataset boundary

`CuratedDatasetBuilder` deterministically exports explicitly selected verified execution record
IDs for `offline_evaluation` or `fine_tuning_candidate` use.

Rows contain only structured operational facts. Free-form execution notes, provider messages,
hidden reasoning and chain-of-thought are not dataset fields.

Every export contains a manifest SHA-256 and hard-coded authority fields:

- `training_authorized=false`;
- `auto_train=false`;
- `auto_promote=false`.

## A19 — Reproducible training-run contract

`TrainingRunSpec` binds an exact reviewed `fine_tuning_candidate` dataset manifest to base-model
id/revision/artifact SHA-256, trainer name/version/config, deterministic seed and training-code
commit. The complete input contract is hashed into one `input_fingerprint`.

A spec always has `execution_authorized=false` and `auto_start=false`.

If a separately authorized host performs training, `TrainingRunCompletion` binds that exact input
fingerprint to the host authorization reference, checkpoint SHA-256 and training evidence.
Completed runs always have `evaluation_required=true`, `promotion_authorized=false` and
`auto_promote=false`.

## A20 — Immutable model candidate + promotion review recomputation

`ModelCandidateRegistry` accepts only a verified completed A19 training lineage. It independently
checks the training spec/config/input fingerprint, completion/run linkage, checkpoint SHA-256,
completion fingerprint and non-promotion authority flags.

The registry derives a deterministic `model:<lineage_sha256>` candidate id from:

- checkpoint SHA-256;
- training run id;
- training input/completion fingerprints;
- dataset id + manifest hash;
- base-model id/revision/artifact SHA-256.

Every model candidate has `evaluation_required=true`, `activation_authorized=false` and
`auto_activate=false`.

`ModelPromotionReviewGate` requires:

- one registered model candidate;
- current baseline benchmark run;
- candidate benchmark run whose candidate id matches the registered model;
- claimed A16 evaluation report.

The gate reruns `LearningEvaluationGate.compare()` itself. If the claimed report differs from the
fresh recomputation, review fails closed.

A recomputed A16 pass yields only `eligible_for_activation_review`. The review record still has:

- `human_review_required=true`;
- `activation_authorized=false`;
- `auto_activate=false`.

A rejected A16 result stays rejected. A20 exposes no activation/deployment tool.

## Current decision/learning/training/promotion chain

```text
four project snapshots
        |
        v
CrossProjectPlanner -> CrossProjectVerifier
        |
       PASS
        v
guarded host execution
        |
        v
exact commit + CI + validators
        |
        v
ExecutionOutcomeStore
        |
        +----> ExperienceStore / Advisor ----> candidate playbook evidence
        |
        v
CuratedDatasetBuilder
        |
        v
fine-tuning-candidate manifest
        |
        v
TrainingRunSpec
        |
 separate host authorization if training actually runs
        v
TrainingRunCompletion
        |
        v
ModelCandidateRegistry
        |
        v
registered immutable model candidate
        |
baseline benchmark <---- same cases ----> candidate benchmark
        |                                      |
        +--------- LearningEvaluationGate -----+
                         |
             rejected / eligible_for_host_review
                         |
                         v
             ModelPromotionReviewGate
            (independent recomputation)
                         |
        rejected / eligible_for_activation_review
                         |
      human_review_required=true
      activation_authorized=false
      auto_activate=false
```

## A21 continuation

1. Add resumable orchestration state linking plan, approvals, execution, experience, evaluation,
   dataset, training, candidate and promotion-review evidence without hidden reasoning.
2. Add a separate explicit activation request contract that references an exact A20 review record
   and requires host/human approval; do not activate automatically.
3. Add rollback identity and previous-baseline binding before any activation can be considered.
4. Add post-activation shadow/health evidence contracts before a candidate can become canonical.
5. Keep deployment credentials and actual serving changes outside model-callable tools.

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
25. Dataset export never authorizes training or model promotion.
26. Training inputs bind exact dataset, base-model artifact, trainer config, seed and code commit.
27. Creating a training spec never authorizes or auto-starts training.
28. Completed training binds one checkpoint hash to one exact input fingerprint and authorization.
29. A model candidate id is derived from immutable training/checkpoint lineage.
30. Model candidates never carry activation authority.
31. Promotion review recomputes A16 rather than trusting a claimed report.
32. Promotion-review eligibility never activates or deploys a candidate.
33. Tests define safety behavior before capability is widened.
