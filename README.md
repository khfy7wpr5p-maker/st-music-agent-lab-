# ST Music Agent Lab

Model-agnostic orchestration core for autonomous software-engineering and music-intelligence
agents across ST projects.

## Current stage

A1-A15 guarded agent + evidence + verified learning foundation:

- **A1 — Core contracts:** task, model capability, provider and action-risk contracts.
- **A2 — Model routing:** capability-driven selection across current open-model profiles.
- **A3 — Autonomy policy:** deterministic gating for reversible, protected, destructive and
  credential-sensitive operations.
- **A4 — Execution adapters:** OpenAI-compatible provider execution, OpenHands Agent Server
  boundary, environment credential resolution, guarded tool execution and a first CLI.
- **A5 — Guarded workspace:** repository-confined file operations plus a narrow command
  classifier.
- **A6 — Disposable sandbox:** executable repository code requires a hardened sandbox backend;
  the concrete Docker backend is ephemeral, network-disabled and resource-bounded.
- **A7 — Tool-call and evidence boundary:** only registered ST tools execute; output is bounded,
  redacted and optionally recorded in a hash-chained run journal.
- **A8 — Provider tool loop + GitHub read surface:** provider function calls are canonicalized and
  mapped into explicit ST registry tools; read-only GitHub access is bounded.
- **A9 — Policy-aware GitHub mutations:** model-callable writes are limited to reversible feature-
  branch creation/file writing; protected/destructive/external actions remain gated.
- **A10 — Run budgets + host approval broker:** cumulative time/turn/tool/byte budgets plus opaque
  one-shot exact-action approvals.
- **A11 — OpenHands ST bridge:** OpenHands can use the ST registry through one restricted MCP
  bridge; raw TerminalTool/FileEditorTool are not granted.
- **A12 — Score Restore + MusicXML/TAB evidence:** read-only, source-provenanced domain snapshots
  preserve production, Stage 12, REVIEW_REQUIRED and canonical-export boundaries.
- **A13 — Score Editor + score-following evidence:** repository source-of-truth and permanent
  research evidence are available as bounded snapshots without authority inflation.
- **A14 — Planner + independent verifier:** all four snapshots are ranked through one transparent,
  deterministic portfolio policy and independently recomputed before the plan is accepted.
- **A15 — Verified experience learning:** only host-recorded outcomes from exactly verified plans
  enter a hash-chained experience store; models can read advisory summaries but cannot write
  experience history or auto-change policy/models/code.

## Model strategy

The architecture deliberately does not depend on one model. The initial catalog uses GLM-5.1 for
primary agentic engineering, Qwen3.8 as an open long-context secondary profile and Kimi-K2.5 for
multimodal/score-image work. These are replaceable capability profiles, not hard dependencies.

## Framework strategy

OpenHands Software Agent SDK / Agent Server is the preferred external software-agent execution
substrate. OpenHands is connected only through a narrow ST-controlled MCP boundary. A bridged
conversation advertises safe `finish`/`think` built-ins and exact ST registry names; raw
`TerminalTool` and `FileEditorTool` are absent.

## Music-domain evidence tools

`build_default_music_domain_toolset()` creates read-only adapters for four current ST
repositories. Register the returned `FullMusicDomainToolset` into a `ToolRegistry` to expose:

- `music.score_restore.snapshot`
- `music.tab_engine.capability_snapshot`
- `music.score_editor.snapshot`
- `music.score_following.snapshot`

Every snapshot contains an evidence schema version, project/authority, bounded claims, warnings
and source provenance (`repository`, `ref`, `path`, Git blob SHA).

The four current truth boundaries are deliberately different:

- **Score Restore:** evaluation/candidate success does not authorize production inference or
  Stage 12.
- **MusicXML -> TAB:** REVIEW_REQUIRED can preserve provisional TAB/playback, while canonical TAB
  export remains PASS-only.
- **Score Editor:** merged feature work does not open the standalone release matrix or authorize
  SesliTab V4 cutover.
- **Real-time score following:** SF-11 permanent research evidence is not acoustic mono-mixture,
  production or pedagogical authority; SF-12 remains the next research stage.

## Planning and verification

`PortfolioPlanningService` collects all four snapshots and exposes one read-only model tool:

- `music.portfolio.plan`

The plan uses policy version `2026-09-11.v1`. It currently prioritizes closing frozen-candidate
validation/integration uncertainty, then teacher-review integration, then bounded editor feature
work, then new research expansion. This order is explicit policy rather than hidden LLM judgment.

`CrossProjectVerifier` independently recomputes the complete plan from the same source evidence.
Changed source SHAs, altered actions/order, unexpected domain-gate changes or any claim that the
plan authorizes execution cause verification failure. Every portfolio plan has
`execution_authorized=false`.

## Verified experience learning

`ExperienceStore` accepts a structured outcome only from trusted host code and only when the
provided `PlanVerificationReport` is PASS for the exact same deterministic `plan_id`.

The model has no experience-write tool. It may receive only:

- `learning.experience.summary`

`ExperienceAdvisor` classifies verified playbook history as `prefer`, `observe` or `review` after
minimum evidence thresholds. All recommendations set `auto_apply=false`; they cannot alter model
weights, prompts, policies, privileges, tools or repository code.

See [`docs/planning-and-learning.md`](docs/planning-and-learning.md).

## Safety boundary

The model never decides its own privilege level.

- read-only inspection can run autonomously;
- reversible feature-branch writes can run autonomously;
- protected-branch writes, destructive operations and external side effects require exact host
  approval;
- credential exposure is denied and credentials resolve only at trusted adapter boundaries;
- arbitrary local process execution is not a model capability;
- executable repository code runs through a hardened sandbox backend;
- model-facing output and provider loops are bounded;
- OpenHands discovers only the concrete ST registry manifest plus safe finish/think built-ins;
- music-domain snapshots are read-only and fail closed on missing/truncated/drifted evidence;
- repository evaluation/research success never silently promotes a product, model or student-
  facing artifact to a stronger authority level;
- portfolio planning never authorizes execution and is independently recomputed;
- only exact verified outcomes can enter experience history;
- experience recommendations never auto-apply;
- persistent run/experience evidence is sanitized and hash chained.

## Development

```bash
python -m pip install -e '.[dev]'
ruff check src tests
pytest
```

## First direct model run

The CLI works with an OpenAI-compatible provider or self-hosted endpoint. The secret itself is
not passed as a command-line value; only the environment-variable name is configured.

```bash
export ST_AGENT_API_KEY='...'

st-music-agent \
  --profile GLM-5.1 \
  --kind code \
  --base-url https://your-provider.example/v1 \
  --model your-provider-model-id \
  --api-key-env ST_AGENT_API_KEY \
  'Inspect this repository and propose the smallest safe fix.'
```

See [`docs/architecture.md`](docs/architecture.md) for the architecture map,
[`docs/model-selection.md`](docs/model-selection.md) for model/framework research,
[`docs/music-domain-evidence.md`](docs/music-domain-evidence.md) for the music evidence contract
and [`docs/planning-and-learning.md`](docs/planning-and-learning.md) for A14-A15.
