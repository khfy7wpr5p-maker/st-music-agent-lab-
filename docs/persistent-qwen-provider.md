# Persistent Qwen Provider

## Goal

Remove the runtime dependency on Colab and temporary Cloudflare tunnels without changing the deterministic executor architecture.

The agent only requires a long-lived OpenAI-compatible provider exposing:

- `GET /health`
- `POST /v1/chat/completions`

The model remains planner-only. GitHub writes continue to be performed by the host-side deterministic executor.

## Generic environment contract

Configure the agent host with:

```text
ST_QWEN_BASE_URL=https://qwen.example.com/v1
ST_QWEN_MODEL=qwen3:4b
ST_QWEN_API_KEY=<secret>
GITHUB_TOKEN=<secret>
```

`ST_QWEN_MODEL` defaults to `qwen3:4b`.

The API key is never stored in source control. For Codespaces, store `ST_QWEN_API_KEY` and, if desired, `ST_QWEN_BASE_URL` as Codespaces secrets.

## Provider host

A portable provider implementation is available in `deploy/qwen-provider/`.

Runtime defaults reproduce the stable T4 configuration validated during development:

- Qwen3 4B
- NF4 4-bit quantization
- input context cap: 4096 tokens
- output cap: 1152 tokens
- generation cache disabled
- CUDA allocator expandable segments enabled in the container

Required provider-host secret:

```text
ST_QWEN_API_KEY=<random-long-secret>
```

Optional provider-host variables:

```text
ST_QWEN_MODEL_ID=Qwen/Qwen3-4B
ST_QWEN_MODEL_NAME=qwen3:4b
ST_QWEN_MAX_INPUT_TOKENS=4096
ST_QWEN_MAX_OUTPUT_TOKENS=1152
```

## Container build

From repository root:

```bash
docker build -f deploy/qwen-provider/Dockerfile -t st-qwen-provider .
```

Run on a host with NVIDIA Container Toolkit and an NVIDIA GPU:

```bash
docker run --gpus all --restart unless-stopped \
  -p 8000:8000 \
  -e ST_QWEN_API_KEY="$ST_QWEN_API_KEY" \
  st-qwen-provider
```

Production deployments should place the service behind HTTPS or a private network. Do not expose port 8000 unauthenticated to the public Internet.

## Agent launch

The wrapper `scripts/run-persistent-qwen-agent.sh` consumes the generic environment contract and starts the existing operator app. No Colab- or Cloudflare-specific value is required.

```bash
export ST_QWEN_BASE_URL=https://qwen.example.com/v1
export ST_QWEN_API_KEY='...'
export GITHUB_TOKEN='...'
bash scripts/run-persistent-qwen-agent.sh
```

## Migration from Colab

1. Start the persistent provider on a GPU host.
2. Verify `GET /health` using the provider API key.
3. Store the stable base URL and API key in the agent host secrets.
4. Launch the agent with the persistent wrapper.
5. Run one bounded smoke task and verify `tool_calls=0`, feature-branch-only writes, and `CI_PENDING`/validator behavior.
6. Retire the Colab runtime and temporary tunnel only after the smoke task passes.

No changes are required to the structured planner, deterministic executor, branch safety, commit binding, or review/CI state machine.
