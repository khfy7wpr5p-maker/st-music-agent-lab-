# ST Music Agent Lab

Model-agnostic orchestration core for autonomous software-engineering and music-intelligence
agents across ST projects.

## Current stage

A1-A24 guarded agent + verified evidence/learning/training/model-runtime/canonical-baseline
stability foundation:

- **A1-A11:** guarded execution, deterministic privilege policy, budgets, approvals, sandboxing,
  bounded GitHub mutation and restricted OpenHands integration.
- **A12-A13:** read-only source-provenanced evidence from Score Restore, MusicXML/TAB, Score Editor
  and real-time score following.
- **A14-A18:** deterministic planning + independent verification, verified experience learning,
  paired evaluation, exact execution evidence and curated dataset export.
- **A19-A20:** reproducible training-run lineage, immutable trained-model candidate identity and
  independent promotion-review recomputation.
- **A21:** resumable hash-chained lifecycle state plus activation request with exact rollback
  binding.
- **A22:** host activation receipts and exact serving/health/shadow-quality/rollback-readiness
  evidence before canonical review.
- **A23:** canonical baseline review that recomputes A22 evidence, plus separately authorized
  canonicalization receipts binding exact previous/new baseline identities.
- **A24:** repeated post-canonical stability evidence plus an append-only baseline registry that
  records exact canonical lineage without granting model-switch or rollback authority.

Package version: `0.22.0`.

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
canonical baseline review (A22 evidence recomputed)
        ↓
separate host canonicalization → canonicalization receipt
        ↓
3+ post-canonical stability rounds
        ↓
append-only baseline registry
```

A successful A23 canonicalization is not considered a stable lifecycle endpoint by itself. A24
requires at least three ordered observation rounds, each with serving identity, health, quality and
rollback-readiness evidence. Only a fully successful recomputation is eligible for host baseline
registration.

The `BaselineRegistry` must be explicitly bootstrapped with the already-existing canonical model.
A new generation can then be appended only when the registered predecessor and rollback target
exactly match the A23 receipt. Registry records are hash-chained and keep `auto_switch=false` and
`auto_rollback=false`.

## Resumable evidence state

`OrchestrationStateStore` hash-chains structured fingerprints through the complete lifecycle up to
`baseline_registered`. Prompts, provider messages and hidden reasoning are not stored as lifecycle
evidence. Stage skipping, regression and silent replacement of prior evidence fail closed.

## Development

```bash
python -m pip install -e '.[dev]'
ruff check src tests
pytest
```

See:

- [`docs/architecture.md`](docs/architecture.md)
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
