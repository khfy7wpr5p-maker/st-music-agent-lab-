from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from .catalog import DEFAULT_MODELS
from .contracts import AgentTask, ModelProfile, TaskKind
from .execution import DirectAgentRunner
from .providers import OpenAICompatibleClient, OpenAICompatibleConfig
from .router import ModelRouter
from .web_app import serve_operator_console


def _profile(name: str) -> ModelProfile:
    for profile in DEFAULT_MODELS:
        if profile.name == name:
            return profile
    available = ", ".join(profile.name for profile in DEFAULT_MODELS)
    raise SystemExit(f"unknown profile {name!r}; available profiles: {available}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="st-music-agent")
    parser.add_argument("instruction")
    parser.add_argument("--profile", default="GLM-5.1")
    parser.add_argument("--kind", choices=[kind.value for kind in TaskKind], default="code")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--api-key-env", required=True)
    return parser


def build_app_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="st-music-agent app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--github-token-env", default="GITHUB_TOKEN")
    parser.add_argument("--github-api-base", default="https://api.github.com")
    return parser


def _run_agent(argv: Sequence[str]) -> int:
    args = build_parser().parse_args(argv)
    profile = _profile(args.profile)
    client = OpenAICompatibleClient(
        profile,
        OpenAICompatibleConfig(
            base_url=args.base_url,
            model=args.model,
            api_key_env=args.api_key_env,
        ),
    )
    runner = DirectAgentRunner(ModelRouter((profile,)), {profile.name: client})
    result = runner.run(AgentTask(args.instruction, kind=TaskKind(args.kind)))
    print(json.dumps(dict(result.message), ensure_ascii=False))
    return 0


def _run_app(argv: Sequence[str]) -> int:
    args = build_app_parser().parse_args(argv)
    serve_operator_console(
        host=args.host,
        port=args.port,
        token_env=args.github_token_env or None,
        api_base=args.github_api_base,
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] == "app":
        return _run_app(raw[1:])
    return _run_agent(raw)


if __name__ == "__main__":
    raise SystemExit(main())
