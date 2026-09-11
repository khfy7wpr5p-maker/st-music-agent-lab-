# ST Music Agent Lab — Architecture Map

Status: A1-A18 guarded agent + verified planning/learning/evaluation/data foundation
Date: 2026-09-11

## Purpose

ST Music Agent Lab is a model-agnostic engineering and music-intelligence agent layer. It
coordinates models and tools around ST repositories while keeping autonomy observable,
reversible, capability-driven and isolated from the host.

## Core design

The ST core stays small and framework-independent. Models, OpenHands, GitHub and music projects
attach through explicit adapters. No external framework may bypass ST-owned policy, tool, budget,
approval, evidence, verification, learning, evaluation, execution-evidence, dataset or sandbox
boundaries.

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
must bind to the exact verified plan candidate through:

- `plan_id` and candidate rank;
- project identity;
- exact planned action;
- candidate evidence SHA-256;
- expected repository;
- branch and full 40-hex commit SHA;
- one or more CI checks;
- one or more validator checks.

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

## Current decision/learning chain

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
offline-evaluation / fine-tuning-candidate manifest
        |
 training_authorized=false / auto_train=false / auto_promote=false
```

## A19 continuation

1. Add an explicitly authorized training-run contract consuming one exact curated dataset manifest
   plus base-model identity, trainer config and reproducibility seed.
2. Record training output checkpoint hash and environment provenance without granting promotion.
3. Require the trained checkpoint to pass the existing A16 paired evaluation against the current
   baseline before it may become a promotion candidate.
4. Add resumable orchestration state linking plan, approvals, execution, experience, evaluation,
   dataset and optional training-run evidence without hidden reasoning.
5. Keep actual checkpoint activation/promotion as a separate explicit host/human gate.

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
29. Future training requires an explicit dataset manifest, reproducible run contract and independent
    post-training evaluation.
30. Tests define safety behavior before capability is widened.
