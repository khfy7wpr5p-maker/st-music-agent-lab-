# A12-A13 Music-Domain Evidence Boundary

A12-A13 connect ST Music Agent Lab to four ST music-engine repositories. The connection remains
read-only and evidence-first.

## Why evidence-first

An engineering agent must not infer project readiness from filenames, old chat context or a
single successful test. Music projects have additional truth boundaries: model-evaluation gates,
notation uncertainty, teacher review, release matrices, provisional artifacts, research scope and
production authorization.

The agent therefore exposes bounded snapshots derived from repository-owned truth, contract,
roadmap or permanent-evidence files. Each snapshot includes:

- versioned evidence schema;
- project identifier;
- authority class;
- explicit state;
- bounded claims and warnings;
- next safe boundary when known;
- repository, ref, source path and Git blob SHA provenance.

If required evidence is truncated, malformed, missing a safety marker or no longer matches the
expected contract, the adapter fails closed instead of inventing a replacement conclusion.

## A12 — Score Restore

Tool: `music.score_restore.snapshot`

Repository: `khfy7wpr5p-maker/st-score-restore-engine`

Source:
`docs/live/ST_SCORE_RESTORE_STAGE11_V2_SYMBOL_PRESERVATION_CURRENT_TRUTH.json`

Important semantics:

- V2a may be a frozen candidate with held-out/Stage 9A preservation passes;
- this does not imply OMR correctness or musical truth;
- an ideal ink-recall target may remain unmet and MSE regression may remain recorded;
- final model selection, Stage 12 authorization and production inference authorization are
  reported independently;
- automatic production promotion remains forbidden unless repository truth explicitly changes.

The adapter does not train, mutate weights, authorize Stage 12 or promote a model.

## A12 — MusicXML -> Guitar TAB

Tool: `music.tab_engine.capability_snapshot`

Repository: `khfy7wpr5p-maker/musicxml-to-guitar-tab-engine`

Sources:

- `src/app/reviewRequiredCapabilityContract.js`
- `tests/workbenchCapabilityBridge.test.js`

Important semantics:

- `REVIEW_REQUIRED` is not a global lock;
- readable MusicXML may keep score rendering available;
- an available TAB artifact may remain usable during review;
- review TAB is provisional;
- canonical TAB and export remain PASS-only;
- review playback may be FULL or APPROXIMATE;
- BLOCKED playback stays disabled;
- editing authority remains narrower than score/TAB visibility.

The adapter does not execute repository JavaScript. Contract-marker drift fails closed.

## A13 — Score Editor

Tool: `music.score_editor.snapshot`

Repository: `khfy7wpr5p-maker/st-score-editor-core`

Source: `ROADMAP.md`

The roadmap explicitly defines repository reality as the current source of truth. A13 preserves
these boundaries:

- APP-11F is complete/merged in repository reality;
- the current phase is strong-editor semantic selection, relation authoring and timing-space
  expansion;
- manual real-device/browser validation remains required;
- the standalone release gate remains closed;
- SesliTab V4 cutover remains unauthorized;
- feature development must not silently open release/cutover gates;
- APP-11G Tuplet Retiming Admission Foundation is the next declared development action.

Planned capability is never reported as production capability.

## A13 — Real-Time Score Following

Tool: `music.score_following.snapshot`

Repository: `khfy7wpr5p-maker/st-real-time-score-following-lab`

Sources:

- `README.md`
- `benchmarks/reports/SF11_MIXED_ENSEMBLE.md`

A13 reports the current research boundary without overstating it:

- SF-11 Mixed Ensemble is complete for repository-owned deterministic channel-separated evidence;
- SF-12 Orchestra Global Score Following is the next research stage;
- SF-11 permanent evidence records a validated implementation head and passing CI run;
- the evidence is synthetic/channel-separated and is not acoustic mono-mixture authority;
- shared confidence remains unavailable rather than synthesized;
- SF-04 real violin evidence remains a separate rights-gated path;
- experimental evidence is not production or pedagogical authority.

Asynchrony, divergence, quorum loss and abstention remain evidence states rather than student or
performer quality grades.

## Composition

`build_default_music_domain_toolset()` now binds four read-only repositories and returns a
`FullMusicDomainToolset`. Registering it into the normal `ToolRegistry` exposes exactly:

- `music.score_restore.snapshot`
- `music.tab_engine.capability_snapshot`
- `music.score_editor.snapshot`
- `music.score_following.snapshot`

The same registry works through the direct provider loop or the A11 restricted OpenHands bridge:

```text
Direct provider -> ToolRegistry -> music.* snapshot -> read-only repository evidence

OpenHands -> restricted ST MCP bridge -> ToolRegistry -> music.* snapshot
                                              |
                                              +-> read-only repository evidence
```

No music-domain write, training, release activation, product cutover, canonical export or
production-promotion capability is introduced by A12-A13.

## Next safe expansion

A14 should consume these snapshots without bypassing them. Suitable work:

1. add a cross-project planner that produces recommendations/evidence dependencies but does not
   mutate source projects;
2. add synthetic/local GitHub integration fixtures for all four evidence adapters;
3. add resumable orchestration state tied to journal/budget/approval evidence;
4. define music-domain mutation contracts only after read/evidence semantics remain stable;
5. keep training/promotion, release/cutover and canonical student-facing export behind dedicated
   human-gated policies.
