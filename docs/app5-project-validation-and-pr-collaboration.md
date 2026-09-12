# APP5 — Project Validation and PR Collaboration Evidence

APP5 extends APP4 with real project-aware validation and bounded pull-request collaboration evidence.
It does not grant merge, deployment, training, activation, canonicalization or rollback authority.

## Exact-HEAD project validation

Generic CI success is not treated as music-domain correctness. After APP3 binds the exact feature
branch HEAD, APP5 runs the existing authoritative evidence adapter for that project using the exact
commit SHA as the evidence ref.

The current validators are:

- `score_restore_current_truth` — reads the Score Restore Stage 11 current-truth artifact and preserves
  explicit safety claims: automatic production promotion remains forbidden and OMR/musical truth is
  not implied;
- `tab_capability_contract` — reads the MusicXML → Guitar TAB executable capability contract and keeps
  `REVIEW_REQUIRED` capability-driven, canonical/export PASS-only and approximate playback allowed;
- `score_editor_release_boundary` — reads the Score Editor repository source-of-truth and keeps planned
  capability distinct from production capability while release/cutover gates remain separate;
- `score_following_research_boundary` — reads permanent real-time score-following research evidence and
  keeps production/pedagogical authority and acoustic mono-mixture authority closed.

Every project validator result uses the existing `PASS / FAIL / UNAVAILABLE` contract and is bound to
the exact task commit SHA. A source returned for another ref fails validation. An unreadable evidence
surface is `UNAVAILABLE`, not `PASS`.

## PR collaboration snapshot

Once a PR exists, an explicit session-token-protected refresh reads bounded GitHub collaboration
evidence:

- review submissions;
- reviewer state and review commit id;
- inline review comments grouped into thread-like roots/replies;
- general PR conversation comments.

APP5 distinguishes review submissions for the exact task HEAD from stale reviews submitted for another
commit. It records exact-head approvals and exact-head change requests separately.

The REST adapter does not claim thread-resolution state. When resolution state is unavailable, APP5
records `unavailable`; it does not infer that a thread is resolved.

## Bounds

The adapter reads at most:

- 50 review submissions;
- 100 inline review comments;
- 50 general conversation comments.

Comment payloads are bounded before persistence. Collaboration evidence is intended for review context
and audit, not unlimited archival.

## Journal event

APP5 adds one append-only evidence event without changing the APP3 stage machine:

```text
PR_COLLABORATION_SNAPSHOT
```

The snapshot contains the task HEAD, PR number, exact/stale review summary, bounded thread evidence and
an explicit `merge_authorized: false` field.

## Authority boundary

APP5 exposes no model-callable or HTTP action for:

- approving a PR;
- resolving/dismissing review threads;
- merge or auto-merge;
- direct protected-branch mutation;
- deployment/release;
- training/activation/canonicalization;
- rollback execution.

Human review metadata can inform the operator, but it never becomes agent self-authority.
