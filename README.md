# ST Music Agent Lab

Model-agnostic orchestration core and runnable operator application for software-engineering and
music-intelligence work across ST projects.

## Current stage

The repository contains the A1-A26 guarded model lifecycle plus the runnable application layer:

- **APP1:** project evidence dashboard + independently verified portfolio planning;
- **APP2:** opt-in, loopback-only guarded engineering tasks on a host-bound feature branch;
- **APP3:** persistent resumable task evidence, exact commit/diff binding, explicit CI/validator
  review, and a human-triggered PR flow gated by `VERIFIED_SUCCESS`;
- **APP4:** bounded exact diff review, human review acknowledgement, immutable retry/amend child
  tasks, and PR review evidence bound to the verified task HEAD.

Package version: `0.28.0`.

## Run read / preview / review mode

```bash
python -m pip install -e '.[dev]'
st-music-agent app
```

Open `http://127.0.0.1:8765`.

This mode reads the four ST project evidence surfaces, builds a fresh verified portfolio plan,
previews engineering tasks, restores persisted task evidence, and can inspect exact APP4 diff review
bundles. It cannot execute model writes unless `--enable-writes` is supplied.

By default APP3/APP4 stores structured task evidence at:

```text
~/.st-music-agent/task-events.jsonl
```

Override with `--task-state-file PATH` or `ST_MUSIC_AGENT_TASK_STATE`. The journal stores bounded
public task/review evidence only; it does not store provider chain-of-thought, API keys, raw
credentials, or secret payloads.

## Run guarded feature-branch tasks

```bash
st-music-agent app \
  --enable-writes \
  --provider-base-url https://YOUR_PROVIDER/v1 \
  --provider-model YOUR_MODEL \
  --provider-api-key-env PROVIDER_API_KEY \
  --github-token-env GITHUB_TOKEN
```

Write mode is accepted only on a loopback host. Credential values remain inside trusted adapters.

The current APP4 flow is:

```text
instruction
  -> exact repo/base SHA preview + deterministic feature branch
  -> append-only PREVIEWED evidence
  -> explicit Run click
  -> bounded feature-branch agent execution
  -> exact final HEAD + bounded base...HEAD change evidence
  -> exact-SHA CI + typed validators
  -> VERIFIED_SUCCESS
  -> bounded exact patch review for the same base/head
  -> review_digest from commit identity + per-file patch digests
  -> explicit human acknowledgement of that exact review
  -> explicit human Open PR click
  -> PR head/base read-back + PR_REVIEW_SNAPSHOT
  -> merge remains unavailable
```

If any patch is unavailable or truncated by APP4 review limits, review is incomplete and cannot be
acknowledged. CI success and review acknowledgement are engineering evidence only; neither is musical
correctness, release readiness or production authorization.

## Retry and amend

APP4 never rewrites a failed or completed parent task. A retry/amend creates a separate child task:

- `retry` is for a `FAILED` parent;
- `amend` requires exact parent commit evidence;
- parent stage/outcome/evidence remains immutable;
- child receives a new task id and a new bounded feature branch through the existing APP3 path;
- parent/child lineage is appended to the same hash-chained journal.

## Persistent task lifecycle

```text
PREVIEWED
  -> BRANCH_CREATED
  -> AGENT_RUNNING
  -> AGENT_COMPLETED
  -> COMMIT_BOUND
  -> CI_PENDING
  -> CI_REVIEWED
  -> VALIDATORS_REVIEWED
  -> VERIFIED_SUCCESS
  -> PR_OPENED
```

A task can transition to terminal `FAILED`; it is not rewritten in place. Public outcomes are
`WORKING`, `REVIEW_REQUIRED`, `VERIFIED_SUCCESS`, and `FAILED`.

APP4 adds evidence events without widening the stage machine:

```text
REVIEW_SNAPSHOT
REVIEW_ACKNOWLEDGED
LINEAGE_PARENT / LINEAGE_CHILD_CREATED
PR_REVIEW_SNAPSHOT
```

## Core safety model

Read-only work may run autonomously. Reversible feature-branch writes may run when deterministic
policy says `AUTO_EXECUTE`. Protected/destructive/external actions remain host or human gated.

The application has no endpoint or model tool for:

- merge or auto-merge;
- direct `main` / `master` writes;
- file deletion;
- deployment/release;
- model training or production activation;
- canonicalization or rollback execution.

The model cannot choose the writable branch and cannot open a PR itself.

## Music-domain evidence

The operator console reads bounded snapshots from:

- Score Restore;
- MusicXML → Guitar TAB;
- Score Editor;
- Real-Time Score Following.

`REVIEW_REQUIRED` remains localized and must not become a global lock when a safe readable/reviewable
artifact can still be shown.

## Model lifecycle

The existing A1-A26 core remains authoritative for evidence, planning, execution records, curated
data, training lineage, model candidates, activation, canonicalization, baseline stability, drift,
rollback review, rollback receipts and post-rollback recovery. APP1-APP4 sit above that core without
replacing its policy or approval boundaries.

## Development

```bash
python -m pip install -e '.[dev]'
ruff check src tests
pytest
```

See:

- [`docs/architecture.md`](docs/architecture.md)
- [`docs/operator-console.md`](docs/operator-console.md)
- [`docs/app3-execution-evidence.md`](docs/app3-execution-evidence.md)
- [`docs/app4-review-and-revision.md`](docs/app4-review-and-revision.md)
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
