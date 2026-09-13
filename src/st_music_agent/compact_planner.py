from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .deterministic_executor import SmallModelPlanner

_MAX_COMPACT_CANDIDATES = 96
_COMMON_TOKENS = frozenset(
    {
        "and",
        "create",
        "exactly",
        "file",
        "for",
        "from",
        "into",
        "only",
        "please",
        "safe",
        "the",
        "this",
        "update",
        "with",
    }
)
_TOKEN = re.compile(r"[a-z0-9][a-z0-9_.-]{1,}")
_PRIORITY_BASENAMES = frozenset(
    {
        "readme.md",
        "pyproject.toml",
        "package.json",
        "requirements.txt",
        "setup.py",
        "setup.cfg",
    }
)


class CompactSmallModelPlanner(SmallModelPlanner):
    """Small-model planner with host-compacted prompts and unchanged strict host validation."""

    def _selection_prompt(
        self,
        *,
        repository: str,
        base_sha: str,
        feature_branch: str,
        instruction: str,
        candidates: Sequence[Mapping[str, Any]],
    ) -> str:
        candidate_paths = _compact_candidate_paths(candidates, instruction)
        payload = {
            "repository": repository,
            "base_sha": base_sha,
            "feature_branch": feature_branch,
            "instruction": instruction,
            "candidate_paths": candidate_paths,
        }
        return (
            "Select existing files to read before planning. Do not request tools. "
            f"Choose at most {self.max_selected_files} paths from candidate_paths. "
            'Return JSON only: {"read_paths":["path"]}. Use [] when no read is needed. '
            "No extra fields.\n"
            + json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )

    def _plan_prompt(
        self,
        *,
        repository: str,
        base_sha: str,
        feature_branch: str,
        instruction: str,
        file_evidence: Sequence[Mapping[str, Any]],
    ) -> str:
        payload = {
            "repository": repository,
            "base_sha": base_sha,
            "feature_branch": feature_branch,
            "instruction": instruction,
            "read_evidence": [dict(item) for item in file_evidence],
        }
        return (
            "Return one strict JSON object only. The host executes mutations; you have no write, shell, "
            "PR or merge authority. Top-level keys must be exactly: repository, base_sha, feature_branch, "
            "changes, validation_targets, summary. Each changes item must contain exactly: path, operation, "
            "expected_blob_sha, content, commit_message. operation is create or update. Updates may target "
            "only paths present in read_evidence and must reuse that exact blob SHA. Creates must use a new "
            "safe path and expected_blob_sha=null. Never target main/master, credentials, GitHub workflow or "
            f"action control files, deploy/release/training/activation/rollback surfaces. Plan at most "
            f"{self.max_changed_files} changes. validation_targets may be [].\n"
            + json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )


def _compact_candidate_paths(
    candidates: Sequence[Mapping[str, Any]],
    instruction: str,
    *,
    limit: int = _MAX_COMPACT_CANDIDATES,
) -> list[str]:
    if limit < 1:
        raise ValueError("compact candidate limit must be >= 1")

    instruction_lower = instruction.lower()
    tokens = {
        token
        for token in _TOKEN.findall(instruction_lower)
        if len(token) >= 2 and token not in _COMMON_TOKENS
    }
    ranked: list[tuple[int, str]] = []
    seen: set[str] = set()
    for item in candidates:
        path = item.get("path")
        if not isinstance(path, str) or path in seen:
            continue
        seen.add(path)
        lowered = path.lower()
        basename = lowered.rsplit("/", 1)[-1]
        score = 0
        if lowered in instruction_lower:
            score += 1000
        for token in tokens:
            if token == basename:
                score += 40
            elif token in basename:
                score += 12
            elif token in lowered:
                score += 4
        if basename in _PRIORITY_BASENAMES:
            score += 1
        ranked.append((score, path))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [path for _score, path in ranked[:limit]]
