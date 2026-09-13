from __future__ import annotations

import json

import pytest

from st_music_agent.compact_planner import (
    CompactSmallModelPlanner,
    _compact_candidate_paths,
    _normalize_compact_json_content,
    _supply_missing_plan_summary,
)
from st_music_agent.deterministic_executor import PlanValidationError

REPO = "owner/repo"
BASE = "a" * 40
BRANCH = "fix/compact-planner"
BLOB = "b" * 40


class CapturingProvider:
    def __init__(self, messages):
        self.messages = list(messages)
        self.calls = []

    def complete_with_tools(self, messages, tools):
        self.calls.append((messages, tools))
        return self.messages.pop(0)


class LargeFakeRead:
    def __init__(self) -> None:
        self.files = {
            f"src/file{index:03d}.py": {"sha": BLOB, "content": f"VALUE = {index}\n"}
            for index in range(250)
        }
        self.files["src/target.py"] = {"sha": BLOB, "content": "VALUE = 'old'\n"}

    def repository_tree(self, ref="main"):
        return {
            "ref": ref,
            "commit_sha": BASE,
            "files": [
                {"path": path, "sha": value["sha"], "size": len(value["content"])}
                for path, value in sorted(self.files.items())
            ],
        }

    def read_file(self, path, ref=None):
        value = self.files[path]
        return {
            "path": path,
            "ref": ref,
            "content": value["content"],
            "truncated": False,
            "sha": value["sha"],
        }


def _valid_plan() -> dict:
    return {
        "repository": REPO,
        "base_sha": BASE,
        "feature_branch": BRANCH,
        "changes": [
            {
                "path": "src/target.py",
                "operation": "update",
                "expected_blob_sha": BLOB,
                "content": "VALUE = 'new'\n",
                "commit_message": "Update target deterministically",
            }
        ],
        "validation_targets": [],
        "summary": "Update target",
    }


def test_compact_candidate_paths_caps_and_ranks_explicit_instruction_path() -> None:
    candidates = [
        {"path": f"src/file{index:03d}.py", "sha": BLOB, "size": 10}
        for index in range(250)
    ]
    candidates.append({"path": "src/target.py", "sha": BLOB, "size": 10})

    selected = _compact_candidate_paths(
        candidates,
        "Update src/target.py safely",
    )

    assert len(selected) == 96
    assert selected[0] == "src/target.py"
    assert len(selected) == len(set(selected))


def test_compact_planner_keeps_two_tool_free_calls_with_small_selection_prompt() -> None:
    read = LargeFakeRead()
    provider = CapturingProvider(
        [
            {"role": "assistant", "content": json.dumps({"read_paths": ["src/target.py"]})},
            {"role": "assistant", "content": json.dumps(_valid_plan())},
        ]
    )

    result = CompactSmallModelPlanner(provider).build_plan(
        repository=REPO,
        base_sha=BASE,
        feature_branch=BRANCH,
        instruction="Update src/target.py safely",
        read_client=read,
    )

    assert result.model_calls == 2
    assert result.selected_paths == ("src/target.py",)
    assert result.plan.changes[0].path == "src/target.py"
    assert all(tools == [] for _, tools in provider.calls)

    selection_prompt = provider.calls[0][0][0]["content"]
    selection_payload = json.loads(selection_prompt.splitlines()[-1])
    assert len(selection_payload["candidate_paths"]) == 96
    assert selection_payload["candidate_paths"][0] == "src/target.py"
    assert "candidate_files" not in selection_payload
    assert all(isinstance(path, str) for path in selection_payload["candidate_paths"])


def test_compact_planner_accepts_single_json_markdown_wrapper_without_extra_model_calls() -> None:
    read = LargeFakeRead()
    plan = _valid_plan()
    provider = CapturingProvider(
        [
            {
                "role": "assistant",
                "content": "```json\n" + json.dumps({"read_paths": ["src/target.py"]}) + "\n```",
            },
            {
                "role": "assistant",
                "content": "```\n" + json.dumps(plan) + "\n```",
            },
        ]
    )

    result = CompactSmallModelPlanner(provider).build_plan(
        repository=REPO,
        base_sha=BASE,
        feature_branch=BRANCH,
        instruction="Update src/target.py safely",
        read_client=read,
    )

    assert result.model_calls == 2
    assert len(provider.calls) == 2
    assert result.selected_paths == ("src/target.py",)
    assert result.plan.changes[0].content == "VALUE = 'new'\n"


def test_compact_planner_supplies_only_missing_non_authoritative_summary() -> None:
    read = LargeFakeRead()
    plan = _valid_plan()
    del plan["summary"]
    provider = CapturingProvider(
        [
            {"role": "assistant", "content": json.dumps({"read_paths": ["src/target.py"]})},
            {"role": "assistant", "content": json.dumps(plan)},
        ]
    )

    result = CompactSmallModelPlanner(provider).build_plan(
        repository=REPO,
        base_sha=BASE,
        feature_branch=BRANCH,
        instruction="Update src/target.py safely",
        read_client=read,
    )

    assert result.model_calls == 2
    assert result.plan.summary == "Apply bounded deterministic plan"
    assert result.plan.changes[0].path == "src/target.py"


def test_missing_summary_repair_does_not_mask_other_schema_errors() -> None:
    plan = _valid_plan()
    del plan["summary"]
    plan["unexpected"] = True

    original = json.dumps(plan)
    assert _supply_missing_plan_summary(original) == original


def test_compact_json_normalization_never_extracts_json_from_commentary() -> None:
    wrapped_with_commentary = 'Here is the JSON:\n```json\n{"read_paths":[]}\n```'

    assert _normalize_compact_json_content(wrapped_with_commentary) == wrapped_with_commentary


def test_compact_json_normalization_rejects_invalid_fenced_json() -> None:
    with pytest.raises(PlanValidationError, match="not valid JSON"):
        _normalize_compact_json_content("```json\n{not-json}\n```")
