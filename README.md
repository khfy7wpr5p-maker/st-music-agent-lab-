# ST Music Agent Lab

Model-agnostic orchestration core and runnable operator application for software-engineering and
music-intelligence work across ST projects.

## Current stage

The repository contains the A1-A26 guarded model lifecycle plus the runnable application layer through
APP8E:

- **APP1:** project evidence dashboard + independently verified portfolio planning;
- **APP2:** opt-in, loopback-only guarded engineering tasks on a host-bound feature branch;
- **APP3:** persistent resumable task evidence, exact commit/diff binding and exact-SHA CI/validator review;
- **APP4:** bounded exact diff review, human review acknowledgement, immutable retry/amend child tasks and exact PR binding;
- **APP5:** real project-specific exact-HEAD validators plus bounded PR review/thread/conversation evidence;
- **APP6:** validator health/freshness, trustworthy GitHub review-thread resolution when available, and bounded audit JSON export;
- **APP7:** deterministic audit verification/replay plus an authenticated remote read-only operator mode with an explicit secure-transport boundary;
- **APP8A:** bounded multi-agent supervisor contracts and deterministic simulation;
- **APP8B:** independent critic/reliability gates;
- **APP8C:** guarded multi-agent execution that reuses exact-SHA feature-branch evidence boundaries;
- **APP8D:** receipt-driven deterministic cross-project coordination across the four ST music repositories;
- **APP8E:** append-only persistent supervision/coordination graphs with deterministic restart replay and authenticated read-only operator graph views.

Package version: `0.36.0`.

APP8E is the completion boundary for the current bounded APP8 supervision architecture. New authority is
not implied by completion of APP8.

## Run local operator mode

```bash
python -m pip install -e '.[dev]'
st-music-agent app
```

Open `http://127.0.0.1:8765`.

Local mode reads the four ST project evidence surfaces, builds verified portfolio plans, previews tasks,
restores persistent evidence, inspects exact diff/review evidence, displays validator health, exports
bounded audits, verifies/replays the local task journal, and exposes persistent APP8 supervision graph
observability. Model writes remain disabled unless `--enable-writes` is supplied.

Task evidence is stored by default at:

```text
~/.st-music-agent/task-events.jsonl
```

APP8 graph evidence is stored by default at:

```text
~/.st-music-agent/app8-graph-events.jsonl
```

Override these with `--task-state-file PATH` / `ST_MUSIC_AGENT_TASK_STATE` and
`--app8-graph-state-file PATH` / `ST_MUSIC_AGENT_APP8_GRAPH_STATE`.

Both journals are append-only SHA-256 hash-chained evidence stores. They do not store provider
chain-of-thought, API keys, raw credentials or secret payloads.

## Run guarded local feature-branch tasks

```bash
st-music-agent app \
  --enable-writes \
  --provider-base-url https://YOUR_PROVIDER/v1 \
  --provider-model YOUR_MODEL \
  --provider-api-key-env PROVIDER_API_KEY \
  --github-token-env GITHUB_TOKEN
```

Write mode is loopback-only. Credential values remain inside trusted adapters. Existing APP2-APP7
feature-branch restrictions remain authoritative when APP8C is used.

## Run authenticated remote read-only mode

Remote operation is a separate read-only mode; it does **not** turn the local write console into a
remotely writable service.

```bash
export ST_REMOTE_OPERATOR_TOKEN='use-a-long-random-token-here'

st-music-agent app \
  --remote-read-only \
  --remote-auth-token-env ST_REMOTE_OPERATOR_TOKEN
```

The safest pattern is to keep the app bound to `127.0.0.1` and reach it through an authenticated SSH,
VPN, private-tunnel or HTTPS reverse-proxy boundary.

A non-loopback bind is rejected unless the operator explicitly attests that a private/encrypted
transport already exists:

```bash
st-music-agent app \
  --host 0.0.0.0 \
  --remote-read-only \
  --remote-auth-token-env ST_REMOTE_OPERATOR_TOKEN \
  --remote-secure-transport-attested
```

The built-in Python HTTP server does not provide TLS. The attestation flag is an explicit human
security assertion, not cryptographic proof that transport is encrypted. Do not expose the built-in
HTTP listener directly to the public internet.

Remote mode behavior:

- bearer authentication is required for data endpoints;
- the bearer token must contain at least 24 characters;
- the server keeps a SHA-256 token digest for request comparison rather than copying the raw token into application state;
- the browser keeps the token only in `sessionStorage`;
- the write session token is not returned remotely;
- every non-GET request is rejected;
- task execution, evidence-refresh writes, review acknowledgement, revisions and PR creation are unavailable remotely;
- APP8 graph list/detail/verify endpoints are authenticated GET-only;
- merge/auto-merge and production authority remain unavailable.

The root login shell and `/api/remote-mode` capability probe are public but contain no task or project
evidence.

## Current guarded task flow

```text
instruction
  -> exact repository/base SHA preview + deterministic feature branch
  -> explicit local Run click
  -> bounded feature-branch agent execution
  -> exact final HEAD + bounded base...HEAD evidence
  -> exact-SHA CI
  -> generic + project-specific exact-HEAD validators
  -> validator health/freshness
  -> VERIFIED_SUCCESS
  -> bounded exact diff review + human acknowledgement
  -> fresh healthy validation required before PR opening
  -> explicit local human PR creation
  -> exact PR head/base + collaboration evidence
  -> trusted GraphQL thread resolution when available
  -> bounded audit JSON export
  -> export digest/structure verification
  -> local hash-journal verification + deterministic replay
  -> merge remains unavailable inside the application
```

## Current APP8 flow

```text
APP8A bounded supervisor graph
  -> APP8B independent critic/reliability gate
  -> APP8C guarded exact-SHA implementation cycle
  -> APP8D verified-receipt cross-project coordination
  -> APP8E persistent hash-chained graph state
  -> deterministic restart reconstruction / replay
  -> authenticated read-only graph operator view
```

APP8E resume means deterministic state reconstruction only. It does not automatically rerun a model,
resume a repository write, create a branch, open a PR, merge, deploy, train, activate, canonicalize or
roll back anything.

Read-only graph endpoints:

```text
GET /api/app8/graphs?limit=N
GET /api/app8/graphs/<graph_id>
GET /api/app8/graphs/<graph_id>/verify
```

There is no APP8 graph mutation endpoint.

## Audit verification and replay

APP7 separates two claims that must not be confused:

1. **Export verification** checks the `audit_sha256`, structural counts/anchors and authority flags. It
   proves the JSON has not changed since its digest was computed, but does **not** authenticate the
   origin journal by itself.
2. **Local verification/replay** compares the audit anchor with the real local hash-chained journal and
   deterministically replays stage/outcome progression. This is the stronger verification surface.

Read-only endpoints:

```text
GET /api/tasks/audit/<task_id>
GET /api/tasks/audit-verify/<task_id>
GET /api/tasks/replay/<task_id>
```

Replay does not rerun model calls, GitHub mutations, CI, deployments or production actions. It only
reconstructs and verifies recorded task-state progression from the journal.

## Validator health and project-specific validation

APP6-APP8 retain the 15-minute validator freshness window and project-aware exact-HEAD validators:

- **Score Restore:** `score_restore_current_truth`;
- **MusicXML → Guitar TAB:** `tab_capability_contract`;
- **Score Editor:** `score_editor_release_boundary`;
- **Real-Time Score Following:** `score_following_research_boundary`.

Historical `VERIFIED_SUCCESS` is never rewritten by expiry. New PR opening requires `FRESH_HEALTHY`
validation.

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

APP8 does not add or skip APP3 task stages. Supervision and coordination graphs are a separate evidence
layer above the existing task lifecycle.

## Core safety model

The application exposes no model tool or HTTP endpoint for merge or auto-merge, direct `main` /
`master` writes, file deletion, deployment/release, model training/production activation,
canonicalization or rollback execution. The model cannot choose the writable branch, approve a PR,
resolve a review thread, or merge it.

APP8 coordination decisions, completion receipts, graph summaries and verification payloads explicitly
keep execution/repository-mutation/PR-open/merge/production authorization false unless an existing,
separately guarded host boundary is used for the permitted reversible action.

The A1-A26 core remains authoritative for lifecycle and production boundaries. APP1-APP8E sit above
that core without replacing its policy or approval model.

## Operational pilot

The first post-APP8 step is a controlled exact-SHA pilot across the real ST repositories, not an
automatic authority expansion. The pilot snapshot and pass criteria are documented in
[`docs/app8-operational-pilot.md`](docs/app8-operational-pilot.md).

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
- [`docs/app7-audit-replay-remote-operator.md`](docs/app7-audit-replay-remote-operator.md)
- [`docs/pre-app8-multi-agent-supervision-architecture.md`](docs/pre-app8-multi-agent-supervision-architecture.md)
- [`docs/app8a-supervisor-simulation.md`](docs/app8a-supervisor-simulation.md)
- [`docs/app8b-reliability-gates.md`](docs/app8b-reliability-gates.md)
- [`docs/app8c-guarded-execution.md`](docs/app8c-guarded-execution.md)
- [`docs/app8d-cross-project-coordination.md`](docs/app8d-cross-project-coordination.md)
- [`docs/app8e-persistent-operator-graph.md`](docs/app8e-persistent-operator-graph.md)
- [`docs/app8-operational-pilot.md`](docs/app8-operational-pilot.md)
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
