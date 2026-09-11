# ST Music Agent Lab — Architecture Map

Status: A1-A26 guarded core + APP1 runnable operator application
Date: 2026-09-11

## Purpose

ST Music Agent Lab is a model-agnostic engineering and music-intelligence agent layer. Models,
OpenHands, GitHub and ST music projects attach through explicit adapters while ST-owned policy,
tool, budget, approval, evidence, verification, learning, evaluation, execution, dataset,
training, model-candidate, orchestration, activation, canonical-baseline, stable-baseline registry,
operational-drift and rollback-recovery boundaries remain authoritative.

APP1 adds the first real user-facing application surface above that core. The UI does not bypass or
reimplement the safety architecture: it consumes the same bounded evidence and verified planning
services.

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

A19 binds exact dataset, base model, trainer config, seed and training-code commit into a reproducible
training input fingerprint. A separately authorized completed run binds the resulting checkpoint to
that exact input.

A20 registers immutable model candidate lineage and independently recomputes A16 before a model can
become `eligible_for_activation_review`. Activation remains unauthorized.

## A21-A23 — Activation and canonicalization

A21 adds resumable lifecycle state and an activation request with exact rollback binding. A22 records
separately executed host activation outcomes and requires serving identity, health, shadow quality
and rollback readiness. A23 independently recomputes those checks before canonical review and
records separately authorized host canonicalization receipts.

No model-facing tool can activate, canonicalize, switch or roll back a serving model.

## A24 — Post-canonical stability + Baseline Registry

A24 requires at least three ordered post-canonical observation rounds containing serving identity,
health, quality and rollback-readiness evidence. Only a complete pass becomes
`eligible_for_baseline_registration`.

`BaselineRegistry` is append-only and SHA-256 hash-chained. It records exact model/checkpoint
lineage, host evidence and transition fingerprints while keeping `auto_switch=false` and
`auto_rollback=false`.

## A25 — Long-term drift watch + rollback review request

A25 monitors an already-registered canonical baseline. At least four observation windows are
required. A single degraded window is insufficient: rollback review requires sustained degradation
for at least two consecutive windows and degradation must still be present in the latest window.
Unavailable evidence or unstable rollback readiness yields `observe` rather than rollback review.

`RollbackReviewRequestBuilder` recomputes the source drift evidence and binds review only to the
exact predecessor already recorded by Baseline Registry. The request always has
`human_approval_required=true`, `rollback_authorized=false` and `auto_rollback=false`.

A separate hash-chained `OperationalWatchStateStore` tracks recurring watch cycles without
rewriting model-training lifecycle history.

## A26 — Rollback receipt + recovery + historical rollback generation

A26 distinguishes a rollback review request from an externally executed rollback.
`RollbackExecutionReceiptBuilder` recomputes the exact A25 baseline, drift windows, drift report and
rollback review request before it can record an outcome.

A successful `rolled_back` receipt requires separate host authorization, an external execution
reference, supporting evidence and observed serving model/checkpoint equal to the exact Baseline
Registry predecessor. The receipt records the external action only. It keeps `auto_rollback=false`
and `auto_switch=false`.

A successful rollback receipt does not immediately become registry truth.
`PostRollbackRecoveryGate` requires at least two ordered rounds, each with exact
`serving_identity`, `health` and `recovery` checks. All must succeed. A passing report yields only
`eligible_for_baseline_registration` with `auto_register_baseline=false`.

`BaselineRegistry` schema 1.1.0 adds `rollback` generations. A rollback generation is appended only
when A25 and A26 evidence recomputes successfully, the current registry record is still the degraded
baseline, and the rollback target is the exact prior generation already in history. The degraded
canonical generation is never deleted.

## APP1 — Runnable Operator Console

APP1 is the first real application surface. It is dependency-free at runtime and starts with:

```text
st-music-agent app
      ↓
localhost HTTP server
      ↓
Operator Console UI
      ↓
OperatorConsoleService
      ↓
read-only music evidence adapters + PortfolioPlanningService
      ↓
A1-A26 guarded core
```

The application exposes:

- current state/summary/warnings/next safe boundary for all four ST music projects;
- isolated per-project errors so one inaccessible repository does not crash the whole UI;
- a capability panel that explicitly shows mutation/production actions as disabled;
- fresh deterministic portfolio planning with independent verifier status;
- a mobile-friendly single-page operator interface.

HTTP routes are currently read-only. Non-GET methods fail closed with `405`. APP1 therefore gives a
truthful working application rather than presenting execution controls that are not yet safely
connected.

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
  -> sustained regression
  -> rollback review request
  -> separate host/human rollback action
  -> rollback execution receipt
  -> repeated post-rollback recovery evidence
  -> append-only rollback generation
```

`OrchestrationStateStore` ends its training/model lifecycle at `baseline_registered`. Repeated
operational drift and rollback cycles remain in separate hash-chained operational watch state.

## Application continuation — APP2

1. Add an explicit task request/preview contract to the Operator Console.
2. Bind task preview to current project evidence, target repository and safe feature-branch intent.
3. Route execution through the existing deterministic policy/approval layer rather than adding a
   second mutation path.
4. Show execution state, commit/CI/validator evidence and resumable status in the same UI.
5. Keep protected-branch, deployment, training, canonicalization and rollback actions unavailable
   unless their existing host/human gates are separately satisfied.

## Model-lifecycle continuation — A27

Incident/rollback outcome learning and read-only incident-lineage evidence remain useful future core
work, but application integration is now the nearer product priority.

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
14. Canonicalization requires separate host authorization and exact observed baseline.
15. Baseline Registry lineage is append-only and cannot switch or roll back serving state.
16. Drift watch requires sustained evidence and exact baseline identity before rollback review.
17. Rollback review requests never authorize execution.
18. Rollback execution receipts require separate host authorization and exact observed target.
19. Post-rollback recovery must pass before rollback history becomes the current registry generation.
20. Failed/superseded baseline generations remain in immutable history.
21. APP1 HTTP write methods remain disabled until guarded execution is explicitly connected.
22. Automatic canonicalization, baseline switching and rollback remain disabled.
23. Tests define safety behavior before capability is widened.
