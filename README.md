# ST Music Agent Lab

Model-agnostic orchestration core and runnable operator application for software-engineering and
music-intelligence work across ST projects.

## Current stage

The repository contains the A1-A26 guarded model lifecycle plus the runnable application layer:

- **APP1:** project evidence dashboard + independently verified portfolio planning;
- **APP2:** opt-in, loopback-only guarded engineering tasks on a host-bound feature branch;
- **APP3:** persistent resumable task evidence, exact commit/diff binding and exact-SHA CI/validator review;
- **APP4:** bounded exact diff review, human review acknowledgement, immutable retry/amend child tasks and exact PR binding;
- **APP5:** real project-specific exact-HEAD validators plus bounded PR review/thread/conversation evidence.

Package version: `0.29.0`.

## Run read / preview / review mode

```bash
python -m pip install -e '.[dev]'
st-music-agent app
```

Open `http://127.0.0.1:8765`.

This mode reads the four ST project evidence surfaces, builds a verified portfolio plan, previews
engineering tasks, restores persisted task evidence, inspects exact APP4 diff review bundles and shows
APP5 project-validation / PR-collaboration evidence. It cannot execute model writes unless
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

The current APP5 flow is:

```text
instruction
  -> exact repository/base SHA preview + deterministic feature branch
  -> explicit Run click
  -> bounded feature-branch agent execution
  -> exact final HEAD + bounded base...HEAD evidence
  -> exact-SHA CI
  -> generic validators
  -> project-specific authoritative evidence adapter at the exact task HEAD
  -> VERIFIED_SUCCESS only when required evidence passes
  -> bounded exact diff review + review_digest
  -> explicit human review acknowledgement
  -> explicit human PR creation
  -> exact PR head/base evidence
  -> optional bounded PR review/thread/conversation refresh
  -> merge remains unavailable
```

## Project-specific APP5 validators

APP5 does not relabel generic CI as domain correctness. It reuses the existing authoritative project
evidence adapters at the exact task commit:

- **Score Restore:** current-truth contract and safety claims such as no automatic production promotion and no implied OMR/musical truth;
- **MusicXML → Guitar TAB:** capability-driven `REVIEW_REQUIRED`, PASS-only canonical/export boundaries and approximate playback contract;
- **Score Editor:** repository-reality contract with release/cutover gates still separate from feature development;
- **Real-Time Score Following:** permanent research evidence with production/pedagogical authority and acoustic mono-mixture claims kept closed.

A malformed project contract is `FAIL`. Evidence that cannot be read is `UNAVAILABLE`; it never
silently becomes `PASS`.

## PR collaboration evidence

After a PR is opened, APP5 can explicitly refresh bounded review collaboration evidence:

- review submissions and their commit IDs;
- exact-HEAD approvals / change requests;
- stale reviews belonging to another commit;
- inline review-comment threads;
- general PR conversation comments.

GitHub REST does not expose thread-resolution state in this adapter, so resolution remains explicitly
`unavailable` rather than being inferred. PR collaboration evidence is append-only and is never merge
authority.

## Retry and amend

APP4/APP5 never rewrite a failed or completed parent task. `retry` and `amend` create separate child
tasks with parent/child lineage in the same journal.

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

A task may terminate as `FAILED`. Public outcomes remain `WORKING`, `REVIEW_REQUIRED`,
`VERIFIED_SUCCESS`, and `FAILED`.

Additional append-only review events now include:

```text
REVIEW_SNAPSHOT
REVIEW_ACKNOWLEDGED
LINEAGE_PARENT / LINEAGE_CHILD_CREATED
PR_REVIEW_SNAPSHOT
PR_COLLABORATION_SNAPSHOT
```

## Core safety model

Read-only work may run autonomously. Reversible feature-branch writes may run only when deterministic
policy allows them. Protected/destructive/external actions remain host or human gated.

The application exposes no model tool or HTTP endpoint for:

- merge or auto-merge;
- direct `main` / `master` writes;
- file deletion;
- deployment/release;
- model training or production activation;
- canonicalization or rollback execution.

The model cannot choose the writable branch, approve a PR, or merge it.

## Model lifecycle

The A1-A26 core remains authoritative for evidence, planning, execution records, curated data,
training lineage, model candidates, activation, canonicalization, baseline stability, drift, rollback
review, rollback receipts and post-rollback recovery. APP1-APP5 sit above that core without replacing
its policy or approval boundaries.

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
