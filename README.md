# ST Music Agent Lab

Model-agnostic orchestration core and runnable operator application for autonomous
software-engineering and music-intelligence work across ST projects.

## Current stage

A1-A26 guarded agent + verified evidence/learning/training/model-runtime/canonical-baseline
stability/drift/rollback-recovery foundation, plus **APP1 runnable Operator Console**:

- **A1-A11:** guarded execution, deterministic privilege policy, budgets, approvals, sandboxing,
  bounded GitHub mutation and restricted OpenHands integration.
- **A12-A13:** read-only source-provenanced evidence from Score Restore, MusicXML/TAB, Score Editor
  and real-time score following.
- **A14-A18:** deterministic planning + independent verification, verified experience learning,
  paired evaluation, exact execution evidence and curated dataset export.
- **A19-A20:** reproducible training-run lineage, immutable trained-model candidate identity and
  independent promotion-review recomputation.
- **A21-A23:** resumable lifecycle, activation receipts, runtime health, canonical review and
  separately authorized canonicalization receipts.
- **A24:** repeated post-canonical stability evidence plus append-only baseline registry lineage.
- **A25:** long-term drift/regression watch and host-reviewed rollback requests bound to the exact
  registered predecessor.
- **A26:** separately authorized rollback execution receipts, repeated post-rollback recovery and
  append-only rollback generations that retain the failed baseline in history.
- **APP1:** dependency-free web Operator Console for live project evidence, safety/capability state,
  and independently verified portfolio planning.

Package version: `0.25.0`.

## Run the application

```bash
python -m pip install -e '.[dev]'
st-music-agent app
```

Open `http://127.0.0.1:8765`.

The first runnable UI shows the four ST music projects, repository-backed evidence, warnings, next
safe boundaries, and a fresh deterministic plan that must pass the existing independent verifier.
Private repository reads can use `GITHUB_TOKEN`; the token itself is never rendered into the UI.

APP1 deliberately exposes no mutation endpoint yet. It is a real read/plan application rather than
a UI that pretends unsafe execution is available.

## Core safety model

The model never decides its own privilege level. Read-only work may run autonomously and reversible
feature-branch writes may run autonomously; protected/destructive/external operations remain host
or human gated.

No model-facing tool can directly:

- start training;
- promote or activate a checkpoint;
- switch the serving model;
- canonicalize a new baseline;
- execute rollback.

Every widening step is represented by a typed, evidence-bound contract and independently verified
before the next boundary may open.

## Music-domain evidence

`build_default_music_domain_toolset()` exposes read-only snapshots for:

- `music.score_restore.snapshot`
- `music.tab_engine.capability_snapshot`
- `music.score_editor.snapshot`
- `music.score_following.snapshot`

The evidence plane does not inflate authority: evaluation is not production permission,
REVIEW_REQUIRED is not canonical TAB export, editor feature completion is not release/cutover, and
score-following research is not pedagogical or production authority.

## Verified lifecycle

```text
source-provenanced music evidence
        ↓
deterministic planner → independent verifier
        ↓
guarded execution → exact commit + CI + validators
        ↓
verified execution evidence → curated dataset
        ↓
reproducible training contract + separate host authorization
        ↓
immutable model candidate
        ↓
paired baseline/candidate benchmark → promotion review
        ↓
activation request → separate host activation → activation receipt
        ↓
serving identity + health + shadow quality + rollback readiness
        ↓
canonical baseline review → separate host canonicalization
        ↓
3+ post-canonical stability rounds → Baseline Registry
        ↓
recurring drift watch
        ↓
healthy / observe / rollback review request
        ↓
separate host rollback action → rollback execution receipt
        ↓
2+ serving identity + health + recovery rounds
        ↓
append-only rollback generation
```

A25 does not allow a single bad observation to trigger rollback review. It requires sustained
regression and exact registry lineage. A26 still does not execute rollback: it records a separately
authorized external rollback only when the observed serving target exactly matches the approved
predecessor.

A successful rollback receipt is also insufficient for registry mutation. At least two ordered
post-rollback recovery rounds must pass. Baseline Registry then appends a new `rollback` generation
while retaining the degraded canonical generation as immutable history.

## Application boundary

APP1 sits above the A1-A26 core rather than bypassing it:

```text
browser
  ↓
Operator Console HTTP boundary
  ↓
read-only evidence adapters + PortfolioPlanningService
  ↓
A1-A26 guarded core
```

All current HTTP write methods fail closed. The next application stage will connect guarded
feature-branch task execution behind explicit task preview, policy decision and approval state.

## Resumable evidence state

`OrchestrationStateStore` hash-chains the model lifecycle through `baseline_registered`. Recurring
operational evidence uses `OperationalWatchStateStore`:

`baseline_bound -> drift_reviewed -> rollback_review_requested -> rollback_execution_recorded
-> post_rollback_recovery_reviewed -> rollback_baseline_registered`

Healthy watches may stop at `drift_reviewed`. Prompts, provider messages and hidden reasoning are
not stored as lifecycle evidence. Stage skipping, regression and silent replacement of prior
evidence fail closed.

## Development

```bash
python -m pip install -e '.[dev]'
ruff check src tests
pytest
```

See:

- [`docs/architecture.md`](docs/architecture.md)
- [`docs/operator-console.md`](docs/operator-console.md)
- [`docs/music-domain-evidence.md`](docs/music-domain-evidence.md)
- [`docs/planning-and-learning.md`](docs/planning-and-learning.md)
- [`docs/learning-evaluation.md`](docs/learning-evaluation.md)
- [`docs/execution-and-dataset.md`](docs/execution-and-dataset.md)
- [`docs/training-run.md`](docs/training-run.md)
- [`docs/model-candidate-promotion.md`](docs/model-candidate-promotion.md)
- [`docs/orchestration-activation.md`](docs/orchestration-activation.md)
- [`docs/runtime-activation.md`](docs/runtime-activation.md)
- [`docs/canonical-baseline.md`](docs/canonical-baseline.md)
- [`docs/post-canonical-stability.md`](docs/post-canonical-stability.md)
- [`docs/drift-and-rollback.md`](docs/drift-and-rollback.md)
- [`docs/rollback-recovery.md`](docs/rollback-recovery.md)
