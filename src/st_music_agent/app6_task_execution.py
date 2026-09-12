from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from .app5_task_execution import App5GitHubReadClient, App5TaskService
from .github_read import GitHubReadConfig, GitHubReadError
from .task_execution import TaskExecutionError
from .transport import JsonRequest

APP6_EVIDENCE_SCHEMA_VERSION = "1.0.0"
VALIDATOR_FRESHNESS_SECONDS = 900
_MAX_GRAPHQL_THREADS = 100
_MAX_GRAPHQL_THREAD_COMMENTS = 20
_MAX_AUDIT_EVENTS = 500


class App6GitHubReadClient(App5GitHubReadClient):
    """APP6 read adapter with trustworthy GitHub review-thread resolution when available."""

    def pull_request_collaboration(self, number: int) -> dict[str, Any]:
        evidence = super().pull_request_collaboration(number)
        try:
            resolution = self._graphql_review_threads(number)
        except (GitHubReadError, RuntimeError, TypeError, ValueError) as exc:
            evidence["resolution_state_available"] = False
            evidence["resolution_source"] = "unavailable"
            evidence["resolution_error"] = _bounded(exc)
            return evidence

        by_root = {
            item["root_comment_id"]: item
            for item in resolution["threads"]
            if isinstance(item.get("root_comment_id"), int)
        }
        for thread in evidence.get("threads", []):
            if not isinstance(thread, dict):
                continue
            resolved = by_root.get(thread.get("root_comment_id"))
            if resolved is None:
                continue
            thread["resolution_state"] = (
                "resolved" if resolved["is_resolved"] else "unresolved"
            )
            thread["resolution_source"] = "github_graphql"
            thread["graphql_thread_id"] = resolved["thread_id"]
            thread["is_outdated"] = resolved["is_outdated"]

        evidence["resolution_state_available"] = resolution["complete"]
        evidence["resolution_source"] = "github_graphql"
        evidence["resolution_truncated"] = not resolution["complete"]
        return evidence

    def _graphql_review_threads(self, number: int) -> dict[str, Any]:
        if number < 1:
            raise ValueError("pull request number must be >= 1")
        if self.config.api_base.rstrip("/") != "https://api.github.com":
            raise GitHubReadError("APP6 GraphQL resolution currently requires api.github.com")
        owner, name = self.config.repository.split("/", 1)
        query = """
query($owner:String!,$name:String!,$number:Int!){
  repository(owner:$owner,name:$name){
    pullRequest(number:$number){
      reviewThreads(first:100){
        nodes{
          id
          isResolved
          isOutdated
          path
          line
          comments(first:20){
            totalCount
            nodes{databaseId commit{oid}}
          }
        }
        pageInfo{hasNextPage}
      }
    }
  }
}
""".strip()
        response = self.transport.request(
            JsonRequest(
                method="POST",
                url="https://api.github.com/graphql",
                payload={
                    "query": query,
                    "variables": {"owner": owner, "name": name, "number": number},
                },
                headers=self._headers(),
                timeout_seconds=self.config.timeout_seconds,
            )
        )
        if response.status_code != 200 or not isinstance(response.payload, Mapping):
            raise GitHubReadError("GitHub GraphQL review-thread request failed")
        if response.payload.get("errors"):
            raise GitHubReadError("GitHub GraphQL review-thread response contains errors")
        data = response.payload.get("data")
        repository = data.get("repository") if isinstance(data, Mapping) else None
        pull_request = repository.get("pullRequest") if isinstance(repository, Mapping) else None
        threads = pull_request.get("reviewThreads") if isinstance(pull_request, Mapping) else None
        if not isinstance(threads, Mapping):
            raise GitHubReadError("GitHub GraphQL review-thread data is missing")
        nodes = threads.get("nodes")
        page_info = threads.get("pageInfo")
        if not isinstance(nodes, list) or not isinstance(page_info, Mapping):
            raise GitHubReadError("GitHub GraphQL review-thread page is invalid")
        if len(nodes) > _MAX_GRAPHQL_THREADS:
            raise GitHubReadError("GitHub GraphQL review-thread response exceeds limit")

        projected: list[dict[str, Any]] = []
        comment_truncated = False
        for node in nodes:
            if not isinstance(node, Mapping):
                continue
            comments = node.get("comments")
            comment_nodes = comments.get("nodes") if isinstance(comments, Mapping) else None
            total_count = comments.get("totalCount") if isinstance(comments, Mapping) else None
            if not isinstance(comment_nodes, list):
                continue
            if isinstance(total_count, int) and total_count > _MAX_GRAPHQL_THREAD_COMMENTS:
                comment_truncated = True
            root_id = None
            root_commit = None
            for comment in comment_nodes:
                if not isinstance(comment, Mapping):
                    continue
                database_id = comment.get("databaseId")
                if isinstance(database_id, int) and not isinstance(database_id, bool):
                    root_id = database_id
                    commit = comment.get("commit")
                    root_commit = commit.get("oid") if isinstance(commit, Mapping) else None
                    break
            projected.append(
                {
                    "thread_id": node.get("id"),
                    "root_comment_id": root_id,
                    "root_commit_id": root_commit,
                    "is_resolved": node.get("isResolved") is True,
                    "is_outdated": node.get("isOutdated") is True,
                    "path": node.get("path"),
                    "line": node.get("line"),
                }
            )
        return {
            "threads": projected,
            "complete": page_info.get("hasNextPage") is not True and not comment_truncated,
        }


class App6TaskService(App5TaskService):
    """APP6 service with validator freshness gates and bounded audit export."""

    def refresh_evidence(self, task_id: str) -> dict[str, Any]:
        super().refresh_evidence(task_id)
        self._record_validator_health(task_id)
        return self.status(task_id)

    def open_pull_request(self, task_id: str) -> Mapping[str, Any]:
        health = self.status(task_id).get("validator_health")
        if not isinstance(health, Mapping) or health.get("effective_state") != "FRESH_HEALTHY":
            raise TaskExecutionError(
                "fresh healthy APP6 validator evidence is required before opening a pull request"
            )
        return super().open_pull_request(task_id)

    def status(self, task_id: str) -> dict[str, Any]:
        result = super().status(task_id)
        view = self._persisted_view(task_id)
        result["validator_health"] = _effective_health(
            view.get("validator_health"),
            now=datetime.now(UTC),
        )
        result["audit_export_available"] = True
        result["merge_authorized"] = False
        result["production_actions_authorized"] = False
        return result

    def audit_bundle(self, task_id: str) -> dict[str, Any]:
        view = self._persisted_view(task_id)
        events = list(self.store.task_events(task_id))
        if not events:
            raise TaskExecutionError("task has no audit evidence")
        preview = view.get("preview") if isinstance(view.get("preview"), Mapping) else {}
        commit = view.get("commit") if isinstance(view.get("commit"), Mapping) else {}
        collaboration = (
            view.get("pr_collaboration")
            if isinstance(view.get("pr_collaboration"), Mapping)
            else {}
        )
        validators = [
            dict(item) for item in view.get("validators", []) if isinstance(item, Mapping)
        ]
        event_projection = [
            {
                "sequence": item.get("sequence"),
                "recorded_at": item.get("recorded_at"),
                "event": item.get("event"),
                "hash": item.get("hash"),
                "previous_hash": item.get("previous_hash"),
            }
            for item in events[-_MAX_AUDIT_EVENTS:]
        ]
        bundle: dict[str, Any] = {
            "schema_version": APP6_EVIDENCE_SCHEMA_VERSION,
            "task_id": task_id,
            "stage": view.get("stage"),
            "outcome": view.get("outcome"),
            "project": preview.get("project"),
            "repository": preview.get("repository"),
            "base_branch": preview.get("base_branch"),
            "base_sha": preview.get("base_sha"),
            "feature_branch": preview.get("feature_branch"),
            "instruction_fingerprint": preview.get("instruction_fingerprint"),
            "head_sha": commit.get("head_sha"),
            "changed_paths": [
                item.get("path")
                for item in commit.get("changed_files", [])
                if isinstance(item, Mapping) and isinstance(item.get("path"), str)
            ],
            "ci": view.get("ci"),
            "validators": validators,
            "validator_health": _effective_health(
                view.get("validator_health"),
                now=datetime.now(UTC),
            ),
            "review": _review_audit(view.get("review"), view.get("review_ack")),
            "pull_request": view.get("pull_request"),
            "pr_review": view.get("pr_review"),
            "pr_collaboration": {
                "exact_head_approvals": collaboration.get("exact_head_approvals", []),
                "exact_head_changes_requested": collaboration.get(
                    "exact_head_changes_requested", []
                ),
                "stale_review_count": collaboration.get("stale_review_count", 0),
                "thread_count": collaboration.get("thread_count", 0),
                "exact_head_thread_count": collaboration.get("exact_head_thread_count", 0),
                "resolution_state_available": collaboration.get(
                    "resolution_state_available", False
                ),
                "merge_authorized": False,
            },
            "lineage": view.get("lineage"),
            "journal": {
                "event_count": len(events),
                "exported_event_count": len(event_projection),
                "truncated": len(events) > _MAX_AUDIT_EVENTS,
                "anchor_sequence": events[-1].get("sequence"),
                "anchor_hash": events[-1].get("hash"),
                "events": event_projection,
            },
            "merge_authorized": False,
            "production_actions_authorized": False,
        }
        encoded = json.dumps(
            bundle,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        bundle["audit_sha256"] = hashlib.sha256(encoded).hexdigest()
        return bundle

    def _record_validator_health(self, task_id: str) -> None:
        events = self.store.task_events(task_id)
        validator_event = next(
            (item for item in reversed(events) if item.get("event") == "VALIDATOR_SNAPSHOT"),
            None,
        )
        if not isinstance(validator_event, Mapping):
            return
        existing = next(
            (item for item in reversed(events) if item.get("event") == "VALIDATOR_HEALTH_SNAPSHOT"),
            None,
        )
        if (
            isinstance(existing, Mapping)
            and isinstance(existing.get("payload"), Mapping)
            and existing["payload"].get("source_sequence") == validator_event.get("sequence")
        ):
            return
        payload = validator_event.get("payload")
        if not isinstance(payload, Mapping):
            return
        results = [item for item in payload.get("results", []) if isinstance(item, Mapping)]
        head_sha = payload.get("head_sha")
        statuses = [item.get("status") for item in results]
        exact = bool(results) and all(item.get("commit_sha") == head_sha for item in results)
        if not exact or "FAIL" in statuses:
            state = "UNHEALTHY"
        elif "UNAVAILABLE" in statuses or not results:
            state = "DEGRADED"
        elif all(value == "PASS" for value in statuses):
            state = "HEALTHY"
        else:
            state = "DEGRADED"
        checked_at = _parse_time(validator_event.get("recorded_at"))
        snapshot = {
            "schema_version": APP6_EVIDENCE_SCHEMA_VERSION,
            "head_sha": head_sha,
            "state": state,
            "checked_at": checked_at.isoformat(),
            "expires_at": (
                checked_at + timedelta(seconds=VALIDATOR_FRESHNESS_SECONDS)
            ).isoformat(),
            "freshness_seconds": VALIDATOR_FRESHNESS_SECONDS,
            "source_sequence": validator_event.get("sequence"),
            "source_hash": validator_event.get("hash"),
            "validator_names": [item.get("name") for item in results],
        }
        self.store.append_evidence(task_id, "VALIDATOR_HEALTH_SNAPSHOT", snapshot)

    def _default_read_factory(self, repository: str) -> App6GitHubReadClient:
        return App6GitHubReadClient(
            GitHubReadConfig(
                repository=repository,
                token_env=self.config.github_token_env,
                api_base=self.config.github_api_base,
            )
        )


def _effective_health(value: Any, *, now: datetime) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {
            "state": "MISSING",
            "fresh": False,
            "effective_state": "MISSING",
            "refresh_required": True,
        }
    expires_at = _parse_time(value.get("expires_at"))
    fresh = now <= expires_at
    state = str(value.get("state") or "MISSING")
    effective = f"FRESH_{state}" if fresh else f"STALE_{state}"
    result = dict(value)
    result.update(
        {
            "fresh": fresh,
            "effective_state": effective,
            "refresh_required": not fresh or state != "HEALTHY",
        }
    )
    return result


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise TypeError("evidence timestamp is missing")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("evidence timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _review_audit(review: Any, acknowledgement: Any) -> dict[str, Any]:
    review_map = review if isinstance(review, Mapping) else {}
    ack_map = acknowledgement if isinstance(acknowledgement, Mapping) else {}
    return {
        "base_sha": review_map.get("base_sha"),
        "head_sha": review_map.get("head_sha"),
        "review_digest": review_map.get("review_digest"),
        "complete": review_map.get("complete") is True,
        "acknowledged": (
            ack_map.get("review_digest") == review_map.get("review_digest")
            and ack_map.get("head_sha") == review_map.get("head_sha")
            and bool(review_map)
        ),
    }


def _bounded(exc: Exception) -> str:
    return (" ".join(str(exc).split()) or exc.__class__.__name__)[:300]
