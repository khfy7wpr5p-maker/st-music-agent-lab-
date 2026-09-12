# APP8 Operational Pilot — exact-SHA read-only first pass

Status: controlled operational-readiness plan after APP8E completion.

This document records the first evidence-driven step after APP8A-APP8E. It does not define a new
application authority layer. The purpose is to prove that the completed APP8 architecture can observe,
coordinate and replay real ST project state before any broader execution scope is considered.

## Snapshot captured on 2026-09-12

The following `main` SHAs were read directly from the live GitHub repositories when this pilot was
prepared. They are a point-in-time pilot snapshot, not a claim that these repositories will remain on
these SHAs later.

| Project | Repository | Exact pilot SHA |
| --- | --- | --- |
| ST Music Agent Lab | `khfy7wpr5p-maker/st-music-agent-lab-` | `6465c7fa1adf113cb9e51e3f910d57d64b3d8090` |
| Score Restore | `khfy7wpr5p-maker/st-score-restore-engine` | `20f8df8fbbb4640083032672acd2f7d1e151aca3` |
| MusicXML → Guitar TAB | `khfy7wpr5p-maker/musicxml-to-guitar-tab-engine` | `963274a5425488b07df153460409e491f56c423d` |
| Score Editor | `khfy7wpr5p-maker/st-score-editor-core` | `6b0e2cac572dfcfa570bfab2bb8eb47a9d7f68fc` |
| Real-Time Score Following | `khfy7wpr5p-maker/st-real-time-score-following-lab` | `a833bee18afffa29686325f5211adc575c7acfa7` |

The pilot must fail closed if any work item expects a different SHA than the exact repository state
being verified.

## Pilot P0 — read-only identity and evidence proof

P0 deliberately performs no repository mutation.

For each of the four ST project repositories:

1. bind a work item to the exact observed `main` SHA;
2. collect only bounded read-only evidence;
3. run the existing project-specific evidence contract where available;
4. produce a host-verified read-only receipt whose `base_sha == head_sha == expected_base_sha`;
5. feed receipts into APP8D rather than treating model text as completion evidence;
6. persist the supervision/coordination graph through APP8E;
7. restart/reload the graph store and require deterministic replay/fingerprint stability.

Project validators remain:

- Score Restore: `score_restore_current_truth`;
- MusicXML → Guitar TAB: `tab_capability_contract`;
- Score Editor: `score_editor_release_boundary`;
- Real-Time Score Following: `score_following_research_boundary`.

P0 does not claim that a validator PASS means musical correctness, production readiness or user-facing
quality. It only proves that the expected project contract was read and evaluated at the exact bound
commit.

## Pilot P0 pass criteria

P0 passes only if all of the following are true:

- every repository identity is a full exact SHA;
- every APP8D read-only receipt remains on the same exact SHA;
- no receipt widens repository, PR, merge or production authority;
- APP8D dependency replay is deterministic;
- APP8E restart reconstruction yields the same plan/replay fingerprints;
- graph journal verification succeeds;
- remote graph access remains authenticated GET-only;
- no APP8 graph mutation HTTP endpoint exists;
- no model-selected protected-branch write is introduced;
- no PR approval, merge, deployment, training, activation/canonicalization or rollback authority is
  added.

A missing/unreadable project evidence surface is `UNAVAILABLE`/review-required evidence, not permission
to infer success.

## Pilot P1 — one reversible feature-branch cycle

P1 is allowed only after P0 passes. It should select exactly one low-risk engineering task in one ST
repository and use the existing APP8C + APP2-APP7 boundaries:

```text
exact main SHA
  -> host-created deterministic feature branch
  -> bounded implementation agent
  -> exact final HEAD
  -> exact-SHA CI
  -> project validator
  -> independent APP8B gate
  -> APP8C VERIFIED record
  -> APP8D completion receipt
  -> APP8E persistent replay
```

P1 must not use direct `main` writes, model-selected branches, merge/auto-merge, deployment, training,
production activation, canonicalization or rollback.

A practical first P1 candidate should be documentation, diagnostics, validation coverage or another
reversible change that does not alter production behavior. The pilot should measure operator friction
before any new architecture stage is proposed.

## Measurements to collect

The first real pilot should record:

- number of supervision nodes and APP8D work items;
- model turns and tool calls consumed;
- exact-SHA evidence refresh count;
- validator outcomes and unavailable evidence;
- critic/reliability disposition;
- number of human gates encountered;
- graph journal/replay verification result;
- any stale-state, unclear-status or operator-UI friction;
- any task that could not be represented without widening authority.

These measurements determine whether the next change should be usability, diagnostics, validator
coverage or orchestration ergonomics. A new execution authority must not be justified merely by the
existence of the next version number.

## Stop conditions

Stop the pilot and preserve the evidence if any of the following occurs:

- repository HEAD differs from the expected exact SHA during a supposedly exact-bound read;
- a receipt/artifact/gate fingerprint cannot be reconciled;
- deterministic replay changes across restart;
- hash-chain verification fails;
- a dependency is advanced without its declared upstream evidence;
- a remote request can mutate graph/task state;
- completing the task would require merge, deployment, training, activation/canonicalization or
  rollback authority that is not separately approved.

## Current conclusion

APP8A-APP8E is structurally complete. The next engineering question is no longer "what APP comes next?"
but "what concrete operator friction appears when exact-SHA APP8 supervision is used against real ST
project state?" This pilot is the evidence boundary for answering that question.
