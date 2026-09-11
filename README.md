# ST Music Agent Lab

Model-agnostic orchestration core and runnable operator application for software-engineering and
music-intelligence work across ST projects.

## Current stage

The repository contains the A1-A26 guarded model lifecycle plus the runnable application layer:

- **APP1:** project evidence dashboard + independently verified portfolio planning;
- **APP2:** opt-in, loopback-only guarded engineering tasks on a host-bound feature branch;
- **APP3:** persistent resumable task evidence, exact commit/diff binding, explicit CI/validator
  review, and a human-triggered PR flow gated by `VERIFIED_SUCCESS`.

Package version: `0.27.0`.

## Run read / preview mode

```bash
python -m pip install -e '.[dev]'
st-music-agent app
```

Open `http://127.0.0.1:8765`.

This mode reads the four ST project evidence surfaces, shows warnings/next-safe-boundaries, builds a
fresh deterministic plan, previews engineering tasks, and can inspect previously persisted APP3 task
evidence. It cannot execute model writes unless `--enable-writes` is supplied.

By default APP3 stores structured task evidence at:

```text
~/.st-music-agent/task-events.jsonl
```

A different local path can be selected with `--task-state-file PATH` or the
`ST_MUSIC_AGENT_TASK_STATE` environment variable. The journal stores task metadata and public
execution evidence only; it does not store provider chain-of-thought, API keys, raw credentials, or
secret payloads.

## Run guarded feature-branch tasks

```bash
st-music-agent app \
  --enable-writes \
  --provider-base-url https://YOUR_PROVIDER/v1 \
  --provider-model YOUR_MODEL \
  --provider-api-key-env PROVIDER_API_KEY \
  --github-token-env GITHUB_TOKEN
```

Write mode is accepted only on a loopback host. Provider/GitHub configuration names reference host
environment variables; credential values stay inside trusted adapters.

APP3 performs this bounded flow:

```text
instruction
  -> preview exact repo + base SHA + deterministic feature branch
  -> persist PREVIEWED metadata in append-only hash-chained task journal
  -> AutonomyPolicy verifies branch/write = AUTO_EXECUTE and PR = REQUIRE_HUMAN
  -> user clicks Run
  -> host creates exact st-agent/... feature branch
  -> model gets bounded repository reads + task.write_file
  -> task.write_file remains host-bound to that exact feature branch
  -> host resolves exact final feature-branch HEAD
  -> bounded base...HEAD compare records changed paths/stats
  -> state becomes CI_PENDING
  -> user/host explicitly refreshes CI + validator evidence
  -> only exact-HEAD workflow runs are considered
  -> typed validators report PASS / FAIL / UNAVAILABLE
  -> VERIFIED_SUCCESS only when required CI and validators pass
  -> user may explicitly click Open PR
  -> PR head/base binding is rechecked
  -> merge remains unavailable
```

There is no uncontrolled background polling loop in core logic. CI/validator refresh is triggered by
the browser or another explicit host request.

## Persistent task evidence

APP3 uses an append-only JSONL journal with a SHA-256 hash chain. Stage skipping is rejected, earlier
evidence is not silently replaced, and failed attempts are not rewritten as successful attempts.
After an app restart the operator can inspect persisted task status and exact commit evidence. A task
that still needs model execution can be re-previewed with the same instruction so its deterministic
identity is rebound in the new process.

The task lifecycle is:

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

A failed attempt can transition to `FAILED`; it is not rewritten in place. Public outcomes are
`WORKING`, `REVIEW_REQUIRED`, `VERIFIED_SUCCESS`, and `FAILED`.

## CI and validator semantics

APP3 never treats a model message such as "done" as proof of success. Success is bound to an exact
repository, feature branch and commit SHA. CI evidence for another SHA cannot satisfy the task.
Incomplete CI remains pending; failed CI cannot become `VERIFIED_SUCCESS`.

Validators use a typed contract containing validator name, `PASS` / `FAIL` / `UNAVAILABLE`, evidence
reference, exact commit SHA, and a bounded message. `UNAVAILABLE` never silently becomes `PASS`.
Generic APP3 validators establish exact commit binding and bounded diff evidence. Project profiles are
configuration data; they can name additional real host validators or required workflow names when
those checks actually exist.

CI success is engineering evidence, not proof of musical correctness, release readiness, model
promotion, deployment safety, or production authorization.

## Core safety model

Read-only work may run autonomously. Reversible feature-branch writes may run when deterministic
policy says `AUTO_EXECUTE`. Protected-branch, destructive and external side effects remain host or
human gated.

The application has no endpoint or model tool for:

- merge or direct `main` / `master` writes;
- file deletion;
- deployment/release;
- model training or production activation;
- canonicalization or rollback execution.

PR creation remains a distinct human/host action and APP3 additionally requires exact verified task
evidence before that action is allowed.

## Music-domain evidence

The operator console reads bounded snapshots from:

- Score Restore;
- MusicXML → Guitar TAB;
- Score Editor;
- Real-Time Score Following.

One inaccessible repository is isolated to its project card. `REVIEW_REQUIRED` remains localized in
music-domain workflows and must not become a global lock when a readable/reviewable artifact can be
shown safely.

## Model lifecycle

The existing A1-A26 core remains authoritative for evidence, planning, execution records, curated
data, training lineage, model candidates, activation, canonicalization, baseline stability, drift,
rollback review, rollback receipts and post-rollback recovery. APP1-APP3 sit above that core rather
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
- [`docs/app3-execution-evidence.md`](docs/app3-execution-evidence.md)
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
