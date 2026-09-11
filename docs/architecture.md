# ST Music Agent Lab — Architecture Map

Status: A1-A26 guarded core + APP1-APP3 runnable guarded application
Date: 2026-09-12

## Purpose

ST Music Agent Lab is the model-agnostic engineering and music-intelligence control layer for ST
projects. The A1-A26 core owns policy, tools, budgets, approvals, evidence, verification, learning,
training/model lifecycle, canonical-baseline history, drift and rollback-recovery boundaries.
APP1-APP3 provide the real operator application above those boundaries.

## Core map

```text
ST music repositories
  -> source-provenanced evidence
  -> deterministic planner
  -> independent verifier
  -> guarded reversible execution
  -> persistent exact task evidence
  -> exact-SHA CI + typed validators
  -> explicit VERIFIED_SUCCESS decision
  -> human-gated PR review flow
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

## APP3 — Persistent execution evidence + CI/validator + PR review

APP3 keeps the APP2 write boundary and adds a durable evidence plane.

```text
browser instruction
  -> POST /api/tasks/preview
  -> exact repository + protected base SHA
  -> deterministic st-agent/<project>/<task> branch
  -> AutonomyPolicy recomputation
       create branch = AUTO_EXECUTE
       write file   = AUTO_EXECUTE
       open PR      = REQUIRE_HUMAN
  -> append PREVIEWED event to local hash-chained journal
  -> explicit Run click
  -> host creates exact feature branch
  -> ToolLoopRunner with bounded read tools + task.write_file
  -> resolve final feature-branch HEAD
  -> exact base...HEAD compare
  -> bind changed paths + bounded diff statistics
  -> CI_PENDING
  -> explicit browser/host evidence refresh
  -> select workflow runs only for exact task HEAD
  -> run typed validators: PASS / FAIL / UNAVAILABLE
  -> VERIFIED_SUCCESS only when required evidence passes
  -> explicit human Open PR click
  -> recheck PR head/base binding
  -> PR_OPENED
  -> no merge endpoint
```

### Persistent journal

The APP3 task store is append-only JSONL with a SHA-256 hash chain. Each record contains structured
public task metadata or bounded evidence; it never stores provider chain-of-thought, API key values or
raw credentials.

The primary stage machine is:

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

`FAILED` is terminal for an attempt. Invalid stage skipping is rejected. Evidence snapshots are
appended instead of replacing earlier evidence. After restart, task status and exact commit evidence
can be reconstructed from the journal. A still-executable task must be re-previewed with the same
instruction so the deterministic instruction fingerprint/task identity is rebound to the new process.

### Exact execution evidence

A model message such as "done" is never task success. After the agent loop returns, APP3 resolves the
feature branch again and requires a new full commit SHA different from the preview base. It then asks
GitHub for a bounded compare of the exact base and exact head and records changed file paths and
statistics. Missing/truncated/unbounded evidence fails closed.

### CI tracking

Core logic has no uncontrolled polling loop. CI is refreshed only because the browser or host asks for
it. Workflow evidence is filtered to the exact task HEAD SHA. Runs for another SHA cannot satisfy the
task. Pending runs remain pending; a completed non-success conclusion fails the task.

Project execution profiles are configuration data. With no explicit workflow names configured, APP3
reviews all exact-SHA workflow runs returned for that task. A profile may name required workflows only
when those checks really exist.

### Validator contract

A validator result contains:

- validator name;
- `PASS`, `FAIL` or `UNAVAILABLE`;
- evidence reference;
- exact commit SHA;
- bounded public message.

`UNAVAILABLE` cannot silently become `PASS`. APP3 includes generic exact-commit-binding and
bounded-diff-evidence validators. Project-specific validators remain adapter-driven and must not be
invented from generic CI success.

### Public outcome

The operator-facing outcome is one of:

- `WORKING`;
- `REVIEW_REQUIRED`;
- `VERIFIED_SUCCESS`;
- `FAILED`.

`VERIFIED_SUCCESS` means only that the bound engineering task has the required APP3 execution, CI and
validator evidence. It is not merge, release, deployment, musical correctness, training, activation,
canonicalization or production authorization.

### PR boundary

PR creation remains an explicit human/host action. It is rejected before `VERIFIED_SUCCESS`. Before
opening, APP3 checks that the feature branch still points at the verified HEAD. After opening, PR
metadata is read back and its head ref/head SHA/base ref are checked before the PR evidence is
persisted. No automatic merge endpoint is introduced.

## Branch confinement retained

The model does not receive `github.create_branch` or `github.open_pull_request`. Its only mutation
tool is `task.write_file`, whose JSON schema has no branch field. The host injects the exact branch
created from the preview. Attempts to supply `branch=main` or any other extra field fail tool
validation.

Task repository discovery remains bounded: recursive Git tree truncation fails closed, credential
paths are filtered, and excessive file counts are rejected rather than silently hidden.

## HTTP boundary retained

Task POSTs require a random per-process `X-ST-Session` token and bounded JSON bodies. Feature-branch
execution requires `--enable-writes`; write mode refuses non-loopback HTTP binding. Provider/GitHub
credentials are configured by environment-variable name and resolved only inside trusted adapters.

## Explicitly unavailable in APP3

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
9. APP3 engineering success is not production authority or domain correctness.
10. Exact commit identity is required anywhere CI/validator evidence can widen task state.
11. Earlier task evidence is append-only and cannot be silently replaced.
12. Tests define the widened application behavior before merge.

## Next application boundary — APP4

APP4 should improve review/diff UX, explicit retry/amend attempts and exact PR review evidence. It
should reuse APP3 persistent task identities and must not widen merge or production authority.
