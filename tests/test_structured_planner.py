from __future__ import annotations

import json

import pytest

from st_music_agent.deterministic_executor import PlanValidationError
from st_music_agent.structured_planner import StructuredCompactPlanner

REPO = "owner/repo"
BASE = "a" * 40
BRANCH = "fix/structured-planner"
BLOB = "b" * 40


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
            "files": [
                {"path": "src/existing.js", "sha": BLOB, "size": 20},
                {"path": "package.json", "sha": "c" * 40, "size": 40},
            ],
        }

    def read_file(self, path, ref=None):
        assert path == "src/existing.js"
        return {
            "path": path,
            "ref": ref,
            "content": "module.exports = 1;\n",
            "truncated": False,
            "sha": BLOB,
        }


def test_structured_planner_separates_manifest_from_file_content() -> None:
    manifest = {
        "changes": [
            {
                "path": "src/existing.js",
                "operation": "update",
                "expected_blob_sha": BLOB,
                "commit_message": "Update existing file",
            }
        ],
        "validation_targets": [],
        "summary": "Update existing file",
    }
    provider = CapturingProvider(
        [
            {"role": "assistant", "content": json.dumps({"read_paths": ["src/existing.js"]})},
            {"role": "assistant", "content": json.dumps(manifest)},
            {"role": "assistant", "content": "module.exports = 2;\n"},
        ]
    )

    result = StructuredCompactPlanner(provider).build_plan(
        repository=REPO,
        base_sha=BASE,
        feature_branch=BRANCH,
        instruction="Update src/existing.js to export 2",
        read_client=FakeRead(),
    )

    assert result.model_calls == 3
    assert result.selected_paths == ("src/existing.js",)
    assert result.plan.repository == REPO
    assert result.plan.base_sha == BASE
    assert result.plan.feature_branch == BRANCH
    assert result.plan.changes[0].content == "module.exports = 2;\n"
    assert result.plan.changes[0].expected_blob_sha == BLOB
    assert all(tools == [] for _, tools in provider.calls)

    manifest_prompt = provider.calls[1][0][0]["content"]
    assert "Do not include file content in JSON" in manifest_prompt
    assert '"repository"' not in manifest_prompt.splitlines()[0]

    content_prompt = provider.calls[2][0][0]["content"]
    assert "Return file content only" in content_prompt


def test_structured_planner_host_binds_create_plan_identity() -> None:
    manifest = {
        "changes": [
            {
                "path": "tests/new.test.js",
                "operation": "create",
                "expected_blob_sha": None,
                "commit_message": "Add regression test",
            }
        ],
        "validation_targets": [],
        "summary": "Add regression test",
    }
    provider = CapturingProvider(
        [
            {"role": "assistant", "content": '{"read_paths":[]}'},
            {"role": "assistant", "content": json.dumps(manifest)},
            {"role": "assistant", "content": "'use strict';\n"},
        ]
    )

    result = StructuredCompactPlanner(provider).build_plan(
        repository=REPO,
        base_sha=BASE,
        feature_branch=BRANCH,
        instruction="Create tests/new.test.js",
        read_client=FakeRead(),
    )

    change = result.plan.changes[0]
    assert result.model_calls == 3
    assert change.path == "tests/new.test.js"
    assert change.operation == "create"
    assert change.expected_blob_sha is None
    assert change.content == "'use strict';\n"


def test_structured_planner_rejects_manifest_with_content_field() -> None:
    manifest = {
        "changes": [
            {
                "path": "tests/new.test.js",
                "operation": "create",
                "expected_blob_sha": None,
                "commit_message": "Add regression test",
                "content": "must not be in manifest",
            }
        ],
        "validation_targets": [],
        "summary": "Add regression test",
    }
    provider = CapturingProvider(
        [
            {"role": "assistant", "content": '{"read_paths":[]}'},
            {"role": "assistant", "content": json.dumps(manifest)},
        ]
    )

    with pytest.raises(PlanValidationError, match="change fields are invalid"):
        StructuredCompactPlanner(provider).build_plan(
            repository=REPO,
            base_sha=BASE,
            feature_branch=BRANCH,
            instruction="Create tests/new.test.js",
            read_client=FakeRead(),
        )
