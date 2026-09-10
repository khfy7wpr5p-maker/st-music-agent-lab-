# Model and Agent Framework Selection

Research date: 2026-09-11

## Decision

ST Music Agent Lab should be model-agnostic. The initial catalog uses three complementary
open models rather than making the repository depend on a single vendor.

### 1. GLM-5.1 — primary agentic-engineering profile

Use for long-horizon repository work, planning, debugging and tool-driven engineering.
The official GLM-5 repository describes GLM-5.1 as its next-generation flagship for
agentic engineering and publishes downloadable model weights. The repository is Apache-2.0.

Sources:
- https://github.com/zai-org/GLM-5
- https://docs.z.ai/guides/overview/migrate-to-glm-new

### 2. Qwen3.8 — secondary open model / longer-context fallback

Use as an independent second implementation path and for tasks needing more context than
our GLM-5.1 profile declares. Qwen3.8 is an open release designed for coding, research and
long-horizon agentic tasks. Official examples expose a 262144-token serving context and
OpenAI-compatible serving through SGLang/vLLM.

Sources:
- https://github.com/QwenLM/Qwen3.8
- https://github.com/QwenLM/qwen-code

### 3. Kimi-K2.5 — multimodal score-analysis profile

Use when a task requires image understanding, including future score-page and notation
inspection. The official model description emphasizes native multimodality, tool use,
agentic execution and a 256K context window. Code and model weights use a Modified MIT license.

Source:
- https://github.com/OpenKimi/Kimi-K2.5

## Agent framework comparison

### OpenHands

Best fit as the first execution-backend candidate. It provides a modular Python Software
Agent SDK, agent server, tools, workspaces and model-agnostic execution. It should be attached
through an adapter rather than copied into this repository.

Sources:
- https://github.com/OpenHands/software-agent-sdk
- https://github.com/OpenHands/OpenHands

### mini-SWE-agent

Strong reference for keeping the engineering loop small and testable. It is useful as an
architectural benchmark, especially for issue-to-fix workflows, but ST Music Agent requires
additional music-domain routing and evidence contracts.

Source:
- https://github.com/SWE-agent/mini-swe-agent

### OpenManus

Useful reference for general agents, MCP tools and multi-agent experiments. It is intentionally
not selected as the core dependency because ST Music Agent needs a software-engineering runtime,
strict action-risk boundaries and music-specific adapters rather than a general-agent fork.

Source:
- https://github.com/FoundationAgents/OpenManus

## Why routing is preferable to one fixed model

The project spans different capability classes: repository coding, long-running planning,
research, score images and later music-domain tools. A single fixed model would couple every
future integration to one model's context, modalities, parser and API behavior. The A2 router
therefore makes the model a replaceable capability profile.

## Current boundary

A1-A3 contain no API keys, provider SDKs, network calls or model downloads. This is deliberate.
Provider execution and sandbox integration belong to A4+ after the contracts and safety policy
are stable and tested.
