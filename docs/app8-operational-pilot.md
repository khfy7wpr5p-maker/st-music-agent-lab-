# APP8 Operational Pilot — exact-SHA read-only first pass

Status: P0 read-only evidence inspection executed; one upstream evidence-contract drift found and
repaired fail-closed in ST Music Agent Lab.

This document records the first evidence-driven step after APP8A-APP8E. It does not define a new
application authority layer. The purpose is to prove that the completed APP8 architecture can observe,
coordinate and replay real ST project state before any broader execution scope is considered.

## Snapshot captured on 2026-09-12

The following `main` SHAs were read directly from the live GitHub repositories during the pilot. They
are point-in-time identities, not a claim that these repositories will remain on these SHAs later.

| Project | Repository | Exact pilot SHA |
| --- | --- | --- |
| ST Music Agent Lab | `khfy7wpr5p-maker/st-music-agent-lab-` | `ef813684e83347a595fb3b16dc98f1a0da9413f9` |
| Score Restore | `khfy7wpr5p-maker/st-score-restore-engine` | `20f8df8fbbb4640083032672acd2f7d1e151aca3` |
| MusicXML → Guitar TAB | `khfy7wpr5p-maker/musicxml-to-guitar-tab-engine` | `963274a5425488b07df153460409e491f56c423d` |
| Score Editor | `khfy7wpr5p-maker/st-score-editor-core` | `6b0e2cac572dfcfa570bfab2bb8eb47a9d7f68fc` |
| Real-Time Score Following | `khfy7wpr5p-maker/st-real-time-score-following-lab` | `a833bee18afffa29686325f5211adc575c7acfa7` |

The pilot fails closed if a work item expects a different SHA than the exact repository state being
verified.

## P0 observed evidence surfaces

### Score Restore

Exact source read at the pilot SHA:

`docs/live/ST_SCORE_RESTORE_STAGE11_V2_SYMBOL_PRESERVATION_CURRENT_TRUTH.json`

Observed contract still matches the adapter boundary:

- artifact type `stage11_v2_symbol_preservation_current_truth`;
- schema `1.2.0`;
- `candidateCheckpointFrozen: true`;
- `finalModelSelected: false`;
- `stage12EntryAuthorized: false`;
- `productionInferenceAuthorized: false`;
- `omrCorrectnessNotImplied: true`;
- `musicalTruthNotImplied: true`;
- `automaticProductionPromotionForbidden: true`.

Result: **P0 evidence contract compatible**. This is not a claim of OMR/musical correctness or
production readiness.

### MusicXML → Guitar TAB

Exact sources read at the pilot SHA:

- `src/app/reviewRequiredCapabilityContract.js`
- `tests/workbenchCapabilityBridge.test.js`

Observed contract still preserves:

- `REVIEW_REQUIRED` score renderability when MusicXML exists;
- provisional TAB availability when a TAB artifact exists;
- approximate review playback when uncertainty affects playback;
- canonical TAB/export PASS-only behavior;
- BLOCKED playback disabled;
- teacher editing authority narrower than render/TAB visibility.

Result: **P0 evidence contract compatible**.

### Score Editor

Exact `ROADMAP.md` remains compatible with the release-boundary adapter:

- repository reality is the declared source of truth;
- manual device validation remains required;
- standalone release gate remains false;
- SesliTab V4 cutover remains unauthorized;
- feature development must not open release/cutover gates.

The same exact repository SHA also contains APP-11I implementation/regression files while the roadmap
still declares APP-11G as its next development action. The adapter deliberately does not infer a newer
product/release state from those unrelated implementation files.

Result: **release-boundary contract compatible, source-of-truth freshness warning recorded**. The
upstream Score Editor roadmap should eventually be refreshed separately, but this does not justify
silently widening the adapter claim.

### Real-Time Score Following

P0 found a real fail-closed maintenance event.

The repository had advanced from the adapter's old SF-11 evidence contract to:

- README: SF-12 complete, SF-13 next;
- permanent evidence: `benchmarks/reports/SF12_ORCHESTRA_GLOBAL.md`.

The existing adapter still required the old SF-11 README wording and
`benchmarks/reports/SF11_MIXED_ENSEMBLE.md`. Therefore current exact-head validation would become
unavailable/fail rather than inventing a current state. That is the intended failure mode.

The P0 repair updates the adapter to the SF-12 evidence surface and preserves these boundaries:

- global orchestra evidence is measure/beat research only;
- per-instrument/section transcription authority remains false;
- real orchestral-audio authority remains false;
- calibrated global confidence remains unavailable;
- production and pedagogical authority remain false;
- SF-13 Orchestra Section Research is the next safe research boundary.

Result: **evidence-contract drift detected and repaired without widening authority**.

## Pilot P0 — read-only identity and evidence proof

P0 deliberately performs no target-project repository mutation.

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

## Measurements collected in P0

- four target repositories resolved to exact live SHAs;
- Score Restore current-truth contract remained compatible;
- TAB capability contract remained compatible;
- Score Editor release-boundary contract remained compatible, with roadmap freshness lag recorded;
- Real-Time Score Following evidence contract drifted from SF-11 to SF-12 and failed closed;
- one adapter refresh was required; no target-project write was needed;
- no merge/deploy/training/activation/rollback authority was required to repair the evidence adapter.

This is the first concrete operator-friction result: **upstream evidence contracts evolve faster than a
static cross-project adapter catalog unless freshness is actively checked.** Future usability work
should prioritize detecting and explaining this drift rather than bypassing it.

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

APP8A-APP8E remains structurally complete. P0 demonstrated a real operational gap without requiring a
new authority layer: **evidence adapter freshness**. The correct response was a bounded adapter/test/doc
refresh, not weaker validation. After this repair is green on exact-head CI, the next safe action is P1:
one low-risk reversible feature-branch cycle through the completed APP8 chain.
