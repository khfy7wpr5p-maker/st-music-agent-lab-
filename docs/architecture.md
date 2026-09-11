# ST Music Agent Lab — Architecture Map

Status: A1-A16 guarded agent + verified planning/learning/evaluation foundation
Date: 2026-09-11

## Purpose

ST Music Agent Lab is a model-agnostic engineering and music-intelligence agent layer. It
coordinates models and tools around ST repositories while keeping autonomy observable,
reversible, capability-driven and isolated from the host.

## Core design

The ST core stays small and framework-independent. Models, OpenHands, GitHub and music projects
attach through explicit adapters. No external framework may bypass ST-owned policy, tool, budget,
approval, evidence, verification, learning, evaluation or sandbox boundaries.

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

Read-only tool:

- `music.portfolio.plan`

## A15 — Verified experience learning

`ExperienceStore` is trusted-host-write-only and uses the existing sanitized hash-chained journal.
An outcome can be recorded only for the exact PASS-verified plan id and recomputation id.

`ExperienceAdvisor` aggregates verified history into:

- `prefer`: >=3 evaluated attempts and >=80% success;
- `review`: >=3 evaluated attempts and <=50% success;
- `observe`: insufficient or mixed evidence.

Abstentions remain visible and are not counted as success/failure. All recommendations have
`auto_apply=false`.

Read-only tool:

- `learning.experience.summary`

The model cannot write/rewrite experience history or automatically change prompts, policy,
privileges, code or model weights.

## A16 — Paired learning evaluation gate

A15 historical preference is advisory evidence, not proof that a changed playbook/model is better.
A16 adds `learning_evaluation.py` to compare one baseline and one candidate on an identical paired
benchmark corpus before the candidate can reach host review.

### Benchmark contract

Each `BenchmarkCaseResult` contains:

- stable case id;
- severity: `standard` or `critical`;
- outcome: `success`, `abstained` or `failure`;
- explicit evidence references.

`BenchmarkRun` requires unique case ids and computes a SHA-256 fingerprint over candidate id,
case definitions, outcomes and evidence references. Evidence changes therefore change run identity.

### Evaluation policy

Policy version: `2026-09-11.v1`.

Default gate requires:

- >=8 paired cases;
- >=2 critical cases;
- exact same case ids between baseline/candidate;
- exact same case severity;
- zero paired regressions;
- zero candidate critical failures;
- at least one strict improvement.

Outcome ordering is conservative:

`failure < abstained < success`

A tie is rejected as “no improvement.” Any regression rejects the candidate even if other cases
improve.

`LearningEvaluationReport` can return:

- `eligible_for_host_review`; or
- `rejected`.

`auto_promote` is always false. Eligibility is not activation authority.

### Model surface

The only A16 model-facing tool is:

- `learning.evaluation.policy`

It is read-only. There is no registered tool to submit benchmark evidence, approve/promote a
candidate, edit prompts/policy, or change model weights.

## Current learning/decision loop

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
host execution path
        |
        v
CI / validators / evidence
        |
        v
ExperienceStore
        |
        v
ExperienceAdvisor
prefer / observe / review
        |
        | candidate implementation remains separately controlled
        v
baseline benchmark <---- paired cases ----> candidate benchmark
        |                                      |
        +--------- LearningEvaluationGate -----+
                         |
               rejected / eligible for host review
                         |
                  auto_promote = false
```

## A17 continuation

1. Add an execution-outcome contract binding one completed action to exact plan candidate,
   branch/commit, CI/validator evidence and final verifier state.
2. Add resumable orchestration state linking plan, execution, journal, budget, approval,
   experience and evaluation evidence without hidden model reasoning.
3. Add curated dataset export contracts from verified experience/evaluation evidence for possible
   future fine-tuning; no raw chat/hidden reasoning export.
4. Add independent pre/post candidate benchmark bundles for future model versions.
5. Keep actual training and model promotion as separately authorized host/human stages.

## Architectural invariants

1. Model choice is replaceable.
2. Models cannot grant themselves privileges or approvals.
3. Unknown/unregistered tools never execute.
4. Protected/destructive/external actions cannot silently escalate.
5. Credentials resolve only after policy permits a trusted adapter operation.
6. Host process execution is not a raw model capability.
7. Executable repository code runs only through an ST-approved sandbox backend.
8. Model-facing output/run traffic is bounded and redacted.
9. Persistent run and experience evidence is sanitized and hash chained.
10. Provider schemas are not host authorization.
11. Run budgets fail closed before overflowing the next action.
12. OpenHands raw terminal/editor capability is absent from the bridged agent configuration.
13. Music evidence cannot silently overstate readiness or authority.
14. Portfolio planning is deterministic/versioned and never execution authority.
15. Portfolio verification independently recomputes accepted plans.
16. Evidence drift invalidates old plans.
17. Only exact verified outcomes may enter experience history.
18. Models cannot write experience history through registered tools.
19. Experience recommendations never auto-apply.
20. Hidden provider reasoning is not persisted as learning data.
21. A learning candidate must use the exact paired benchmark case set/severity as baseline.
22. Any paired regression rejects a learning candidate.
23. Critical benchmark failures reject a learning candidate.
24. Benchmark eligibility never auto-promotes a playbook/model.
25. Future fine-tuning requires curated data, independent evaluation and explicit promotion gates.
26. Tests define safety behavior before capability is widened.
