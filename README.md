# ST Music Agent Lab

Model-agnostic orchestration core for autonomous software-engineering and music-intelligence
agents across ST projects.

## Current stage

A1-A20 guarded agent + evidence + verified learning/evaluation/data/training/model-candidate foundation:

- **A1-A3:** core contracts, model routing and deterministic autonomy policy.
- **A4-A6:** provider/OpenHands boundaries, guarded workspace and disposable sandbox execution.
- **A7-A8:** explicit tool registry, bounded/redacted evidence, hash-chained journal, provider tool
  loop and bounded GitHub reads.
- **A9-A10:** reversible feature-branch mutations, cumulative run budgets and exact one-shot host
  approvals.
- **A11:** restricted OpenHands MCP bridge with no raw TerminalTool/FileEditorTool authority.
- **A12-A13:** read-only, source-provenanced evidence from Score Restore, MusicXML/TAB, Score
  Editor and real-time score following.
- **A14:** deterministic cross-project planner plus independent recomputation verifier.
- **A15:** host-write-only verified experience store and advisory `prefer/observe/review` learning.
- **A16:** paired baseline-vs-candidate benchmark gate before any future playbook/model promotion
  review.
- **A17:** exact execution-outcome evidence binding plan candidate, repository, branch, commit SHA,
  CI and validators in a hash-chained host-only record.
- **A18:** explicit curated dataset export from selected verified execution records, with training
  and promotion authority kept false.
- **A19:** reproducible training-run contract binding exact dataset manifest, base model revision,
  trainer config, seed and code commit to any later checkpoint hash without granting promotion.
- **A20:** immutable model-candidate lineage plus promotion-review recomputation before any
  activation review; activation remains explicitly unauthorized.

## Model strategy

The architecture deliberately does not depend on one model. The initial catalog uses GLM-5.1 for
primary agentic engineering, Qwen3.8 as an open long-context secondary profile and Kimi-K2.5 for
multimodal/score-image work. These are replaceable capability profiles, not hard dependencies.

## Music-domain evidence tools

`build_default_music_domain_toolset()` creates read-only adapters for four current ST repositories
and exposes:

- `music.score_restore.snapshot`
- `music.tab_engine.capability_snapshot`
- `music.score_editor.snapshot`
- `music.score_following.snapshot`

The evidence plane preserves project-specific authority boundaries: evaluation does not imply
Score Restore production, REVIEW_REQUIRED does not imply canonical TAB export, editor feature
completion does not imply release/cutover and score-following research does not imply production or
pedagogical authority.

## Planning and verification

`PortfolioPlanningService` exposes `music.portfolio.plan`. The planner uses explicit versioned
policy rather than hidden LLM judgment. `CrossProjectVerifier` independently recomputes the plan
from the same source evidence; source-SHA drift, altered order/actions or an execution-authorized
claim fail verification. Every accepted plan still has `execution_authorized=false`.

## Verified experience learning

`ExperienceStore` accepts outcomes only from trusted host code and only for the exact PASS-verified
`plan_id`. The model has no experience-write tool. It may only read:

- `learning.experience.summary`

`ExperienceAdvisor` classifies verified history as `prefer`, `observe` or `review`; every
recommendation has `auto_apply=false`.

## A16 learning evaluation

`LearningEvaluationGate` compares the current baseline and a candidate on the same paired benchmark
cases. Defaults require at least 8 cases, at least 2 critical cases, no regression, no critical
failure and at least one strict improvement. A candidate can only become
`eligible_for_host_review`; `auto_promote=false`.

The only model-facing A16 tool is read-only:

- `learning.evaluation.policy`

## A17 exact execution outcome

A successful execution can no longer be represented by a free-form claim. `ExecutionOutcomeStore`
requires the exact verified plan and binds the record to the chosen candidate's rank, project,
action and evidence hash plus the expected repository, branch and full commit SHA.

`SUCCESS` requires every supplied CI and validator check to pass. Failure/abstention must retain
non-green evidence. Records are host-only, append-only and hash chained.

## A18 curated dataset boundary

`CuratedDatasetBuilder` exports only explicitly selected verified execution record IDs. The export
contains structured operational facts but excludes free-form notes and hidden reasoning.

Every manifest states:

- `training_authorized=false`;
- `auto_train=false`;
- `auto_promote=false`.

A `fine_tuning_candidate` export is therefore only a reviewable data artifact, not permission to
train or promote a model.

## A19 reproducible training run contract

`TrainingRunContractBuilder` accepts only a verified `fine_tuning_candidate` dataset manifest and
binds it to an exact base-model id/revision/artifact SHA-256, trainer name/version/config, seed and
training-code Git commit. Those inputs produce a deterministic `input_fingerprint`.

The spec always keeps `execution_authorized=false` and `auto_start=false`. If a separately
authorized host later performs training, the completion contract binds that exact fingerprint to a
host authorization reference, checkpoint SHA-256 and explicit training evidence.

Every completed checkpoint still carries `evaluation_required=true`,
`promotion_authorized=false` and `auto_promote=false`. It must pass the A16 paired evaluation gate
before any promotion review.

## A20 model candidate and promotion review

`ModelCandidateRegistry` turns only a verified completed A19 training lineage into a deterministic
model candidate id. The candidate keeps its checkpoint SHA-256, dataset/base-model lineage and
training fingerprints, while `activation_authorized=false` and `auto_activate=false` remain fixed.

`ModelPromotionReviewGate` receives the registered candidate, the current baseline benchmark run,
the candidate benchmark run and the claimed A16 report. It recomputes A16 itself and rejects any
report that differs from that recomputation.

A passing candidate can become only `eligible_for_activation_review`. The result still states
`human_review_required=true`, `activation_authorized=false` and `auto_activate=false`.

See [`docs/model-candidate-promotion.md`](docs/model-candidate-promotion.md).

## Safety boundary

The model never decides its own privilege level.

- read-only inspection can run autonomously;
- reversible feature-branch writes can run autonomously;
- protected/destructive/external actions require exact host approval;
- executable repository code runs only through the guarded sandbox path;
- OpenHands discovers only the concrete ST registry manifest plus safe finish/think built-ins;
- music snapshots fail closed on missing/truncated/drifted authority evidence;
- portfolio plans never authorize execution and are independently recomputed;
- execution success requires exact plan/commit/CI/validator evidence;
- only exact verified outcomes can enter experience history;
- experience recommendations never auto-apply;
- candidate improvement must survive paired benchmark evaluation before host review;
- benchmark eligibility still never auto-promotes a candidate;
- curated dataset export never authorizes training or model promotion;
- a training spec never authorizes or auto-starts training;
- a trained checkpoint never bypasses independent evaluation or auto-promotes;
- a model candidate never activates itself;
- promotion review independently recomputes A16 and never grants activation authority;
- persistent run/experience/execution evidence is sanitized and hash chained.

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
[`docs/training-run.md`](docs/training-run.md) for A19 and
[`docs/model-candidate-promotion.md`](docs/model-candidate-promotion.md) for A20.
