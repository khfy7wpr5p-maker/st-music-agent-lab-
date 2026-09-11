# ST Music Agent Lab

Model-agnostic orchestration core for autonomous software-engineering and music-intelligence
agents across ST projects.

## Current stage

A1-A16 guarded agent + evidence + verified learning/evaluation foundation:

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

A15 experience advice is not enough to change a playbook, prompt, policy or model. A16 adds
`LearningEvaluationGate`, which compares the current baseline and a candidate on the exact same
paired benchmark cases.

Default gate:

- at least 8 paired cases;
- at least 2 critical cases;
- identical case ids and severities;
- no candidate regression on any case;
- no critical failure;
- at least one strict improvement.

Outcomes are ordered conservatively as `failure < abstained < success`. A tie is not an
improvement. A candidate can only become `eligible_for_host_review`; `auto_promote` is always
false.

The only model-facing A16 tool is read-only:

- `learning.evaluation.policy`

There is no model-callable benchmark-result submission, promotion, prompt/policy mutation or model
weight update.

See [`docs/learning-evaluation.md`](docs/learning-evaluation.md).

## Safety boundary

The model never decides its own privilege level.

- read-only inspection can run autonomously;
- reversible feature-branch writes can run autonomously;
- protected/destructive/external actions require exact host approval;
- executable repository code runs only through the guarded sandbox path;
- OpenHands discovers only the concrete ST registry manifest plus safe finish/think built-ins;
- music snapshots fail closed on missing/truncated/drifted authority evidence;
- portfolio plans never authorize execution and are independently recomputed;
- only exact verified outcomes can enter experience history;
- experience recommendations never auto-apply;
- candidate improvement must survive paired benchmark evaluation before host review;
- benchmark eligibility still never auto-promotes a candidate;
- persistent run/experience evidence is sanitized and hash chained.

## Development

```bash
python -m pip install -e '.[dev]'
ruff check src tests
pytest
```

See [`docs/architecture.md`](docs/architecture.md) for the architecture map,
[`docs/music-domain-evidence.md`](docs/music-domain-evidence.md) for music evidence,
[`docs/planning-and-learning.md`](docs/planning-and-learning.md) for A14-A15 and
[`docs/learning-evaluation.md`](docs/learning-evaluation.md) for A16.
