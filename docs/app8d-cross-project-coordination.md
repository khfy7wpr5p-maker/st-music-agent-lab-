# APP8D — Cross-project coordination

Status: receipt-driven coordination layer. It coordinates already-verified project work; it does not execute repository mutations itself.

## Purpose

APP8D lets one ST music project unlock a bounded downstream project only when the upstream result is represented by a verified, exact-bound completion receipt. The coordinator is deterministic and replayable.

The initial project set is fixed to:

- `st-score-restore-engine`
- `musicxml-to-guitar-tab-engine`
- `st-score-editor-core`
- `st-real-time-score-following-lab`

Each project is bound to its canonical repository through `PROJECT_REPOSITORIES`; a plan cannot silently substitute a different repository.

## Plan contract

A `CrossProjectPlan` contains at least two `ProjectWorkItem` values. APP8D v1 permits at most one work item per music project.

Every item declares:

- project and canonical repository
- exact expected base SHA
- bounded instruction
- dependency item ids
- required upstream evidence keys
- produced evidence keys
- mutation class: read-only or reversible feature-branch only

The plan rejects unknown dependencies, self-dependencies, undeclared upstream evidence, cycles, unsupported mutation classes, invalid repository bindings, and malformed hashes.

## Verified completion receipts

Downstream work is unlocked only by `ProjectCompletionReceipt` evidence.

### Reversible feature-branch item

A writable project item must use `ProjectCompletionReceipt.from_app8c(...)` and therefore requires:

1. an APP8C implementation record with `VERIFIED` disposition;
2. the expected project repository and exact base SHA;
3. an APP8B gate with `ACCEPT` disposition;
4. gate binding to the same repository, implementation HEAD, and artifact SHA-256;
5. all declared produced evidence keys.

The coordinator does not call APP8C itself. A host executes APP8C separately and supplies the verified receipt.

### Read-only item

A read-only item can use `from_host_verified_read_only(...)`. The receipt must remain on the exact expected SHA and cannot advance repository state.

## State machine

Per item:

`PENDING -> READY -> RUNNING -> ACCEPTED`

Non-pass terminal states:

- `REVIEW_REQUIRED`
- `ABSTAINED`
- `FAILED`

Dependent work becomes `BLOCKED` when an upstream dependency reaches a non-pass terminal state or cannot supply declared required evidence.

Only one coordination item is scheduled at a time in APP8D v1. Selection is deterministic by project key and item id.

## Deterministic replay

Every scheduling/result event is fingerprinted from canonical JSON. `replay_coordination(...)` reconstructs item states and the final coordination disposition from the plan plus event stream. The replay performs no external action.

## Authority boundary

APP8D does not:

- invoke a model;
- dispatch project tools;
- create a branch;
- write a repository file;
- open or approve a PR;
- merge or auto-merge;
- resolve review threads;
- deploy or release;
- train a model;
- activate/canonicalize a model;
- execute rollback;
- mutate secrets or privileges.

All plan, decision, receipt, and replay projections keep these flags false:

- `execution_authorized`
- `repository_mutation_authorized`
- `pr_open_authorized`
- `merge_authorized`
- `production_actions_authorized`

APP8D therefore coordinates evidence, not authority.

## Relationship to APP8C

APP8C remains the only APP8 layer that can reuse the existing APP3–APP7 reversible feature-branch execution chain. APP8D can accept an APP8C verified-cycle receipt, but it cannot initiate that execution or widen its permissions.

A typical bounded chain is:

`Score Restore verified receipt -> Guitar TAB work becomes READY -> APP8C runs externally -> accepted TAB receipt -> optional downstream Editor/Score Following work becomes READY`

## Next boundary

APP8E may expose persistent operator graph state, resume controls, and read-only visualization for APP8A–APP8D evidence. It must not introduce merge, deployment, or production authority.
