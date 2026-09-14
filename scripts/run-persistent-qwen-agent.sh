#!/usr/bin/env bash
set -euo pipefail

: "${ST_QWEN_BASE_URL:?ST_QWEN_BASE_URL is required}"
: "${ST_QWEN_API_KEY:?ST_QWEN_API_KEY is required}"
: "${GITHUB_TOKEN:?GITHUB_TOKEN is required}"

ST_QWEN_MODEL="${ST_QWEN_MODEL:-qwen3:4b}"
PORT="${ST_AGENT_PORT:-8765}"
STATE_FILE="${ST_AGENT_STATE_FILE:-/tmp/st-music-agent-state.jsonl}"

exec python -m st_music_agent.cli app \
  --host "${ST_AGENT_HOST:-127.0.0.1}" \
  --port "$PORT" \
  --enable-writes \
  --profile "${ST_AGENT_PROFILE:-Local-Qwen3-Test}" \
  --provider-base-url "$ST_QWEN_BASE_URL" \
  --provider-model "$ST_QWEN_MODEL" \
  --provider-api-key-env ST_QWEN_API_KEY \
  --github-token-env GITHUB_TOKEN \
  --task-state-file "$STATE_FILE"
