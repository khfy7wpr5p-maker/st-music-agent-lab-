# ST Music Agent Lab — Architecture Map

Status: A1-A3 foundation
Date: 2026-09-11

## Purpose

ST Music Agent Lab is a model-agnostic engineering and music-intelligence agent layer.
Its job is not to become another monolithic chatbot. It should coordinate models and tools
around ST repositories while keeping autonomy observable, reversible, and capability-driven.

Initial target domains:

- repository inspection, coding, tests, CI and documentation;
- music-score and notation analysis;
- research and architecture planning;
- later adapters for ST Score Restore, Score Editor, MusicXML/TAB and score-following projects.

## Design decision

Do not fork a large agent framework into this repository.
Keep the ST core small and stable, then attach execution backends through adapters.

Research references:

- OpenHands Software Agent SDK: modular model-agnostic execution substrate.
- mini-SWE-agent: minimal software-engineering agent reference.
- OpenManus: useful general-agent and MCP reference, but not the core dependency.
- Qwen Code / Qwen-Agent: useful Qwen-native terminal and MCP integrations.

## A1 — Core contracts

`contracts.py` defines stable boundaries for:

- task intent (`AgentTask`);
- task categories (`TaskKind`);
- model capabilities (`ModelProfile`);
- action risk (`RiskLevel`);
- provider adapter contract (`ModelClient`).

No provider SDK is allowed to leak into these contracts.

## A2 — Capability-driven model routing

`catalog.py` contains the initial researched model profiles.
`router.py` selects a model from declared task requirements.

Initial routing intent:

- GLM-5.1: primary long-horizon agentic engineering, planning, research and code.
- Qwen3.8: open secondary model and longer-context fallback.
- Kimi-K2.5: multimodal/score-image specialist and fallback agent model.

The names are configuration data, not architectural dependencies.

## A3 — Autonomous execution policy

`policy.py` separates routine autonomous work from actions requiring human approval.

Default behavior:

- read-only inspection: autonomous;
- reversible writes on a feature branch: autonomous;
- direct protected-branch writes: human approval;
- destructive or external side-effect actions: human approval;
- secret/credential access requests: denied by the core policy.

This policy is intentionally independent from any LLM.
A model cannot promote its own privileges.

## Planned continuation

A4 and later should add adapters rather than replace the core:

1. OpenAI-compatible provider adapter.
2. OpenHands execution adapter / sandbox integration.
3. GitHub tool adapter with explicit action risk metadata.
4. Persistent run journal and resumable state.
5. Music-domain tool adapters and structured evidence.
6. Evaluation corpus for coding, notation and tool-use tasks.

## Architectural invariants

1. Model choice is replaceable.
2. Tools declare risk before execution.
3. Protected/destructive actions cannot be silently escalated.
4. Failure to find a compatible model fails closed.
5. Music-specific intelligence stays above generic execution infrastructure.
6. Tests define routing and autonomy behavior before provider integrations are added.
