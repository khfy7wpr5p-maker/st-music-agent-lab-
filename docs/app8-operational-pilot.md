# APP8 Operational Pilot — exact-SHA read-only first pass

Status: P0 read-only evidence inspection completed; upstream evidence-contract drift was found and
repaired fail-closed. A Score Editor source-of-truth cleanup was also completed as a host-managed,
docs-only precursor. The first true in-application APP8 reversible execution cycle is still pending.

This document records the first evidence-driven work after APP8A-APP8E. It does not define a new
application authority layer. The purpose is to prove that the completed APP8 architecture can observe,
coordinate and replay real ST project state before any broader execution scope is considered.

## Exact repository snapshot

The following identities were read from live GitHub repository state during this pilot. They are
point-in-time identities, not permanent aliases.

| Project | Repository | Exact observed SHA |
| --- | --- | --- |
| ST Music Agent Lab | `khfy7wpr5p-maker/st-music-agent-lab-` | `91fd187fa6c6c26f675efe535b951e1d3858e524` |
| Score Restore | `khfy7wpr5p-maker/st-score-restore-engine` | `20f8df8fbbb4640083032672acd2f7d1e151aca3` |
| MusicXML → Guitar TAB | `khfy7wpr5p-maker/musicxml-to-guitar-tab-engine` | `963274a5425488b07df153460409e491f56c423d` |
| Score Editor | `khfy7wpr5p-maker/st-score-editor-core` | `712f7ef46c93b443e84eda66399c599fa1c1d562` |
| Real-Time Score Following | `khfy7wpr5p-maker/st-real-time-score-following-lab` | `a833bee18afffa29686325f5211adc575c7acfa7` |

The pilot fails closed if a supposedly exact-bound read or receipt resolves to a different SHA.

## P0 observed evidence surfaces

### Score Restore

Exact source:
`docs/live/ST_SCORE_RESTORE_STAGE11_V2_SYMBOL_PRESERVATION_CURRENT_TRUTH.json`

The current contract remains compatible with the adapter boundary:

- artifact type `stage11_v2_symbol_preservation_current_truth`;
- schema `1.2.0`;
- frozen candidate recorded;
- final model selection false;
- Stage 12 authorization false;
- production inference authorization false;
- OMR correctness and musical truth are explicitly not implied;
- automatic production promotion remains forbidden.

Result: **P0 evidence contract compatible.** This is not OMR/musical correctness or production
readiness evidence.

### MusicXML → Guitar TAB

Exact sources:

- `src/app/reviewRequiredCapabilityContract.js`
- `tests/workbenchCapabilityBridge.test.js`

The contract still preserves:

- `REVIEW_REQUIRED` is capability-driven rather than a global lock;
- readable MusicXML may render;
- available review TAB remains provisional;
- approximate playback may remain available;
- canonical TAB/export remain PASS-only;
- BLOCKED playback is disabled;
- edit authority is narrower than score/TAB visibility.

Result: **P0 evidence contract compatible.**

### Real-Time Score Following

P0 found a real fail-closed maintenance event. The upstream repository had advanced from the adapter's
old SF-11 contract to:

- README: SF-12 complete, SF-13 next;
- permanent evidence: `benchmarks/reports/SF12_ORCHESTRA_GLOBAL.md`.

The old adapter correctly stopped matching rather than inventing a current state. ST Music Agent Lab
PR #42 then refreshed the adapter/test/documentation contract to SF-12 while preserving these limits:

- global orchestra evidence is measure/beat research only;
- per-instrument/section transcription authority remains false;
- real orchestral-audio authority remains false;
- calibrated global confidence remains unavailable;
- production and pedagogical authority remain false;
- SF-13 Orchestra Section Research is the next safe research boundary.

Result: **evidence-contract drift detected and repaired without widening authority.**

### Score Editor

P0 initially found a different freshness problem: repository implementation had already reached
APP-11I while the declared `ROADMAP.md` source of truth still described APP-11F complete / APP-11G
next. The evidence adapter deliberately continued to follow the roadmap rather than inferring product
state from unrelated implementation files.

An existing docs-only PR #141 was then verified at exact head
`06606cd4fa9e4354061c2288d0b8582b669a299d` and merged. The new Score Editor main is
`712f7ef46c93b443e84eda66399c599fa1c1d562`. The synchronized roadmap now records:

- APP-11G analysis-only Triplet Retiming Admission complete;
- APP-11H atomic retiming + explicit-rest balancing complete;
- APP-11I session/browser productization complete;
- one successful retiming user action = one unified history revision with exact Undo;
- APP-11J Triplet Removal / Unretiming Admission Foundation next;
- physical device validation still required;
- standalone release gate false;
- SesliTab cutover false and outside the current core-development track.

Because the roadmap wording/state changed, the strict ST Music Agent adapter again had to be refreshed.
That refresh is intentionally bounded to the repository-owned roadmap and keeps release/cutover false.

Result: **source-of-truth freshness repaired upstream; adapter refresh required and kept fail-closed.**

## P0 validator names

The project-specific exact-head validators remain:

- Score Restore: `score_restore_current_truth`;
- MusicXML → Guitar TAB: `tab_capability_contract`;
- Score Editor: `score_editor_release_boundary`;
- Real-Time Score Following: `score_following_research_boundary`.

A validator PASS means only that its declared exact-head contract passed. It does not mean musical
correctness, production readiness or user-facing quality.

## P0 pass criteria

P0 is considered structurally successful only while all of these remain true:

- every repository identity is a full exact SHA;
- read-only receipts remain on their exact expected SHA;
- no receipt widens repository, PR, merge or production authority;
- APP8D dependency replay remains deterministic;
- APP8E restart reconstruction preserves fingerprints;
- graph-journal verification succeeds;
- remote graph access remains authenticated GET-only;
- no APP8 graph-mutation HTTP endpoint exists;
- no model-selected protected-branch write is introduced;
- no PR approval, merge, deployment, training, activation/canonicalization or rollback authority is
  added.

Missing/unreadable project evidence stays `UNAVAILABLE`/review-required evidence. It is never
permission to infer success.

## Host-managed cleanup is not an APP8 runtime proof

The Score Editor PR #141 merge and the evidence-adapter maintenance in ST Music Agent Lab are useful
operational cleanup, but they were executed by the authorized host/GitHub workflow. They must **not**
be described as proof that APP8C/APP8D/APP8E executed a complete autonomous runtime cycle.

This distinction is important: GitHub connector actions performed outside the ST Music Agent runtime do
not become model capabilities inside the application.

## P1 — first true reversible in-application cycle

P1 remains the next runtime proof. It must select exactly one low-risk engineering task and exercise the
existing guarded application boundaries end-to-end:

```text
exact main SHA
  -> host-bound feature branch
  -> bounded APP8C implementation cycle
  -> exact final HEAD
  -> exact-SHA CI
  -> project validator
  -> independent APP8B gate
  -> verified completion record
  -> APP8D receipt/coordination evidence
  -> APP8E persistent graph
  -> process restart / deterministic replay verification
```

P1 must not use direct `main` writes, model-selected branches, merge/auto-merge, deployment, training,
production activation, canonicalization or rollback.

A documentation, diagnostics or validation-coverage task remains the preferred first mutation because
it is reversible and does not alter production behavior.

## Measurements from the pilot so far

- four target repositories were bound to exact SHAs;
- Score Restore current-truth contract remained compatible;
- TAB capability contract remained compatible;
- Score Following exposed SF-11 -> SF-12 adapter drift and was repaired fail-closed;
- Score Editor exposed implementation -> roadmap truth lag, then roadmap -> adapter drift after the
  authoritative docs were synchronized;
- no target-project production behavior needed to change;
- no deployment/training/activation/rollback authority was required;
- the repeated friction class is now clear: **cross-project evidence freshness**.

The important result is not that validation should be weakened. It is that the operator should be able
to detect, explain and refresh evidence-contract drift quickly while preserving exact-SHA provenance.

## Stop conditions

Stop and preserve evidence if any of the following occurs:

- repository HEAD differs from the expected exact SHA during an exact-bound read;
- a receipt/artifact/gate fingerprint cannot be reconciled;
- deterministic replay changes across restart;
- hash-chain verification fails;
- a dependency advances without declared upstream evidence;
- a remote request can mutate graph/task state;
- completing the task would require merge, deployment, training, activation/canonicalization or
  rollback authority that is not separately approved.

## Current conclusion

APP8A-APP8E remains structurally complete. P0 produced a concrete operational finding: **evidence
adapter freshness is a real maintenance boundary across independently moving ST repositories**. The
Score Following and Score Editor cases both validated the fail-closed design. After the current Score
Editor adapter refresh is exact-head green and merged, the next meaningful proof is the first genuine
P1 in-application reversible execution/replay cycle—not another architecture version number.
