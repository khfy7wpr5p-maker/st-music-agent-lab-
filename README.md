# ST Music Agent Lab

Model-agnostic orchestration core for autonomous software-engineering and music-intelligence
agents across ST projects.

## Current stage

A1-A22 guarded agent + verified evidence/learning/training/model-runtime foundation:

- **A1-A11:** guarded execution, policy, budgets, approvals, sandboxing, GitHub boundaries and
  restricted OpenHands integration.
- **A12-A13:** read-only source-provenanced evidence from Score Restore, MusicXML/TAB, Score Editor
  and Real-Time Score Following.
- **A14:** deterministic cross-project planner plus independent recomputation verifier.
- **A15:** trusted-host-write verified experience history with advisory learning only.
- **A16:** paired baseline-vs-candidate evaluation; regressions and critical failures reject.
- **A17:** exact execution outcome bound to repository/branch/commit/CI/validator evidence.
- **A18:** explicit curated dataset export with training/promotion authority fixed false.
- **A19:** reproducible training-run contract binding dataset, base model, trainer config, seed and
  code commit to any resulting checkpoint.
- **A20:** immutable model-candidate lineage and independent promotion-review recomputation.
- **A21:** hash-chained resumable lifecycle state plus exact activation-request/rollback binding.
- **A22:** host activation receipts plus deterministic serving/health/shadow/rollback-readiness
  review before any candidate may reach canonical-baseline review.

## Model strategy

The architecture is model-agnostic. Provider/model profiles are replaceable capability profiles,
not authority boundaries. Models never decide their own privileges.

## Music-domain evidence tools

`build_default_music_domain_toolset()` exposes read-only evidence tools:

- `music.score_restore.snapshot`
- `music.tab_engine.capability_snapshot`
- `music.score_editor.snapshot`
- `music.score_following.snapshot`

Project-specific authority is preserved: evaluation is not production authority, REVIEW_REQUIRED
is not canonical TAB export, editor feature completion is not release/cutover, and score-following
research is not production/pedagogical authority.

## Verified lifecycle

```text
music evidence
    |
planner -> verifier
    |
exact execution + CI + validators
    |
verified experience / curated dataset
    |
reproducible training contract
    |
immutable model candidate
    |
paired benchmark + promotion recomputation
    |
activation request (still unauthorized)
    |
separate human/host activation
    |
activation receipt
    |
serving identity + health + shadow quality + rollback readiness
    |
rejected / eligible_for_canonical_review
```

Even after A22 passes, canonicalization is not automatic. The runtime report keeps
`human_review_required=true`, `canonicalization_authorized=false` and `auto_canonicalize=false`.

## Safety boundary

- read-only inspection can run autonomously;
- reversible feature-branch writes can run autonomously;
- protected/destructive/external actions require exact host approval;
- executable repository code runs only through guarded execution paths;
- model-facing outputs are bounded/redacted;
- persistent execution/orchestration evidence is hash chained;
- hidden reasoning is excluded from learning/training/orchestration data;
- dataset export never authorizes training or promotion;
- training specs never auto-start;
- model candidates never activate themselves;
- activation requests never deploy;
- activation receipts only record externally executed host actions;
- shadow-health success grants only canonical-review eligibility;
- deployment credentials, serving switches, rollback execution and canonicalization remain outside
  model-callable tools.

## Development

```bash
python -m pip install -e '.[dev]'
ruff check src tests
pytest
```

See [`docs/architecture.md`](docs/architecture.md) for the architecture map,
[`docs/music-domain-evidence.md`](docs/music-domain-evidence.md) for music evidence,
[`docs/planning-and-learning.md`](docs/planning-and-learning.md) for A14-A15,
[`docs/learning-evaluation.md`](docs/learning-evaluation.md) for A16,
[`docs/execution-and-dataset.md`](docs/execution-and-dataset.md) for A17-A18,
[`docs/training-run.md`](docs/training-run.md) for A19,
[`docs/model-candidate-promotion.md`](docs/model-candidate-promotion.md) for A20,
[`docs/orchestration-activation.md`](docs/orchestration-activation.md) for A21 and
[`docs/runtime-activation.md`](docs/runtime-activation.md) for A22.
