# ST Music Agent Lab — Architecture Map

Status: A1-A26 guarded core + APP1-APP8E bounded runnable application
Date: 2026-09-12

## Purpose

ST Music Agent Lab is the model-agnostic engineering and music-intelligence control layer for ST
projects. The A1-A26 core owns policy, tools, budgets, approvals, evidence, verification, learning,
training/model lifecycle, canonical-baseline history, drift and rollback-recovery boundaries.
APP1-APP8E provide the runnable operator/supervision application above those boundaries.

Critical production actions never become model self-authority.

## Full architecture map

```text
ST music repositories
  -> source-provenanced evidence
  -> deterministic planner
  -> independent verifier
  -> guarded reversible feature-branch execution
  -> persistent exact task evidence
  -> exact final commit identity
  -> exact-SHA CI
  -> generic + project-specific validators
  -> validator health/freshness
  -> VERIFIED_SUCCESS
  -> bounded exact diff review
  -> human review acknowledgement bound to review_digest + HEAD
  -> fresh-health gate before PR opening
  -> explicit human-gated PR creation
  -> exact PR head/base evidence
  -> bounded PR collaboration evidence
  -> trustworthy GraphQL thread resolution when available
  -> bounded audit JSON + journal anchor hash
  -> export digest/structure verification
  -> local hash-journal verification + deterministic evidence replay

  -> APP8A bounded multi-agent supervisor graph
  -> APP8B independent critic / reliability gate
  -> APP8C guarded exact-SHA multi-agent implementation cycle
  -> APP8D verified-receipt cross-project coordination
  -> APP8E append-only persistent supervision/coordination graph
  -> deterministic restart reconstruction + verification
  -> authenticated read-only operator graph view

  -> separately governed curated data / training contract
  -> immutable model candidate
  -> paired benchmark + promotion review
  -> separately authorized activation/canonicalization
  -> repeated health/stability evidence
  -> append-only Baseline Registry
  -> long-term drift watch
  -> host-reviewed rollback request
  -> separately authorized rollback receipt
  -> repeated recovery evidence
  -> append-only rollback generation
```

## APP1 — Operator Console

APP1 provides project evidence, warnings, next-safe-boundaries and independently verified portfolio
planning across Score Restore, MusicXML → Guitar TAB, Score Editor and Real-Time Score Following.

## APP2 — Guarded task execution

APP2 introduced opt-in loopback-only feature-branch execution. The model receives bounded repository
reads and one host-bound `task.write_file` mutation. It cannot select `main`, create/approve/merge a
PR, deploy, train, canonicalize or execute rollback.

## APP3 — Persistent execution evidence + CI/validators

APP3 adds an append-only SHA-256 journal, exact final task HEAD, bounded base...HEAD evidence,
exact-SHA CI selection and typed `PASS / FAIL / UNAVAILABLE` validators.

Primary task stages remain:

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

`FAILED` is terminal for a task identity. A model message such as "done" is never proof of success.

## APP4 — Exact review + immutable revisions + PR binding

APP4 binds bounded patch review to the exact task base/head, computes per-file digests and a
`review_digest`, requires explicit human acknowledgement and only then allows a separate human PR-open
action. Missing/truncated patch evidence cannot be acknowledged. Retry/amend creates a new child task
rather than rewriting the parent.

## APP5 — Project validation + PR collaboration evidence

APP5 runs the authoritative project adapter at the exact task HEAD:

- Score Restore -> `score_restore_current_truth`;
- MusicXML → Guitar TAB -> `tab_capability_contract`;
- Score Editor -> `score_editor_release_boundary`;
- Real-Time Score Following -> `score_following_research_boundary`.

Unreadable evidence remains `UNAVAILABLE`; contract violations are `FAIL`. PR collaboration refreshes
bounded review submissions, inline comments and conversation metadata while keeping merge authority
false. Raw PR comment bodies are not persisted; only body hashes/lengths are retained.

## APP6 — Validator health + trusted resolution + audit export

APP6 adds `VALIDATOR_HEALTH_SNAPSHOT`, bound to the exact validator event sequence/hash. Current
freshness is 900 seconds.

```text
all PASS + exact HEAD -> HEALTHY
UNAVAILABLE/incomplete -> DEGRADED
FAIL/wrong commit -> UNHEALTHY
```

At read time the snapshot becomes `FRESH_*` or `STALE_*`. Expiry never rewrites historical
`VERIFIED_SUCCESS`, but a new PR-open action requires `FRESH_HEALTHY` evidence.

For `api.github.com`, APP6 uses GitHub GraphQL `PullRequest.reviewThreads.isResolved` as the trusted
resolution source. Unsupported, failed or truncated GraphQL evidence remains explicitly unavailable.
The application cannot resolve/unresolve/dismiss a thread or approve a PR.

APP6 also exposes a bounded audit projection containing exact task identity, CI, validators, health,
review/PR evidence, lineage, journal event headers, an anchor sequence/hash and `audit_sha256`.

## APP7 — Deterministic audit verification/replay + remote read-only operator

APP7 separates export integrity from source-journal authenticity.

`verify_audit_export()` recomputes `audit_sha256`, checks exported journal counts/anchors and verifies
that merge/production authority remains false. A successful result is `STRUCTURE_VERIFIED`; it does
not claim source-journal authentication.

`verify_current_audit()` compares the export with the actual local hash-chained journal and requires
matching journal anchor, deterministic replay stage and deterministic replay outcome.

`replay_task()` is evidence replay only. It does not rerun a model, GitHub mutation, CI, external
validator, deployment, training, activation, canonicalization or rollback.

Remote mode is authenticated GET-only. It never returns a write-session token. Non-loopback binding
requires explicit secure-transport attestation because the built-in Python HTTP server does not provide
TLS.

Read-only APP7 endpoints include:

```text
GET /api/tasks/audit/<task_id>
GET /api/tasks/audit-verify/<task_id>
GET /api/tasks/replay/<task_id>
```

## APP8A — Bounded multi-agent supervisor

APP8A introduces typed multi-agent supervision contracts before allowing execution. The supervisor
constructs a deterministic dependency graph with explicit roles, evidence dependencies, mutation
classes, completion/abstention criteria and bounded budgets.

APP8A itself is non-mutating simulation. It cannot call a model or execute repository work merely by
creating a graph.

## APP8B — Independent critic and reliability gates

APP8B adds a separate evidence-bound critic/reliability layer. Acceptance is not derived from the same
agent that produced implementation output. Reliability gates remain explicit and fail closed when the
required exact evidence is missing or inconsistent.

Critic acceptance is evidence for the next guarded step; it is not merge, deployment or production
authority.

## APP8C — Guarded multi-agent execution

APP8C permits the bounded multi-agent architecture to reuse the existing APP2-APP7 reversible
feature-branch execution path. Exact repository/base SHA, host-bound feature branch, final head,
artifact digest, validators and reliability gate remain bound together.

A successful implementation cycle can produce a verified completion record, but it cannot self-open or
approve a PR, merge, deploy, train, activate/canonicalize a model or roll back production state.

## APP8D — Deterministic cross-project coordination

APP8D coordinates work across the four fixed ST repositories:

- `khfy7wpr5p-maker/st-score-restore-engine`
- `khfy7wpr5p-maker/musicxml-to-guitar-tab-engine`
- `khfy7wpr5p-maker/st-score-editor-core`
- `khfy7wpr5p-maker/st-real-time-score-following-lab`

A `CrossProjectPlan` declares exact base SHAs, dependency edges, required upstream evidence, produced
evidence and mutation class. Reversible feature-branch work is accepted only through an APP8C verified
cycle whose APP8B gate accepted the same exact artifact/head. Read-only work uses a host-verified exact
SHA receipt.

The coordinator never invokes project execution itself. It only schedules dependency-ready work and
accepts/rejects typed receipts. `REVIEW_REQUIRED`, `ABSTAINED` or `FAILED` upstream work deterministically
blocks dependents instead of being guessed through.

All APP8D plan/decision/receipt/replay authority flags keep repository mutation, PR opening, merge and
production actions false.

## APP8E — Persistent operator supervision graph

APP8E persists APP8A supervision graphs and APP8D coordination graphs to a separate append-only,
hash-chained JSONL journal:

```text
~/.st-music-agent/app8-graph-events.jsonl
```

The journal validates global record order, per-graph event order, registration-before-event ordering,
previous-record SHA-256 and current record SHA-256 on reload.

APP8E reconstructs typed plans/events and deterministically replays state after process restart. Resume
means state reconstruction only; it does not automatically run the next agent or mutation.

Read-only operator endpoints are:

```text
GET /api/app8/graphs?limit=N
GET /api/app8/graphs/<graph_id>
GET /api/app8/graphs/<graph_id>/verify
```

Remote mode reuses APP7 bearer authentication. APP8 graph endpoints are GET-only and there is no APP8
graph mutation endpoint.

## APP8 completion boundary

The current bounded APP8 architecture is complete at APP8E:

```text
APP8A Supervisor contracts/simulation
  -> APP8B Independent critic/reliability
  -> APP8C Guarded exact-SHA execution
  -> APP8D Cross-project verified-receipt coordination
  -> APP8E Persistent operator graph / deterministic resume
```

Further development must be driven by demonstrated operator needs. The immediate next step is a
controlled operational pilot against real exact repository SHAs, documented in
`docs/app8-operational-pilot.md`, not an automatic authority expansion.

## Persistent evidence and authority boundaries

The task journal and APP8 graph journal are separate evidence layers. Neither journal grants authority.

The model still has no branch argument on `task.write_file`, no PR-open tool, no PR approval tool, no
thread-resolution tool and no merge tool. Local task mutations require a per-process `X-ST-Session`
token. Credentials are resolved only inside trusted adapters.

## Explicitly unavailable

- direct `main` / `master` mutation by the model;
- arbitrary branch selection by the model;
- file deletion through the guarded task toolset;
- autonomous PR approval;
- review-thread resolution/dismissal authority;
- merge / auto-merge inside the application;
- release/deployment;
- training execution;
- model activation/canonicalization;
- rollback execution;
- remote write execution;
- APP8 graph mutation through HTTP;
- privilege or credential mutation.

## A1-A26 invariants retained

1. Models cannot grant themselves privileges or approvals.
2. Unknown tools never execute.
3. Secret/credential paths fail closed.
4. Reversible writes on non-protected branches may auto-execute only after deterministic policy.
5. Protected/destructive/external actions remain human/host gated.
6. Plans and lifecycle widening are independently recomputed from evidence.
7. Training, activation, canonicalization and rollback remain separate host-authorized boundaries.
8. Baseline history is append-only; failed generations are retained.
9. Engineering success/review/audit metadata is not production authority or domain correctness.
10. Exact commit identity is required wherever CI/validator/review evidence widens task state.
11. Earlier task, revision, collaboration and health evidence cannot be silently replaced.
12. Standalone export integrity is not misrepresented as source-journal authentication.
13. Remote access may reduce authority but may not silently widen it.
14. Multi-agent supervision cannot bypass existing feature-branch/exact-SHA boundaries.
15. Cross-project dependency progress requires typed verified receipts, not agent assertions.
16. Persistent APP8 replay reconstructs evidence state only and does not imply execution authority.
17. Tests define widened application behavior before merge.
