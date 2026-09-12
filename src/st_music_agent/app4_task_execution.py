from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from .app3_task_execution import App3GitHubReadClient, App3TaskService, _full_sha
from .github_read import GitHubReadConfig, GitHubReadError
from .task_execution import TaskExecutionError, TaskPreview
from .task_state import TaskOutcome, TaskStage

APP4_REVIEW_SCHEMA_VERSION = "1.0.0"
_MAX_REVIEW_FILES = 100
_MAX_PATCH_CHARS_PER_FILE = 16_000
_MAX_REVIEW_PATCH_CHARS = 160_000
_MAX_REVISION_INSTRUCTION_CHARS = 8_000
_REVIEW_DIGEST = 64


class App4GitHubReadClient(App3GitHubReadClient):
    """APP4 read adapter that exposes a bounded, exact-base/head patch projection."""

    def review_compare(self, base_sha: str, head_sha: str) -> dict[str, Any]:
        for label, value in (("base_sha", base_sha), ("head_sha", head_sha)):
            if not _full_sha(value):
                raise ValueError(f"{label} must be a full lowercase Git SHA")
        data = self._get(f"/compare/{base_sha}...{head_sha}")
        raw_files = data.get("files")
        if not isinstance(raw_files, list):
            raise GitHubReadError("GitHub compare response is missing files")
        if len(raw_files) > _MAX_REVIEW_FILES:
            raise GitHubReadError("review compare exceeds configured file limit")

        files: list[dict[str, Any]] = []
        displayed_chars = 0
        complete = True
        for item in raw_files:
            if not isinstance(item, Mapping):
                continue
            path = item.get("filename")
            if not isinstance(path, str):
                continue
            try:
                safe_path = self._safe_path(path)
            except ValueError:
                continue

            raw_patch = item.get("patch")
            patch_available = isinstance(raw_patch, str)
            full_patch = raw_patch if isinstance(raw_patch, str) else ""
            patch_digest = (
                hashlib.sha256(full_patch.encode("utf-8")).hexdigest()
                if patch_available
                else None
            )
            remaining = max(_MAX_REVIEW_PATCH_CHARS - displayed_chars, 0)
            allowed = min(_MAX_PATCH_CHARS_PER_FILE, remaining)
            display_patch = full_patch[:allowed] if patch_available else ""
            truncated = patch_available and len(full_patch) > len(display_patch)
            if not patch_available or truncated:
                complete = False
            displayed_chars += len(display_patch)

            files.append(
                {
                    "path": safe_path,
                    "status": item.get("status"),
                    "additions": _optional_int(item.get("additions")),
                    "deletions": _optional_int(item.get("deletions")),
                    "changes": _optional_int(item.get("changes")),
                    "patch": display_patch,
                    "patch_sha256": patch_digest,
                    "patch_available": patch_available,
                    "patch_truncated": truncated,
                    "attention": _attention(
                        safe_path,
                        str(item.get("status") or ""),
                        _optional_int(item.get("changes")),
                        patch_available=patch_available,
                        truncated=truncated,
                    ),
                }
            )
        files.sort(key=lambda value: value["path"])
        return {
            "schema_version": APP4_REVIEW_SCHEMA_VERSION,
            "base_sha": base_sha,
            "head_sha": head_sha,
            "status": data.get("status"),
            "ahead_by": data.get("ahead_by"),
            "behind_by": data.get("behind_by"),
            "total_commits": data.get("total_commits"),
            "complete": complete and bool(files),
            "files": files,
        }


class App4TaskService(App3TaskService):
    """APP4 task service: exact diff review, immutable revisions and review-bound PRs."""

    def review_bundle(self, task_id: str) -> dict[str, Any]:
        view = self._persisted_view(task_id)
        preview = self._persistent_preview(view)
        commit = view.get("commit")
        if not isinstance(commit, Mapping):
            raise TaskExecutionError("task has no exact commit evidence to review")
        base_sha = commit.get("base_sha")
        head_sha = commit.get("head_sha")
        if not _full_sha(base_sha) or not _full_sha(head_sha):
            raise TaskExecutionError("task commit evidence is invalid")
        assert isinstance(base_sha, str)
        assert isinstance(head_sha, str)

        repository = str(preview["repository"])
        feature_branch = str(preview["feature_branch"])
        read_client = self._read_factory(repository)
        branch = read_client.branch_info(feature_branch)
        if branch.get("commit_sha") != head_sha:
            raise TaskExecutionError("task branch moved away from the exact review HEAD")

        method = getattr(read_client, "review_compare", None)
        if not callable(method):
            raise TaskExecutionError("read client does not support APP4 review evidence")
        review = method(base_sha, head_sha)
        if not isinstance(review, dict):
            raise TaskExecutionError("APP4 review evidence is invalid")
        if review.get("base_sha") != base_sha or review.get("head_sha") != head_sha:
            raise TaskExecutionError("APP4 review evidence is bound to the wrong commits")
        files = review.get("files")
        if not isinstance(files, list) or not files:
            raise TaskExecutionError("APP4 review evidence contains no files")

        digest = _review_digest(base_sha, head_sha, files)
        review["task_id"] = task_id
        review["repository"] = repository
        review["feature_branch"] = feature_branch
        review["review_digest"] = digest
        review["exact_head"] = True

        snapshot = {
            "schema_version": APP4_REVIEW_SCHEMA_VERSION,
            "base_sha": base_sha,
            "head_sha": head_sha,
            "review_digest": digest,
            "complete": review.get("complete") is True,
            "files": [_review_file_evidence(item) for item in files],
        }
        existing = view.get("review")
        if not isinstance(existing, Mapping) or existing.get("review_digest") != digest:
            self.store.append_evidence(task_id, "REVIEW_SNAPSHOT", snapshot)
        return review

    def acknowledge_review(self, task_id: str, review_digest: str) -> dict[str, Any]:
        if not _digest(review_digest):
            raise TaskExecutionError("review_digest must be a lowercase SHA-256 digest")
        view = self._persisted_view(task_id)
        review = view.get("review")
        if not isinstance(review, Mapping):
            raise TaskExecutionError("load the exact APP4 review before acknowledging it")
        if review.get("review_digest") != review_digest:
            raise TaskExecutionError("review acknowledgement does not match the latest exact review")
        if review.get("complete") is not True:
            raise TaskExecutionError("incomplete or truncated review evidence cannot be acknowledged")
        head_sha = review.get("head_sha")
        if not _full_sha(head_sha):
            raise TaskExecutionError("review HEAD is invalid")
        assert isinstance(head_sha, str)

        preview = self._persistent_preview(view)
        read_client = self._read_factory(str(preview["repository"]))
        branch = read_client.branch_info(str(preview["feature_branch"]))
        if branch.get("commit_sha") != head_sha:
            raise TaskExecutionError("task branch moved after review; acknowledgement is rejected")

        existing = view.get("review_ack")
        if not (
            isinstance(existing, Mapping)
            and existing.get("review_digest") == review_digest
            and existing.get("head_sha") == head_sha
        ):
            self.store.append_evidence(
                task_id,
                "REVIEW_ACKNOWLEDGED",
                {
                    "review_digest": review_digest,
                    "head_sha": head_sha,
                    "base_sha": review.get("base_sha"),
                },
            )
        return self.status(task_id)

    def create_revision(
        self,
        parent_task_id: str,
        instruction: str,
        *,
        mode: str,
    ) -> dict[str, Any]:
        normalized_mode = mode.strip().lower()
        if normalized_mode not in {"retry", "amend"}:
            raise TaskExecutionError("revision mode must be retry or amend")
        normalized_instruction = " ".join(instruction.split())
        if not normalized_instruction:
            raise TaskExecutionError("revision instruction must not be empty")
        if len(normalized_instruction) > _MAX_REVISION_INSTRUCTION_CHARS:
            raise TaskExecutionError("revision instruction exceeds configured limit")

        parent = self._persisted_view(parent_task_id)
        parent_preview = self._persistent_preview(parent)
        parent_stage = TaskStage(str(parent["stage"]))
        if normalized_mode == "retry" and parent_stage is not TaskStage.FAILED:
            raise TaskExecutionError("retry is reserved for a FAILED parent task")
        if normalized_mode == "amend" and not isinstance(parent.get("commit"), Mapping):
            raise TaskExecutionError("amend requires an exact parent commit to review")

        lineage = parent.get("lineage")
        children = lineage.get("children", []) if isinstance(lineage, Mapping) else []
        revision_number = len(children) + 1
        decorated = (
            f"{normalized_instruction}\n\n"
            "APP4 revision context: "
            f"mode={normalized_mode}; parent_task={parent_task_id}; revision={revision_number}. "
            "Treat parent task evidence as immutable. Make only the requested correction on the new "
            "bounded task branch; do not claim the parent was rewritten."
        )
        if len(decorated) > _MAX_REVISION_INSTRUCTION_CHARS:
            raise TaskExecutionError("revision instruction plus lineage context exceeds configured limit")

        child = self.preview(str(parent_preview["project"]), decorated)
        if child.task_id == parent_task_id:
            raise TaskExecutionError("revision must create a distinct child task identity")

        child_link = {
            "child_task_id": child.task_id,
            "mode": normalized_mode,
            "revision": revision_number,
            "parent_stage": parent_stage.value,
            "parent_head_sha": _parent_head(parent),
        }
        child_view = self._persisted_view(child.task_id)
        child_lineage = child_view.get("lineage")
        child_parent = child_lineage.get("parent") if isinstance(child_lineage, Mapping) else None
        if not isinstance(child_parent, Mapping):
            self.store.append_evidence(
                child.task_id,
                "LINEAGE_PARENT",
                {
                    "parent_task_id": parent_task_id,
                    "mode": normalized_mode,
                    "revision": revision_number,
                    "parent_head_sha": _parent_head(parent),
                },
            )
        if not any(
            isinstance(item, Mapping) and item.get("child_task_id") == child.task_id
            for item in children
        ):
            self.store.append_evidence(parent_task_id, "LINEAGE_CHILD_CREATED", child_link)

        return {
            "schema_version": APP4_REVIEW_SCHEMA_VERSION,
            "mode": normalized_mode,
            "revision": revision_number,
            "parent_task_id": parent_task_id,
            "child": child.as_dict(),
        }

    def open_pull_request(self, task_id: str) -> Mapping[str, Any]:
        view = self._persisted_view(task_id)
        review = view.get("review")
        acknowledgement = view.get("review_ack")
        commit = view.get("commit")
        if not isinstance(commit, Mapping):
            raise TaskExecutionError("task is missing exact commit evidence")
        head_sha = commit.get("head_sha")
        if not _full_sha(head_sha):
            raise TaskExecutionError("task head SHA is invalid")
        if not isinstance(review, Mapping) or review.get("head_sha") != head_sha:
            raise TaskExecutionError("exact APP4 review is required before opening a pull request")
        if review.get("complete") is not True:
            raise TaskExecutionError("complete APP4 review evidence is required before PR opening")
        if not isinstance(acknowledgement, Mapping):
            raise TaskExecutionError("human review acknowledgement is required before PR opening")
        if (
            acknowledgement.get("review_digest") != review.get("review_digest")
            or acknowledgement.get("head_sha") != head_sha
        ):
            raise TaskExecutionError("review acknowledgement is stale for the exact task HEAD")

        metadata = dict(super().open_pull_request(task_id))
        refreshed = self._persisted_view(task_id)
        pr_review = refreshed.get("pr_review")
        snapshot = {
            "task_head_sha": head_sha,
            "review_digest": review.get("review_digest"),
            "pr_number": metadata.get("number"),
            "pr_head_sha": metadata.get("head_sha"),
            "pr_base_sha": metadata.get("base_sha"),
            "draft": metadata.get("draft"),
            "mergeable": metadata.get("mergeable"),
            "exact_head_match": metadata.get("head_sha") in {None, head_sha},
        }
        if not isinstance(pr_review, Mapping) or pr_review != snapshot:
            self.store.append_evidence(task_id, "PR_REVIEW_SNAPSHOT", snapshot)
        return metadata

    def refresh_pr_review(self, task_id: str) -> dict[str, Any]:
        view = self._persisted_view(task_id)
        pull_request = view.get("pull_request")
        commit = view.get("commit")
        review_ack = view.get("review_ack")
        if not isinstance(pull_request, Mapping):
            raise TaskExecutionError("task does not have an opened pull request")
        if not isinstance(commit, Mapping) or not _full_sha(commit.get("head_sha")):
            raise TaskExecutionError("task commit evidence is invalid")
        number = pull_request.get("number")
        if not isinstance(number, int) or isinstance(number, bool):
            raise TaskExecutionError("pull request number is invalid")

        preview = self._persistent_preview(view)
        read_client = self._read_factory(str(preview["repository"]))
        reader = getattr(read_client, "pull_request", None)
        if not callable(reader):
            raise TaskExecutionError("read client cannot refresh pull request evidence")
        pr = reader(number)
        if not isinstance(pr, Mapping):
            raise TaskExecutionError("pull request evidence is invalid")
        head_sha = str(commit["head_sha"])
        if pr.get("head_ref") != preview["feature_branch"] or pr.get("head_sha") != head_sha:
            raise TaskExecutionError("pull request no longer matches the verified task HEAD")
        if pr.get("base_ref") != preview["base_branch"]:
            raise TaskExecutionError("pull request base no longer matches the task base")

        snapshot = {
            "task_head_sha": head_sha,
            "review_digest": (
                review_ack.get("review_digest") if isinstance(review_ack, Mapping) else None
            ),
            "pr_number": number,
            "pr_head_sha": pr.get("head_sha"),
            "pr_base_sha": pr.get("base_sha"),
            "state": pr.get("state"),
            "draft": pr.get("draft"),
            "mergeable": pr.get("mergeable"),
            "exact_head_match": True,
        }
        current = view.get("pr_review")
        if not isinstance(current, Mapping) or current != snapshot:
            self.store.append_evidence(task_id, "PR_REVIEW_SNAPSHOT", snapshot)
        return self.status(task_id)

    def status(self, task_id: str) -> dict[str, Any]:
        result = super().status(task_id)
        view = self._persisted_view(task_id)
        review = view.get("review")
        acknowledgement = view.get("review_ack")
        result.update(
            {
                "review": review,
                "review_ack": acknowledgement,
                "lineage": view.get("lineage"),
                "pr_review": view.get("pr_review"),
                "review_ready_for_pr": _review_ready(review, acknowledgement),
            }
        )
        return result

    def _default_read_factory(self, repository: str) -> App4GitHubReadClient:
        return App4GitHubReadClient(
            GitHubReadConfig(
                repository=repository,
                token_env=self.config.github_token_env,
                api_base=self.config.github_api_base,
            )
        )


def _review_digest(base_sha: str, head_sha: str, files: list[Any]) -> str:
    projected = []
    for item in files:
        if not isinstance(item, Mapping):
            continue
        projected.append(_review_file_evidence(item))
    material = {
        "schema_version": APP4_REVIEW_SCHEMA_VERSION,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "files": projected,
    }
    encoded = json.dumps(
        material,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _review_file_evidence(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "path": item.get("path"),
        "status": item.get("status"),
        "additions": item.get("additions"),
        "deletions": item.get("deletions"),
        "changes": item.get("changes"),
        "patch_sha256": item.get("patch_sha256"),
        "patch_available": item.get("patch_available") is True,
        "patch_truncated": item.get("patch_truncated") is True,
        "attention": item.get("attention"),
    }


def _attention(
    path: str,
    status: str,
    changes: int | None,
    *,
    patch_available: bool,
    truncated: bool,
) -> str:
    lowered = path.lower()
    if not patch_available or truncated:
        return "incomplete"
    if status in {"removed", "renamed"}:
        return "high"
    if lowered.startswith(".github/workflows/"):
        return "high"
    if lowered in {"pyproject.toml", "package.json", "package-lock.json", "requirements.txt"}:
        return "high"
    if isinstance(changes, int) and changes >= 400:
        return "high"
    if isinstance(changes, int) and changes >= 150:
        return "medium"
    return "normal"


def _review_ready(review: Any, acknowledgement: Any) -> bool:
    return bool(
        isinstance(review, Mapping)
        and review.get("complete") is True
        and isinstance(acknowledgement, Mapping)
        and acknowledgement.get("review_digest") == review.get("review_digest")
        and acknowledgement.get("head_sha") == review.get("head_sha")
    )


def _digest(value: Any) -> bool:
    return isinstance(value, str) and len(value) == _REVIEW_DIGEST and all(
        char in "0123456789abcdef" for char in value
    )


def _parent_head(view: Mapping[str, Any]) -> str | None:
    commit = view.get("commit")
    if isinstance(commit, Mapping) and _full_sha(commit.get("head_sha")):
        return str(commit["head_sha"])
    return None


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
