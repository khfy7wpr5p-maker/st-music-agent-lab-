# A12 Music-Domain Evidence Boundary

A12 is the first direct connection from ST Music Agent Lab to ST music-engine repositories.
The connection is deliberately read-only and evidence-first.

## Why evidence-first

An engineering agent must not infer project readiness from filenames, old chat context or a
single successful test. Music projects have additional truth boundaries: model-evaluation gates,
notation uncertainty, teacher review, provisional artifacts and production authorization.

A12 therefore exposes bounded snapshots derived from repository-owned truth/contract files. Each
snapshot includes:

- schema version;
- project identifier;
- authority class;
- explicit state;
- bounded claims;
- warnings;
- next safe boundary when the source declares one;
- repository, ref, source path and Git blob SHA provenance.

If a required source is truncated, malformed, has an unsupported schema, loses a required safety
field or no longer matches the executable contract markers, the adapter fails closed instead of
inventing a replacement conclusion.

## Score Restore adapter

Tool: `music.score_restore.snapshot`

Repository: `khfy7wpr5p-maker/st-score-restore-engine`

Authoritative source:

`docs/live/ST_SCORE_RESTORE_STAGE11_V2_SYMBOL_PRESERVATION_CURRENT_TRUTH.json`

A12 currently supports current-truth schema `1.2.0` and projects only selected status, gate,
safety and preservation fields. Important semantics are preserved:

- the V2a candidate may be frozen and have held-out/Stage 9A preservation passes recorded;
- that does not imply OMR correctness or musical truth;
- an ideal ink-recall target may still be unmet;
- MSE regression may remain explicitly recorded;
- `finalModelSelected`, `stage12EntryAuthorized` and `productionInferenceAuthorized` are reported
  independently and are never inferred from evaluation passes;
- automatic production promotion remains a separate safety boundary.

The adapter does not run training, mutate weights, authorize Stage 12 or promote a model.

## MusicXML -> Guitar TAB adapter

Tool: `music.tab_engine.capability_snapshot`

Repository: `khfy7wpr5p-maker/musicxml-to-guitar-tab-engine`

Primary executable contract:

`src/app/reviewRequiredCapabilityContract.js`

Corroborating workbench test:

`tests/workbenchCapabilityBridge.test.js`

The adapter does not execute repository JavaScript. It verifies the bounded contract markers and
projects the semantics relevant to the agent:

- `REVIEW_REQUIRED` is not a global application lock;
- score rendering depends on readable MusicXML;
- TAB generation depends on an available TAB artifact;
- TAB shown during `REVIEW_REQUIRED` is provisional;
- canonical TAB and export remain PASS-only;
- playback may remain FULL or APPROXIMATE for a readable review-required score;
- BLOCKED playback remains disabled;
- review-required editing is not advertised merely to unlock UI controls.

If these executable markers or the corroborating workbench expectations change, the A12 adapter
fails closed until its evidence projection is deliberately updated.

## Composition

`build_default_music_domain_toolset()` creates read-only GitHub clients for both current ST
repositories. The returned `MusicDomainToolset` can be registered into the existing
`ToolRegistry`.

That means the same tools can flow through either execution route without widening privilege:

```text
Direct provider -> ToolRegistry -> music.* snapshot -> read-only GitHub evidence

OpenHands -> restricted ST MCP bridge -> ToolRegistry -> music.* snapshot
                                              |
                                              +-> read-only GitHub evidence
```

No music-domain write, training, export, merge or production-promotion capability is introduced
in A12.

## Next safe expansion

A13 should build on these evidence contracts rather than bypass them. Suitable next work:

1. add Score Editor and real-time score-following evidence adapters;
2. add cross-project planning that consumes snapshots but cannot mutate source projects directly;
3. add synthetic/local integration fixtures for the two remote adapters;
4. introduce explicit music-domain action contracts only after their read/evidence semantics are
   stable;
5. keep training/promotion and canonical student-facing export behind dedicated human-gated
   policies.
