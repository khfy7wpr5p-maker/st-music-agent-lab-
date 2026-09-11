# ST Music Agent Lab

Model-agnostic orchestration core for autonomous software-engineering and music-intelligence
agents across ST projects.

## Current stage

A1-A13 guarded agent + music evidence foundation:

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
  research evidence are now available as bounded snapshots without silently converting feature
  completion into release authority or research evidence into production/pedagogical authority.

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

`build_default_music_domain_toolset()` now creates read-only adapters for four current ST
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

See [`docs/music-domain-evidence.md`](docs/music-domain-evidence.md).

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
- persistent run evidence is sanitized and hash chained.

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
[`docs/model-selection.md`](docs/model-selection.md) for model/framework research and
[`docs/music-domain-evidence.md`](docs/music-domain-evidence.md) for the music evidence contract.
