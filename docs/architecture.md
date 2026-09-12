# ST Music Agent Lab — Architecture Map

Status: A1-A26 guarded core + APP1-APP7 runnable guarded application
Date: 2026-09-12

## Purpose

ST Music Agent Lab is the model-agnostic engineering and music-intelligence control layer for ST
projects. The A1-A26 core owns policy, tools, budgets, approvals, evidence, verification, learning,
training/model lifecycle, canonical-baseline history, drift and rollback-recovery boundaries.
APP1-APP7 provide the runnable operator application above those boundaries.

## Core map

```text
ST music repositories
  -> source-provenanced evidence
  -> deterministic planner
  -> independent verifier
  -> guarded reversible feature-branch execution
  -> persistent exact task evidence
  -> exact-SHA CI
  -> generic + project-specific validators
  -> validator health/freshness
  -> VERIFIED_SUCCESS
  -> bounded exact diff review
  -> human review acknowledgement bound to review_digest + HEAD
  -> fresh-health gate before PR opening
  -> human-gated PR creation
  -> exact PR head/base evidence
  -> bounded PR collaboration evidence
  -> trustworthy GraphQL thread resolution when available
  -> bounded audit JSON + journal anchor hash
  -> export digest/structure verification
  -> local hash-journal verification + deterministic evidence replay
  -> curated data / training contract
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

Critical production actions never become model self-authority.

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

## APP7 — Deterministic audit verification/replay

APP7 separates export integrity from source-journal authenticity.

### Export verification

`verify_audit_export()` recomputes `audit_sha256`, checks exported journal counts/anchors and verifies
that merge/production authority remains false. A successful result is `STRUCTURE_VERIFIED`; it
explicitly sets `source_journal_authenticated: false` because a standalone export cannot prove which
journal produced it.

### Local verification

`verify_current_audit()` compares the export with the actual local hash-chained journal:

- local latest task sequence == audit anchor sequence;
- local latest task hash == audit anchor hash;
- deterministic replay stage == audit stage;
- deterministic replay outcome == audit outcome.

The underlying `TaskEventStore` validates the global append-only SHA-256 chain when loading the journal.

### Deterministic replay

`replay_task()` walks recorded task events, checks the APP3 stage-transition graph and derives the final
stage/outcome. Replay emits a deterministic digest over event headers and derived state.

Replay is **evidence replay**, not execution replay. It does not rerun a model, GitHub mutation, CI,
external validator, deployment, training, activation, canonicalization or rollback.

Read-only endpoints are:

```text
GET /api/tasks/audit/<task_id>
GET /api/tasks/audit-verify/<task_id>
GET /api/tasks/replay/<task_id>
```

## APP7 — Authenticated remote read-only operator

Remote operation is a separate authority profile, not a remotely exposed version of local write mode.

### Authentication

Remote mode requires `--remote-read-only` plus an environment-variable name containing a bearer token
of at least 24 characters. The application keeps the SHA-256 digest for constant-time comparison; the
browser keeps the entered bearer token in `sessionStorage`.

Only `/` and `/api/remote-mode` are public. They expose the login shell/capability metadata, not task
or project evidence. Other data endpoints require `Authorization: Bearer ...`.

### Mutation confinement

In remote mode:

- `TaskExecutionConfig.enabled` must be false;
- `/api/session` returns no write-session token;
- every non-GET request returns `405 remote_read_only` before inherited mutation handlers execute;
- task execution, evidence-refresh journal writes, exact-review loading/acknowledgement, revisions and
  PR creation are unavailable;
- merge/auto-merge, review-thread mutation and production lifecycle actions remain unavailable.

### Network threat boundary

The built-in `ThreadingHTTPServer` does not provide TLS. Normal APP7 mode therefore rejects every
non-loopback bind. A non-loopback bind is accepted only in authenticated remote read-only mode and only
when the operator explicitly provides `--remote-secure-transport-attested`.

That flag is a human assertion, not transport detection. It is intended for an existing SSH tunnel,
private encrypted VPN/tunnel or TLS reverse proxy. Direct public-internet exposure of the built-in HTTP
listener is outside the APP7 threat model.

The preferred remote topology is:

```text
remote browser
  -> authenticated encrypted tunnel / TLS proxy
  -> 127.0.0.1 APP7 remote-read-only listener
  -> authenticated GET-only evidence APIs
```

## Persistent evidence and authority boundaries

APP7 does not add or skip task stages and does not need a new journal event. Audit verification and
replay are derived read-only evidence.

The model still has no branch argument on `task.write_file`, no PR-open tool, no PR approval tool, no
thread-resolution tool and no merge tool. Local task mutations require a per-process `X-ST-Session`
token. Credentials are resolved only inside trusted adapters.

## Explicitly unavailable in APP7

- direct `main` / `master` mutation;
- arbitrary branch selection by the model;
- file deletion;
- autonomous PR creation or approval;
- review-thread resolution/dismissal authority;
- merge / auto-merge;
- release/deployment;
- training execution;
- model activation/canonicalization;
- rollback execution;
- remote write execution.

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
14. Tests define widened application behavior before merge.

## Future application boundary

No APP8 authority expansion is implied by APP7. A future stage should be justified by observed daily
operator needs and must preserve the same separation between evidence, human approval and production
authority.
