# ST Music Agent Lab — Architecture Map

Status: A1-A26 guarded core + APP1-APP6 runnable guarded application
Date: 2026-09-12

## Purpose

ST Music Agent Lab is the model-agnostic engineering and music-intelligence control layer for ST
projects. The A1-A26 core owns policy, tools, budgets, approvals, evidence, verification, learning,
training/model lifecycle, canonical-baseline history, drift and rollback-recovery boundaries.
APP1-APP6 provide the runnable operator application above those boundaries.

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

APP6 hardens operational use of APP5 evidence.

### Validator freshness

Each explicit evidence refresh creates `VALIDATOR_HEALTH_SNAPSHOT`, bound to the exact validator event
sequence/hash. Current freshness is 900 seconds.

```text
all PASS + exact HEAD -> HEALTHY
UNAVAILABLE/incomplete -> DEGRADED
FAIL/wrong commit -> UNHEALTHY
```

At read time the snapshot becomes `FRESH_*` or `STALE_*`. Expiry never rewrites historical
`VERIFIED_SUCCESS`, but a new PR-open action requires `FRESH_HEALTHY` evidence and therefore fails
closed when validation is stale.

### Review-thread resolution

For `api.github.com`, APP6 uses GitHub GraphQL `PullRequest.reviewThreads.isResolved` as the trusted
resolution source. The adapter is bounded to 100 threads and 20 comments per thread. Unsupported,
failed or truncated GraphQL evidence stays explicitly unavailable; resolution is never inferred from
comment text.

The application still cannot resolve/unresolve/dismiss a thread or approve a PR.

### Audit export

APP6 exposes a read-only task audit projection at:

```text
GET /api/tasks/audit/<task_id>
```

The bundle contains exact repo/commit identity, CI, validators, health, review digests, PR binding,
collaboration summary, lineage, bounded journal event headers, journal anchor sequence/hash and an
`audit_sha256`. Provider chain-of-thought, credentials and raw PR comment bodies are excluded.

### APP6 evidence event

```text
VALIDATOR_HEALTH_SNAPSHOT
```

APP6 does not add or skip task stages.

## Branch and HTTP confinement retained

The model has no branch argument on `task.write_file`, no PR-open tool, no PR approval tool, no thread
resolution tool and no merge tool. Task mutations require a per-process `X-ST-Session` token. Write
mode is loopback-only. Credentials are resolved only inside trusted adapters.

## Explicitly unavailable in APP6

- direct `main` / `master` mutation;
- arbitrary branch selection by the model;
- file deletion;
- autonomous PR creation or approval;
- review-thread resolution/dismissal authority;
- merge / auto-merge;
- release/deployment;
- training execution;
- model activation/canonicalization;
- rollback execution.

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
12. Tests define widened application behavior before merge.

## Next application boundary — APP7

A later APP7 should be justified by daily operator needs. Likely candidates are deterministic audit
verification/replay and a separately threat-modeled authenticated remote operator mode. Neither should
implicitly add merge or production authority.
