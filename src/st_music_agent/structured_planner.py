from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .compact_planner import CompactSmallModelPlanner, _compact_candidate_paths
from .deterministic_executor import (
    PlanValidationError,
    PlannerResult,
    TaskReadClient,
    _is_sensitive_path,
    _message_content,
    _parse_selection,
    parse_execution_plan,
)

_MANIFEST_TOP_LEVEL_KEYS = frozenset({"changes", "validation_targets", "summary"})
_MANIFEST_CHANGE_KEYS = frozenset(
    {"path", "operation", "expected_blob_sha", "commit_message"}
)


class StructuredCompactPlanner(CompactSmallModelPlanner):
    """Host-bound planner that keeps code content out of the control-plane JSON.

    The model first selects read evidence, then emits a compact mutation manifest that contains
    only paths, operations and commit metadata. File contents are generated in separate bounded
    calls as plain text. The host injects repository/base/branch identity and runs the assembled
    plan through the existing authoritative ``parse_execution_plan`` validator before any write.

    This avoids asking small local models to JSON-escape entire source files while preserving all
    deterministic executor security boundaries.
    """

    def build_plan(
        self,
        *,
        repository: str,
        base_sha: str,
        feature_branch: str,
        instruction: str,
        read_client: TaskReadClient,
    ) -> PlannerResult:
        tree = read_client.repository_tree(feature_branch)
        if tree.get("commit_sha") != base_sha:
            raise PlanValidationError(
                "structured planner inspection requires feature branch at exact base SHA"
            )
        raw_files = tree.get("files")
        if not isinstance(raw_files, list):
            raise PlanValidationError("repository tree evidence is invalid")

        candidates: list[dict[str, Any]] = []
        existing_by_path: dict[str, Mapping[str, Any]] = {}
        for item in raw_files:
            if not isinstance(item, Mapping):
                continue
            path = item.get("path")
            sha = item.get("sha")
            if not isinstance(path, str) or not isinstance(sha, str):
                continue
            if _is_sensitive_path(path):
                continue
            evidence = {"path": path, "sha": sha, "size": item.get("size")}
            candidates.append(evidence)
            existing_by_path[path] = evidence

        compact_candidates = [
            {"path": path}
            for path in _compact_candidate_paths(candidates, instruction)
        ]
        selection_message = self._complete(
            self._selection_prompt(
                repository=repository,
                base_sha=base_sha,
                feature_branch=feature_branch,
                instruction=instruction,
                candidates=compact_candidates,
            )
        )
        selection = _parse_selection(
            _message_content(selection_message),
            existing_paths=frozenset(existing_by_path),
            max_paths=self.max_selected_files,
        )

        file_evidence: list[dict[str, Any]] = []
        for path in selection.read_paths:
            evidence = read_client.read_file(path, feature_branch)
            if evidence.get("truncated") is True:
                raise PlanValidationError(f"planner evidence file is truncated: {path}")
            content = evidence.get("content")
            sha = evidence.get("sha")
            if not isinstance(content, str) or not isinstance(sha, str):
                raise PlanValidationError(f"planner evidence file is invalid: {path}")
            if len(content) > self.max_content_chars_per_file:
                raise PlanValidationError(f"planner evidence file exceeds content limit: {path}")
            if sha != existing_by_path[path].get("sha"):
                raise PlanValidationError(f"planner evidence blob changed during inspection: {path}")
            file_evidence.append({"path": path, "sha": sha, "content": content})

        manifest_message = self._complete(
            self._manifest_prompt(
                instruction=instruction,
                file_evidence=file_evidence,
            )
        )
        manifest = _parse_manifest(
            _message_content(manifest_message),
            max_changed_files=self.max_changed_files,
        )

        rendered_changes: list[dict[str, Any]] = []
        model_calls = 2
        for change in manifest["changes"]:
            content = _exact_create_content_contract(
                instruction=instruction,
                path=change["path"],
                operation=change["operation"],
            )
            if content is None:
                content_message = self._complete_content(
                    self._content_prompt(
                        instruction=instruction,
                        change=change,
                        file_evidence=file_evidence,
                    )
                )
                model_calls += 1
                content = _normalize_file_content(_message_content(content_message))
            content = _enforce_final_newline_contract(instruction, content)
            if len(content) > self.max_content_chars_per_file:
                raise PlanValidationError(
                    f"generated file content exceeds configured limit: {change['path']}"
                )
            rendered_changes.append({**change, "content": content})

        assembled = {
            "repository": repository,
            "base_sha": base_sha,
            "feature_branch": feature_branch,
            "changes": rendered_changes,
            "validation_targets": manifest["validation_targets"],
            "summary": manifest["summary"],
        }
        plan = parse_execution_plan(
            json.dumps(assembled, ensure_ascii=False, separators=(",", ":")),
            expected_repository=repository,
            expected_base_sha=base_sha,
            expected_feature_branch=feature_branch,
            allowed_update_paths=frozenset(selection.read_paths),
            existing_paths=frozenset(existing_by_path),
            max_changed_files=self.max_changed_files,
            max_content_chars_per_file=self.max_content_chars_per_file,
        )
        return PlannerResult(
            plan=plan,
            selected_paths=selection.read_paths,
            model_calls=model_calls,
            final_message={"role": "assistant", "content": plan.summary},
        )

    def _complete_content(self, prompt: str) -> Mapping[str, Any]:
        message = self.provider.complete_with_tools(
            [{"role": "user", "content": prompt}],
            [],
        )
        if not isinstance(message, Mapping):
            raise PlanValidationError("planner content response must be an object")
        if message.get("tool_calls") not in (None, []):
            raise PlanValidationError("planner content generation must not request tools")
        content = message.get("content")
        if not isinstance(content, str):
            raise PlanValidationError("planner content response must contain text")
        return message

    def _manifest_prompt(
        self,
        *,
        instruction: str,
        file_evidence: Sequence[Mapping[str, Any]],
    ) -> str:
        payload = {
            "instruction": instruction,
            "read_evidence": [
                {"path": item["path"], "sha": item["sha"]}
                for item in file_evidence
            ],
        }
        return (
            "Return one compact JSON mutation manifest only. Do not include file content in JSON. "
            "Top-level keys must be exactly changes, validation_targets, summary. Each changes item "
            "must contain exactly path, operation, expected_blob_sha, commit_message. operation is "
            "create or update. For create, expected_blob_sha must be null. For update, use only a path "
            "from read_evidence and copy its exact sha. Plan at most "
            f"{self.max_changed_files} changes. Never request protected branches, credentials, workflows, "
            "deploy/release/training/activation/rollback, PR, merge or shell actions. "
            "validation_targets may be []. Return JSON only, no markdown or commentary.\n"
            + json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )

    @staticmethod
    def _content_prompt(
        *,
        instruction: str,
        change: Mapping[str, Any],
        file_evidence: Sequence[Mapping[str, Any]],
    ) -> str:
        payload = {
            "instruction": instruction,
            "change": dict(change),
            "selected_read_evidence": [dict(item) for item in file_evidence],
        }
        return (
            "Generate the complete UTF-8 content for exactly one planned file. Return file content only: "
            "no JSON wrapper, no explanation, no markdown fence, no path header. Follow the user task "
            "exactly. Use selected_read_evidence when the requested file depends on existing repository "
            "contracts. For an update, preserve unrelated content. For a create, produce the complete new "
            "file. Do not emit credentials, workflow controls, deploy/release/training/activation/rollback "
            "content.\n"
            + json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )


def _parse_manifest(raw_json: str, *, max_changed_files: int) -> dict[str, Any]:
    try:
        value = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise PlanValidationError("structured planner manifest is not valid JSON") from exc
    if not isinstance(value, dict) or frozenset(value) != _MANIFEST_TOP_LEVEL_KEYS:
        raise PlanValidationError("structured planner manifest fields are invalid")

    changes = value.get("changes")
    if not isinstance(changes, list) or not changes:
        raise PlanValidationError("structured planner manifest must contain file changes")
    if len(changes) > max_changed_files:
        raise PlanValidationError("structured planner manifest exceeds changed-file limit")
    for change in changes:
        if not isinstance(change, dict) or frozenset(change) != _MANIFEST_CHANGE_KEYS:
            raise PlanValidationError("structured planner change fields are invalid")
        if not isinstance(change.get("path"), str) or not change["path"]:
            raise PlanValidationError("structured planner change path is invalid")
        if change.get("operation") not in {"create", "update"}:
            raise PlanValidationError("structured planner change operation is invalid")
        expected_sha = change.get("expected_blob_sha")
        if expected_sha is not None and not isinstance(expected_sha, str):
            raise PlanValidationError("structured planner expected blob SHA is invalid")
        if not isinstance(change.get("commit_message"), str) or not change["commit_message"].strip():
            raise PlanValidationError("structured planner commit message is invalid")

    validation_targets = value.get("validation_targets")
    if not isinstance(validation_targets, list) or any(
        not isinstance(item, str) for item in validation_targets
    ):
        raise PlanValidationError("structured planner validation_targets are invalid")
    if not isinstance(value.get("summary"), str) or not value["summary"].strip():
        raise PlanValidationError("structured planner summary is invalid")
    return value


def _normalize_file_content(content: str) -> str:
    """Strip one whole-response markdown fence; otherwise preserve model text verbatim."""

    stripped = content.strip()
    if not stripped.startswith("```"):
        return content
    lines = stripped.splitlines()
    if len(lines) < 3 or lines[-1].strip() != "```":
        return content
    opening = lines[0].strip()
    if not opening.startswith("```") or opening.count("```") != 1:
        return content
    return "\n".join(lines[1:-1]) + ("\n" if content.endswith("\n") else "")


def _exact_create_content_contract(*, instruction: str, path: str, operation: str) -> str | None:
    """Return host-authoritative literal content for a narrow exact-create instruction."""

    if operation != "create":
        return None
    pattern = re.compile(
        rf"create exactly one new file\s+{re.escape(path)}\s+"
        r"with exactly this content:[ \t]*(?P<content>.*?)\s+followed by one newline\.",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(instruction)
    if match is None:
        return None
    return match.group("content") + "\n"


def _enforce_final_newline_contract(instruction: str, content: str) -> str:
    """Apply an explicit user-requested final newline without changing unrelated content."""

    normalized = " ".join(instruction.casefold().split())
    requires_newline = any(
        phrase in normalized
        for phrase in (
            "followed by one newline",
            "end with newline",
            "end with a newline",
            "ends with newline",
            "ends with a newline",
            "final newline",
        )
    )
    if requires_newline and not content.endswith("\n"):
        return content + "\n"
    return content
