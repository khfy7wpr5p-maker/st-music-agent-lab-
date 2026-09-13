from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .deterministic_executor import PlanValidationError, SmallModelPlanner

_MAX_COMPACT_CANDIDATES = 96
_MAX_WRAPPER_COMMENTARY = 160
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
_FENCED_JSON_BLOCK = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.IGNORECASE | re.DOTALL)
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
_PLAN_KEYS_WITHOUT_SUMMARY = frozenset(
    {
        "repository",
        "base_sha",
        "feature_branch",
        "changes",
        "validation_targets",
    }
)
_DEFAULT_PLAN_SUMMARY = "Apply bounded deterministic plan"


class CompactSmallModelPlanner(SmallModelPlanner):
    """Small-model planner with host-compacted prompts and unchanged strict host validation."""

    def _complete(self, prompt: str) -> Mapping[str, Any]:
        message = super()._complete(prompt)
        content = message.get("content")
        normalized = _normalize_compact_json_content(content)
        normalized = _supply_missing_plan_summary(normalized)
        if normalized == content:
            return message
        result = dict(message)
        result["content"] = normalized
        return result

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
            '{"read_paths":["path"]}. Return JSON only. Use [] when no read is needed. '
            "No extra fields. Do not use markdown fences or commentary; the first non-whitespace "
            "character must be { and the last must be }.\n"
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
            "changes, validation_targets, summary. summary is required and must be a short string. "
            "Each changes item must contain exactly: path, operation, expected_blob_sha, content, "
            "commit_message. operation is create or update. Updates may target only paths present in "
            "read_evidence and must reuse that exact blob SHA. Creates must use a new safe path and "
            "expected_blob_sha=null. Never target main/master, credentials, GitHub workflow or action "
            "control files, deploy/release/training/activation/rollback surfaces. Plan at most "
            f"{self.max_changed_files} changes. validation_targets may be []. Do not use markdown fences "
            "or commentary; the first non-whitespace character must be { and the last must be }.\n"
            + json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )


def _plain_commentary_is_safe(text: str) -> bool:
    if len(text) > _MAX_WRAPPER_COMMENTARY:
        return False
    if any(char in text for char in "{}[]`"):
        return False
    return not any(not char.isprintable() and not char.isspace() for char in text)


def _normalize_compact_json_content(content: Any) -> str:
    """Normalize one bounded JSON wrapper without weakening plan validation.

    Small local models sometimes prepend or append a short phrase even after being told to emit JSON
    only. The host may remove exactly one fenced JSON wrapper, or bounded non-structural prose around
    exactly one raw JSON object. It never accepts multiple JSON values or discards structural content.
    Exact schema, repository/branch binding, path, SHA and mutation limits remain enforced by the
    authoritative planner parsers.
    """

    if not isinstance(content, str):
        raise PlanValidationError("compact planner response content must be text")

    text = content.strip()
    matches = list(_FENCED_JSON_BLOCK.finditer(text))
    if matches:
        if len(matches) != 1:
            return text
        match = matches[0]
        prefix = text[: match.start()].strip()
        suffix = text[match.end() :].strip()
        if not _plain_commentary_is_safe(prefix + suffix):
            return text

        inner = match.group(1).strip()
        if not inner:
            raise PlanValidationError("compact planner fenced JSON response is empty")
        try:
            value = json.loads(inner)
        except json.JSONDecodeError as exc:
            raise PlanValidationError("compact planner fenced response is not valid JSON") from exc
        if not isinstance(value, dict):
            return text
        return inner

    first_object = text.find("{")
    if first_object < 0:
        return text

    prefix = text[:first_object].strip()
    if not _plain_commentary_is_safe(prefix):
        return text

    decoder = json.JSONDecoder()
    try:
        value, consumed = decoder.raw_decode(text[first_object:])
    except json.JSONDecodeError:
        return text
    if not isinstance(value, dict):
        return text

    suffix = text[first_object + consumed :].strip()
    if not _plain_commentary_is_safe(suffix):
        return text

    return text[first_object : first_object + consumed].strip()


def _supply_missing_plan_summary(content: str) -> str:
    """Fill only non-authoritative summary metadata when every security-relevant plan key is present."""

    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        return content

    if not isinstance(value, dict) or frozenset(value) != _PLAN_KEYS_WITHOUT_SUMMARY:
        return content

    value["summary"] = _DEFAULT_PLAN_SUMMARY
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


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
