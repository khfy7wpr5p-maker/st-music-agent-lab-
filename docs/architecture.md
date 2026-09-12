# ST Music Agent Lab — Architecture Map

Status: A1-A26 guarded core + APP1-APP5 runnable guarded application
Date: 2026-09-12

## Purpose

ST Music Agent Lab is the model-agnostic engineering and music-intelligence control layer for ST
projects. The A1-A26 core owns policy, tools, budgets, approvals, evidence, verification, learning,
training/model lifecycle, canonical-baseline history, drift and rollback-recovery boundaries.
APP1-APP5 provide the runnable operator application above those boundaries.

## Core map

```text
ST music repositories
  -> source-provenanced evidence
  -> deterministic planner
  -> independent verifier
  -> guarded reversible execution
  -> persistent exact task evidence
  -> exact-SHA CI
  -> generic + project-specific typed validators
  -> VERIFIED_SUCCESS
  -> bounded exact diff review
  -> human review acknowledgement bound to review_digest + HEAD
  -> human-gated PR creation
  -> exact PR head/base evidence
  -> bounded PR review/thread/conversation evidence
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

APP1 provides project evidence, warnings, next-safe-boundaries and verified portfolio planning across
Score Restore, MusicXML → Guitar TAB, Score Editor and Real-Time Score Following.

## APP2 — Guarded task execution

APP2 introduced opt-in loopback-only feature-branch execution. The model receives bounded reads and one
host-bound `task.write_file` mutation. It cannot select `main`, create/approve/merge a PR, deploy,
train, canonicalize or execute rollback.

## APP3 — Persistent execution evidence + CI/validators

APP3 adds the append-only SHA-256 task journal, exact final task HEAD, bounded base...HEAD evidence,
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

`FAILED` is terminal for a task identity. No model message such as "done" is treated as success.

## APP4 — Exact review + immutable revisions + PR binding

APP4 binds a bounded exact patch review to the task base/head pair, computes per-file patch digests and
a deterministic `review_digest`, requires explicit human acknowledgement, then allows a separate human
PR-open action. Missing/truncated patch evidence cannot be acknowledged.

Retry/amend does not rewrite history: it creates a new child task with append-only lineage evidence.
APP4 also persists `PR_REVIEW_SNAPSHOT` for exact PR head/base binding.

## APP5 — Project validation + PR collaboration evidence

APP5 turns the generic validator plane into real project-aware validation without confusing CI with
music-domain correctness.

For every new APP5 task, the authoritative evidence adapter for that project is re-run using the exact
task HEAD as its Git ref:

- Score Restore -> `score_restore_current_truth`;
- MusicXML → Guitar TAB -> `tab_capability_contract`;
- Score Editor -> `score_editor_release_boundary`;
- Real-Time Score Following -> `score_following_research_boundary`.

Each adapter must return evidence sources for the exact task HEAD. Contract violations are `FAIL`;
unreadable evidence remains `UNAVAILABLE`, never `PASS`.

### Project invariants

APP5 preserves project-specific safety boundaries rather than inventing one global music validator.
Examples include:

- Score Restore: no automatic production promotion; OMR/musical truth not implied;
- TAB: `REVIEW_REQUIRED` remains capability-driven; canonical/export stays PASS-only;
- Score Editor: planned capability remains distinct from production; release/cutover gates stay closed
  unless separately authorized;
- Score Following: research evidence is not production/pedagogical authority and does not imply
  acoustic mono-mixture authority.

### PR collaboration evidence

After PR creation, an explicit session-token-protected refresh reads bounded review collaboration
information. APP5 separates reviews for the exact task HEAD from stale reviews for older commits and
stores review submissions, inline comment threads and general PR conversation evidence.

GitHub REST does not expose review-thread resolution state in this runtime adapter. APP5 records that
state as `unavailable` rather than inferring it.

The append-only event is:

```text
PR_COLLABORATION_SNAPSHOT
```

It always contains `merge_authorized: false`.

## Persistent evidence events

The APP3 stage machine is unchanged. Additional review/evidence events include:

```text
REVIEW_SNAPSHOT
REVIEW_ACKNOWLEDGED
LINEAGE_PARENT
LINEAGE_CHILD_CREATED
PR_REVIEW_SNAPSHOT
PR_COLLABORATION_SNAPSHOT
```

## Branch and HTTP confinement retained

The model still has no branch field on `task.write_file`, no PR-open tool, no PR approval tool and no
merge tool. Task POSTs require a random per-process `X-ST-Session` token. Write mode is loopback-only.
Credentials are resolved only inside trusted adapters.

## Explicitly unavailable in APP5

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
9. Engineering success/review metadata is not production authority or domain correctness.
10. Exact commit identity is required wherever CI/validator/review evidence widens task state.
11. Earlier task, revision and collaboration evidence is append-only and cannot be silently replaced.
12. Tests define widened application behavior before merge.

## Next application boundary — APP6

APP6 should focus on operational hardening of validator health/freshness, richer review-resolution
adapters where trustworthy APIs are available, and audit/export ergonomics. Merge and production
authority must remain outside the agent application.
