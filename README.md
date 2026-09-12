# ST Music Agent Lab

Model-agnostic orchestration core and runnable operator application for software-engineering and
music-intelligence work across ST projects.

## Current stage

The repository contains the A1-A26 guarded model lifecycle plus the runnable application layer:

- **APP1:** project evidence dashboard + independently verified portfolio planning;
- **APP2:** opt-in, loopback-only guarded engineering tasks on a host-bound feature branch;
- **APP3:** persistent resumable task evidence, exact commit/diff binding and exact-SHA CI/validator review;
- **APP4:** bounded exact diff review, human review acknowledgement, immutable retry/amend child tasks and exact PR binding;
- **APP5:** real project-specific exact-HEAD validators plus bounded PR review/thread/conversation evidence;
- **APP6:** validator health/freshness, trustworthy GitHub review-thread resolution when available, and bounded audit JSON export.

Package version: `0.30.0`.

## Run read / preview / review / audit mode

```bash
python -m pip install -e '.[dev]'
st-music-agent app
```

Open `http://127.0.0.1:8765`.

This mode reads the four ST project evidence surfaces, builds a verified portfolio plan, previews
engineering tasks, restores persisted evidence, inspects exact diff/review evidence, displays validator
health and can export a bounded task audit bundle. It cannot execute model writes unless
`--enable-writes` is supplied.

Task evidence is stored by default at:

```text
~/.st-music-agent/task-events.jsonl
```

Override with `--task-state-file PATH` or `ST_MUSIC_AGENT_TASK_STATE`. The append-only SHA-256
hash-chained journal stores bounded public task/review evidence only; it does not store provider
chain-of-thought, API keys, raw credentials or secret payloads.

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

The current APP6 flow is:

```text
instruction
  -> exact repository/base SHA preview + deterministic feature branch
  -> explicit Run click
  -> bounded feature-branch agent execution
  -> exact final HEAD + bounded base...HEAD evidence
  -> exact-SHA CI
  -> generic + project-specific exact-HEAD validators
  -> validator health snapshot with freshness expiry
  -> VERIFIED_SUCCESS
  -> bounded exact diff review + human acknowledgement
  -> fresh healthy validator evidence required before PR opening
  -> explicit human PR creation
  -> exact PR head/base evidence
  -> optional bounded PR review/thread/conversation refresh
  -> GitHub GraphQL resolved/unresolved evidence when trustworthy API access is available
  -> bounded audit JSON export with journal anchor hash
  -> merge remains unavailable
```

## Validator health and freshness

APP6 records a `VALIDATOR_HEALTH_SNAPSHOT` from the latest exact validator snapshot. The current
freshness window is 15 minutes. `VERIFIED_SUCCESS` remains part of immutable history when the window
expires, but a new PR-opening action requires `FRESH_HEALTHY` evidence. A stale, failed, mismatched or
unavailable validator surface requires an explicit evidence refresh.

## Project-specific validators

APP6 retains the APP5 project-aware validators at the exact task commit:

- **Score Restore:** current-truth contract and safety claims;
- **MusicXML → Guitar TAB:** capability-driven `REVIEW_REQUIRED` and PASS-only canonical/export boundaries;
- **Score Editor:** repository-reality contract with release/cutover gates separate;
- **Real-Time Score Following:** research evidence with production/pedagogical authority kept closed.

Unreadable evidence remains `UNAVAILABLE`, not `PASS`.

## PR collaboration and resolution evidence

APP6 retains bounded APP5 review/comment evidence and, for `api.github.com`, uses GitHub GraphQL
`reviewThreads.isResolved` as the authoritative source for resolved/unresolved thread state. If GraphQL
is unavailable, errors, or exceeds the configured bound, resolution remains explicitly unavailable;
APP6 never infers resolution from comment text.

Review metadata never authorizes merge.

## Audit export

`GET /api/tasks/audit/<task_id>` returns a bounded derived JSON bundle containing exact repository/
commit identity, CI, validators, freshness state, review digests, PR metadata, collaboration summary,
lineage, journal sequence/hash anchors and an `audit_sha256` digest. It excludes raw provider reasoning,
credentials and raw PR comment bodies.

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

APP6 adds evidence without widening the stage machine:

```text
VALIDATOR_HEALTH_SNAPSHOT
```

Existing review/lineage/collaboration evidence remains append-only.

## Core safety model

The application exposes no model tool or HTTP endpoint for merge or auto-merge, direct `main` /
`master` writes, file deletion, deployment/release, model training/production activation,
canonicalization or rollback execution. The model cannot choose the writable branch, approve a PR,
resolve a review thread, or merge it.

The A1-A26 core remains authoritative for lifecycle and production boundaries. APP1-APP6 sit above
that core without replacing its policy or approval model.

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
- [`docs/app5-project-validation-and-pr-collaboration.md`](docs/app5-project-validation-and-pr-collaboration.md)
- [`docs/app6-health-resolution-audit.md`](docs/app6-health-resolution-audit.md)
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
