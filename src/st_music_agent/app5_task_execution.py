from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlencode

from .app4_task_execution import App4GitHubReadClient, App4TaskService
from .github_read import GitHubReadConfig, GitHubReadError
from .music_adapters import MusicXmlTabEvidenceAdapter, ScoreRestoreEvidenceAdapter
from .music_adapters_extended import ScoreEditorEvidenceAdapter, ScoreFollowingEvidenceAdapter
from .music_evidence import MusicEvidenceError, MusicEvidenceSnapshot
from .task_execution import TaskExecutionError
from .task_state import ValidatorResult, ValidatorStatus
from .transport import JsonRequest

APP5_EVIDENCE_SCHEMA_VERSION = "1.0.0"
_MAX_REVIEWS = 50
_MAX_REVIEW_COMMENTS = 100
_MAX_ISSUE_COMMENTS = 50
_MAX_COMMENT_CHARS = 800

_PROJECT_VALIDATOR_NAMES = {
    "score_restore": "score_restore_current_truth",
    "musicxml_guitar_tab": "tab_capability_contract",
    "score_editor": "score_editor_release_boundary",
    "real_time_score_following": "score_following_research_boundary",
}


class App5GitHubReadClient(App4GitHubReadClient):
    """APP5 read adapter for bounded PR review/comment collaboration evidence."""

    def pull_request_collaboration(self, number: int) -> dict[str, Any]:
        if number < 1:
            raise ValueError("pull request number must be >= 1")
        reviews = self._get_array(f"/pulls/{number}/reviews", {"per_page": _MAX_REVIEWS})
        review_comments = self._get_array(
            f"/pulls/{number}/comments",
            {"per_page": _MAX_REVIEW_COMMENTS},
        )
        issue_comments = self._get_array(
            f"/issues/{number}/comments",
            {"per_page": _MAX_ISSUE_COMMENTS},
        )
        return {
            "schema_version": APP5_EVIDENCE_SCHEMA_VERSION,
            "pull_request": number,
            "reviews": [_review_projection(item) for item in reviews],
            "threads": _thread_projection(review_comments),
            "conversation": [_issue_comment_projection(item) for item in issue_comments],
            "resolution_state_available": False,
        }

    def _get_array(
        self,
        route: str,
        query: Mapping[str, str | int] | None = None,
    ) -> list[dict[str, Any]]:
        suffix = f"?{urlencode(query)}" if query else ""
        url = (
            f"{self.config.api_base.rstrip('/')}/repos/"
            f"{self.config.repository}{route}{suffix}"
        )
        response = self.transport.request(
            JsonRequest(
                method="GET",
                url=url,
                headers=self._headers(),
                timeout_seconds=self.config.timeout_seconds,
            )
        )
        if response.status_code != 200:
            raise GitHubReadError(f"GitHub returned unexpected status {response.status_code}")
        if not isinstance(response.payload, list):
            raise GitHubReadError("GitHub collaboration response is not a JSON array")
        return [dict(item) for item in response.payload if isinstance(item, Mapping)]


class App5TaskService(App4TaskService):
    """APP5 service with exact-head project validators and bounded PR collaboration evidence."""

    def _validators(
        self,
        preview: Mapping[str, Any],
        commit: Mapping[str, Any],
        head_sha: str,
        *,
        exact_head: bool,
    ) -> list[ValidatorResult]:
        results = super()._validators(preview, commit, head_sha, exact_head=exact_head)
        project = str(preview["project"])
        results.append(self._project_validator(project, head_sha, preview))
        return results

    def _project_validator(
        self,
        project: str,
        head_sha: str,
        preview: Mapping[str, Any],
    ) -> ValidatorResult:
        name = _PROJECT_VALIDATOR_NAMES.get(project)
        if name is None:
            return ValidatorResult(
                name=f"project_contract:{project}",
                status=ValidatorStatus.UNAVAILABLE,
                evidence_reference=f"project:{project}@{head_sha}",
                commit_sha=head_sha,
                message="no APP5 project-specific validator is registered",
            )
        read_client = self._read_factory(str(preview["repository"]))
        try:
            snapshot = _collect_project_snapshot(project, read_client, head_sha)
            failures = _project_invariant_failures(project, snapshot)
            if any(source.ref != head_sha for source in snapshot.sources):
                failures.append("project evidence is not bound to the exact task HEAD")
            status = ValidatorStatus.FAIL if failures else ValidatorStatus.PASS
            message = (
                "; ".join(failures)[:500]
                if failures
                else f"{snapshot.state}: exact-head project contract passed ({len(snapshot.sources)} source(s))"
            )
            return ValidatorResult(
                name=name,
                status=status,
                evidence_reference=f"music-evidence:{project}@{head_sha}",
                commit_sha=head_sha,
                message=message,
            )
        except GitHubReadError as exc:
            return ValidatorResult(
                name=name,
                status=ValidatorStatus.UNAVAILABLE,
                evidence_reference=f"music-evidence:{project}@{head_sha}",
                commit_sha=head_sha,
                message=f"project evidence unavailable: {_bounded(exc)}",
            )
        except (MusicEvidenceError, TypeError, ValueError) as exc:
            return ValidatorResult(
                name=name,
                status=ValidatorStatus.FAIL,
                evidence_reference=f"music-evidence:{project}@{head_sha}",
                commit_sha=head_sha,
                message=f"project contract invalid: {_bounded(exc)}",
            )

    def refresh_pr_collaboration(self, task_id: str) -> dict[str, Any]:
        self.refresh_pr_review(task_id)
        view = self._persisted_view(task_id)
        pull_request = view.get("pull_request")
        commit = view.get("commit")
        if not isinstance(pull_request, Mapping):
            raise TaskExecutionError("task does not have an opened pull request")
        if not isinstance(commit, Mapping):
            raise TaskExecutionError("task is missing exact commit evidence")
        number = pull_request.get("number")
        head_sha = commit.get("head_sha")
        if not isinstance(number, int) or isinstance(number, bool):
            raise TaskExecutionError("pull request number is invalid")
        if not isinstance(head_sha, str) or len(head_sha) != 40:
            raise TaskExecutionError("task head SHA is invalid")

        preview = self._persistent_preview(view)
        read_client = self._read_factory(str(preview["repository"]))
        method = getattr(read_client, "pull_request_collaboration", None)
        if not callable(method):
            raise TaskExecutionError("read client does not support APP5 PR collaboration evidence")
        evidence = method(number)
        if not isinstance(evidence, Mapping):
            raise TaskExecutionError("PR collaboration evidence is invalid")
        snapshot = _collaboration_snapshot(number, head_sha, evidence)
        current = view.get("pr_collaboration")
        if not isinstance(current, Mapping) or current != snapshot:
            self.store.append_evidence(task_id, "PR_COLLABORATION_SNAPSHOT", snapshot)
        return self.status(task_id)

    def status(self, task_id: str) -> dict[str, Any]:
        result = super().status(task_id)
        view = self._persisted_view(task_id)
        project_validation = None
        for item in result.get("validators", []):
            if isinstance(item, Mapping) and item.get("name") in _PROJECT_VALIDATOR_NAMES.values():
                project_validation = dict(item)
                break
        result.update(
            {
                "project_validation": project_validation,
                "pr_collaboration": view.get("pr_collaboration"),
                "merge_authorized": False,
                "production_actions_authorized": False,
            }
        )
        return result

    def _default_read_factory(self, repository: str) -> App5GitHubReadClient:
        return App5GitHubReadClient(
            GitHubReadConfig(
                repository=repository,
                token_env=self.config.github_token_env,
                api_base=self.config.github_api_base,
            )
        )


def _collect_project_snapshot(project: str, read_client: Any, head_sha: str) -> MusicEvidenceSnapshot:
    if project == "score_restore":
        return ScoreRestoreEvidenceAdapter(read_client).collect(head_sha)
    if project == "musicxml_guitar_tab":
        return MusicXmlTabEvidenceAdapter(read_client).collect(head_sha)
    if project == "score_editor":
        return ScoreEditorEvidenceAdapter(read_client).collect(head_sha)
    if project == "real_time_score_following":
        return ScoreFollowingEvidenceAdapter(read_client).collect(head_sha)
    raise MusicEvidenceError(f"unsupported APP5 project: {project}")


def _project_invariant_failures(project: str, snapshot: MusicEvidenceSnapshot) -> list[str]:
    claims = snapshot.claims
    checks: dict[str, tuple[tuple[str, Any], ...]] = {
        "score_restore": (
            ("automatic_production_promotion_forbidden", True),
            ("omr_correctness_implied", False),
            ("musical_truth_implied", False),
        ),
        "musicxml_guitar_tab": (
            ("review_required_is_global_lock", False),
            ("canonical_tab_requires_pass", True),
            ("export_requires_pass", True),
            ("review_required_playback_can_be_approximate", True),
        ),
        "score_editor": (
            ("planned_capability_is_production_capability", False),
            ("standalone_release_gate_passed", False),
            ("seslitab_cutover_authorized", False),
        ),
        "real_time_score_following": (
            ("research_evidence_is_production_authority", False),
            ("research_evidence_is_pedagogical_authority", False),
            ("acoustic_mono_mixture_authority", False),
        ),
    }
    failures: list[str] = []
    for key, expected in checks.get(project, ()):
        if claims.get(key) != expected:
            failures.append(f"{key} must remain {expected!r}")
    return failures


def _collaboration_snapshot(
    number: int,
    head_sha: str,
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    reviews = [dict(item) for item in evidence.get("reviews", []) if isinstance(item, Mapping)]
    threads = [dict(item) for item in evidence.get("threads", []) if isinstance(item, Mapping)]
    conversation = [
        dict(item) for item in evidence.get("conversation", []) if isinstance(item, Mapping)
    ]
    latest: dict[str, dict[str, Any]] = {}
    stale = 0
    for review in sorted(reviews, key=lambda item: str(item.get("submitted_at") or "")):
        login = str(review.get("reviewer") or "unknown")
        if review.get("commit_id") == head_sha:
            latest[login] = review
        else:
            stale += 1
    approvals = sorted(
        login for login, review in latest.items() if review.get("state") == "APPROVED"
    )
    changes_requested = sorted(
        login for login, review in latest.items() if review.get("state") == "CHANGES_REQUESTED"
    )
    exact_threads = sum(1 for thread in threads if thread.get("commit_id") == head_sha)
    return {
        "schema_version": APP5_EVIDENCE_SCHEMA_VERSION,
        "pull_request": number,
        "task_head_sha": head_sha,
        "exact_head_approvals": approvals,
        "exact_head_changes_requested": changes_requested,
        "stale_review_count": stale,
        "review_count": len(reviews),
        "thread_count": len(threads),
        "exact_head_thread_count": exact_threads,
        "conversation_comment_count": len(conversation),
        "resolution_state_available": evidence.get("resolution_state_available") is True,
        "reviews": reviews,
        "threads": threads,
        "conversation": conversation,
        "merge_authorized": False,
    }


def _review_projection(item: Mapping[str, Any]) -> dict[str, Any]:
    user = item.get("user")
    return {
        "id": item.get("id"),
        "reviewer": user.get("login") if isinstance(user, Mapping) else None,
        "state": item.get("state"),
        "commit_id": item.get("commit_id"),
        "submitted_at": item.get("submitted_at"),
        "body": _text(item.get("body")),
    }


def _thread_projection(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[int, list[dict[str, Any]]] = {}
    roots: dict[int, dict[str, Any]] = {}
    for item in items:
        item_id = item.get("id")
        if not isinstance(item_id, int) or isinstance(item_id, bool):
            continue
        reply_to = item.get("in_reply_to_id")
        root_id = reply_to if isinstance(reply_to, int) else item_id
        groups.setdefault(root_id, []).append(item)
        if root_id == item_id:
            roots[root_id] = item
    output: list[dict[str, Any]] = []
    for root_id in sorted(groups):
        comments = groups[root_id]
        root = roots.get(root_id, comments[0])
        output.append(
            {
                "root_comment_id": root_id,
                "path": root.get("path"),
                "line": root.get("line"),
                "side": root.get("side"),
                "commit_id": root.get("commit_id") or root.get("original_commit_id"),
                "comment_count": len(comments),
                "resolution_state": "unavailable",
                "comments": [_review_comment_projection(item) for item in comments],
            }
        )
    return output


def _review_comment_projection(item: Mapping[str, Any]) -> dict[str, Any]:
    user = item.get("user")
    return {
        "id": item.get("id"),
        "reviewer": user.get("login") if isinstance(user, Mapping) else None,
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "body": _text(item.get("body")),
    }


def _issue_comment_projection(item: Mapping[str, Any]) -> dict[str, Any]:
    user = item.get("user")
    return {
        "id": item.get("id"),
        "author": user.get("login") if isinstance(user, Mapping) else None,
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "body": _text(item.get("body")),
    }


def _text(value: Any) -> str:
    return " ".join(value.split())[:_MAX_COMMENT_CHARS] if isinstance(value, str) else ""


def _bounded(exc: Exception) -> str:
    return (" ".join(str(exc).split()) or exc.__class__.__name__)[:300]
