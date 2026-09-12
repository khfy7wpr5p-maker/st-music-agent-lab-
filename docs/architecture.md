# ST Music Agent Lab — Architecture Map

Status: A1-A26 guarded core + APP1-APP4 runnable guarded application
Date: 2026-09-12

## Purpose

ST Music Agent Lab is the model-agnostic engineering and music-intelligence control layer for ST
projects. The A1-A26 core owns policy, tools, budgets, approvals, evidence, verification, learning,
training/model lifecycle, canonical-baseline history, drift and rollback-recovery boundaries.
APP1-APP4 provide the runnable operator application above those boundaries.

## Core map

```text
ST music repositories
  -> source-provenanced evidence
  -> deterministic planner
  -> independent verifier
  -> guarded reversible execution
  -> persistent exact task evidence
  -> exact-SHA CI + typed validators
  -> VERIFIED_SUCCESS
  -> bounded exact diff review
  -> human review acknowledgement bound to review_digest + HEAD
  -> human-gated PR creation
  -> exact PR head/base review evidence
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

APP1 starts with `st-music-agent app` and provides a mobile-friendly local web interface for:

- Score Restore;
- MusicXML → Guitar TAB;
- Score Editor;
- Real-Time Score Following;
- project state, warnings and next safe boundary;
- fresh portfolio planning with deterministic independent verification.

Per-project evidence failures are isolated so one unavailable repository does not crash the whole
console.

## APP2 — Guarded task execution

APP2 introduced an explicit task preview/run/PR boundary without creating a second mutation
architecture. Write mode is opt-in and loopback-only. The model can use bounded repository reads and
one `task.write_file` mutation whose branch is injected by the host. It cannot select `main`, create a
PR, merge, deploy, train, canonicalize or execute rollback.

## APP3 — Persistent execution evidence + CI/validator

APP3 keeps the APP2 write boundary and adds a durable evidence plane.

```text
browser instruction
  -> exact repository + base SHA
  -> deterministic st-agent/<project>/<task> feature branch
  -> append PREVIEWED to local hash-chained journal
  -> explicit Run click
  -> bounded ToolLoopRunner + task.write_file
  -> resolve exact final feature-branch HEAD
  -> exact base...HEAD compare
  -> CI_PENDING
  -> explicit host/browser CI refresh
  -> exact-SHA workflow selection
  -> typed validators: PASS / FAIL / UNAVAILABLE
  -> VERIFIED_SUCCESS only when required evidence passes
```

### APP3 persistent journal

The task store is append-only JSONL with a SHA-256 hash chain. It stores structured public task
metadata and bounded execution evidence, never provider chain-of-thought, API key values or raw
credentials.

Primary stage machine:

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

`FAILED` is terminal for a task identity. Stage skipping is rejected. Earlier evidence is retained.

### Exact execution evidence

A model message such as "done" is never success. APP3 requires a final full commit SHA different from
the preview base, then binds bounded changed-file evidence to the exact base/head pair.

### CI tracking

Core logic has no uncontrolled polling loop. CI is refreshed only by an explicit host/browser request.
Runs from another SHA cannot satisfy the task. Incomplete runs remain pending; completed non-success
runs fail the task.

### Validator contract

Validator results contain name, `PASS` / `FAIL` / `UNAVAILABLE`, evidence reference, exact commit SHA
and bounded public message. `UNAVAILABLE` cannot silently become `PASS`.

## APP4 — Exact review + immutable revisions + PR evidence

APP4 adds a human review plane without widening merge or production authority.

```text
VERIFIED_SUCCESS
  -> load bounded exact base...HEAD patch review
  -> calculate per-file patch SHA-256 digests
  -> calculate deterministic review_digest
  -> reject acknowledgement if any patch is missing/truncated
  -> explicit human acknowledgement for review_digest + exact HEAD
  -> recheck feature branch still equals exact task HEAD
  -> explicit human Open PR action
  -> read back PR head/base metadata
  -> append PR_REVIEW_SNAPSHOT
  -> merge remains unavailable
```

### Bounded exact diff review

APP4 projects at most 100 changed files, at most 16,000 displayed patch characters per file and at
most 160,000 displayed patch characters across the review. The digest is based on commit identity and
per-file patch digests/statistics rather than trusting the rendered UI alone.

If GitHub omits a textual patch or APP4 must truncate it, the review becomes incomplete. Incomplete
review evidence cannot be acknowledged and therefore cannot open a PR through APP4.

Deterministic attention labels highlight workflow/build configuration changes, removals/renames,
large changes and incomplete patches. These labels are review hints, not semantic correctness claims.

### Human review acknowledgement

`REVIEW_ACKNOWLEDGED` is append-only and bound to both the exact task HEAD and `review_digest`.
Moving the branch makes that acknowledgement stale. APP4 rechecks branch identity before PR creation.

This acknowledgement is not merge approval, release authorization or musical correctness.

### Retry / amend lineage

APP4 never rewrites failed or completed parent history.

- `retry` is allowed only for a `FAILED` parent task;
- `amend` requires exact parent commit evidence;
- a new deterministic child task is previewed through the existing APP3 path;
- parent and child receive append-only lineage events;
- parent stage/outcome/evidence remains unchanged;
- the child later receives its own branch, CI, validator, review and PR evidence.

This makes failed and superseded attempts auditable instead of silently converting them into success.

### Exact PR review evidence

After PR creation APP4 persists a `PR_REVIEW_SNAPSHOT` that binds:

- exact task HEAD;
- acknowledged review digest;
- PR number;
- PR head/base SHA metadata;
- draft/mergeable metadata when available;
- an exact-head-match flag.

The operator may explicitly refresh this metadata. A PR whose head/base no longer matches the verified
task evidence fails closed.

### APP4 journal evidence events

APP4 adds evidence events without changing the APP3 stage machine:

```text
REVIEW_SNAPSHOT
REVIEW_ACKNOWLEDGED
LINEAGE_PARENT
LINEAGE_CHILD_CREATED
PR_REVIEW_SNAPSHOT
```

## Branch confinement retained

The model does not receive `github.create_branch`, `github.open_pull_request` or merge tools. Its only
mutation tool is `task.write_file`, whose schema has no branch field. The host injects the exact
feature branch.

Repository discovery remains bounded: recursive tree truncation fails closed, credential-sensitive
paths are filtered, and excessive file counts are rejected rather than silently hidden.

## HTTP boundary retained

Task POSTs require a random per-process `X-ST-Session` token and bounded JSON bodies. Feature-branch
execution requires `--enable-writes`; write mode refuses non-loopback HTTP binding. Provider/GitHub
credentials are configured by environment-variable name and resolved only inside trusted adapters.

## Explicitly unavailable in APP4

- direct `main` / `master` mutation;
- arbitrary branch selection by the model;
- file deletion;
- autonomous PR creation;
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
9. Engineering success/review acknowledgement is not production authority or domain correctness.
10. Exact commit identity is required wherever CI/validator/review evidence widens task state.
11. Earlier task and revision evidence is append-only and cannot be silently replaced.
12. Tests define widened application behavior before merge.

## Next application boundary — APP5

APP5 should focus on real project-specific validator adapters and richer PR review collaboration
(review/thread evidence, project-aware validation summaries) while keeping merge and production
authority outside the agent application.
