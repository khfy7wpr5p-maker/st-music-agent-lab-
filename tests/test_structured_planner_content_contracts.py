from __future__ import annotations

import json

from st_music_agent.structured_planner import StructuredCompactPlanner

REPO = "owner/repo"
BASE = "a" * 40
BRANCH = "fix/structured-planner"


class CapturingProvider:
    def __init__(self, messages):
        self.messages = list(messages)
        self.calls = []

    def complete_with_tools(self, messages, tools):
        self.calls.append((messages, tools))
        return self.messages.pop(0)


class FakeRead:
    def repository_tree(self, ref="main"):
        return {
            "ref": ref,
            "commit_sha": BASE,
            "files": [{"path": "package.json", "sha": "c" * 40, "size": 40}],
        }

    def read_file(self, path, ref=None):
        raise AssertionError("exact create contract should not read repository files")


def _manifest(path: str) -> str:
    return json.dumps(
        {
            "changes": [
                {
                    "path": path,
                    "operation": "create",
                    "expected_blob_sha": None,
                    "commit_message": "Create contract file",
                }
            ],
            "validation_targets": [],
            "summary": "Create contract file",
        }
    )


def test_exact_create_content_is_host_authoritative_and_keeps_final_newline() -> None:
    path = "docs/exact.txt"
    provider = CapturingProvider(
        [
            {"role": "assistant", "content": '{"read_paths":[]}'},
            {"role": "assistant", "content": _manifest(path)},
        ]
    )

    result = StructuredCompactPlanner(provider).build_plan(
        repository=REPO,
        base_sha=BASE,
        feature_branch=BRANCH,
        instruction=(
            "Create exactly one new file docs/exact.txt with exactly this content: "
            "ST_AGENT_QWEN4B_STRUCTURED_OK followed by one newline. "
            "Do not modify any existing file."
        ),
        read_client=FakeRead(),
    )

    assert result.model_calls == 2
    assert len(provider.calls) == 2
    assert result.plan.changes[0].content == "ST_AGENT_QWEN4B_STRUCTURED_OK\n"


def test_explicit_final_newline_is_added_to_generated_content() -> None:
    path = "docs/generated.txt"
    provider = CapturingProvider(
        [
            {"role": "assistant", "content": '{"read_paths":[]}'},
            {"role": "assistant", "content": _manifest(path)},
            {"role": "assistant", "content": "hello"},
        ]
    )

    result = StructuredCompactPlanner(provider).build_plan(
        repository=REPO,
        base_sha=BASE,
        feature_branch=BRANCH,
        instruction="Create docs/generated.txt. The file must end with a newline.",
        read_client=FakeRead(),
    )

    assert result.model_calls == 3
    assert result.plan.changes[0].content == "hello\n"
