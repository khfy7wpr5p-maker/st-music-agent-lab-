# ST Music Agent Lab

Model-agnostic orchestration core and runnable operator application for software-engineering and
music-intelligence work across ST projects.

## Current stage

The repository contains the A1-A26 guarded model lifecycle plus the runnable application layer:

- **APP1:** project evidence dashboard + independently verified portfolio planning;
- **APP2:** opt-in, loopback-only guarded engineering tasks on a host-bound feature branch.

Package version: `0.26.0`.

## Run read / preview mode

```bash
python -m pip install -e '.[dev]'
st-music-agent app
```

Open `http://127.0.0.1:8765`.

This mode reads the four ST project evidence surfaces, shows warnings/next-safe-boundaries, builds a
fresh deterministic plan, and can preview an engineering task. It cannot create branches or write
files.

## Run guarded feature-branch tasks

```bash
st-music-agent app \
  --enable-writes \
  --provider-base-url https://YOUR_PROVIDER/v1 \
  --provider-model YOUR_MODEL \
  --provider-api-key-env PROVIDER_API_KEY \
  --github-token-env GITHUB_TOKEN
```

Write mode is accepted only on a loopback host. The provider/GitHub values above are environment
variable names; credential values stay inside trusted adapters.

APP2 performs this bounded flow:

```text
instruction
  -> preview exact repo + main SHA + deterministic feature branch
  -> AutonomyPolicy verifies branch/write = auto_execute and PR = require_human
  -> user clicks run
  -> host creates exact st-agent/... feature branch
  -> model gets bounded repository reads + task.write_file
  -> task.write_file is host-bound to that exact feature branch
  -> branch head / workflow evidence returned
  -> user may explicitly click Open PR
  -> merge remains unavailable
```

The model is never given a branch-selection field for writes and never receives create-PR, merge,
deploy, training, activation, canonicalization or rollback tools.

## Core safety model

Read-only work may run autonomously. Reversible feature-branch writes may run when the deterministic
policy says `auto_execute`. Protected-branch, destructive and external side effects remain host or
human gated.

The application still has no endpoint for:

- merge or direct `main`/`master` writes;
- file deletion;
- deployment/release;
- model training or production activation;
- canonicalization or rollback execution.

A successful APP2 development task is evidence, not production authority.

## Music-domain evidence

The operator console reads bounded snapshots from:

- Score Restore;
- MusicXML → Guitar TAB;
- Score Editor;
- Real-Time Score Following.

One inaccessible repository is isolated to its project card. The verified plan is shown only after
independent deterministic recomputation passes.

## Model lifecycle

The existing A1-A26 core remains authoritative for evidence, planning, execution records, curated
data, training lineage, model candidates, activation, canonicalization, baseline stability, drift,
rollback review, rollback receipts and post-rollback recovery. APP1/APP2 sit above that core rather
than replacing its policy or approval boundaries.

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
