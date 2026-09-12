from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from .agent_tools import ToolRegistry
from .app8_reliability import (
    ClaimSource,
    EvidenceVerdict,
    GateReport,
    IndependentDisagreementGate,
    VerificationClaim,
)
from .app8_supervision import (
    AgentRole,
    DependencyGraph,
    MutationClass,
    NodeOutcome,
    SubtaskNode,
)
from .contracts import ModelProfile
from .task_state import TaskOutcome
from .tool_loop import ToolCallingClient, ToolLoopBudget, ToolLoopRunner

APP8_EXECUTION_SCHEMA_VERSION = "1.0.0"
APP8_EXECUTION_POLICY_VERSION = "2026-09-12.app8c.v1"

_SHA = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PROTECTED_BRANCHES = frozenset({"main", "master"})
_MAX_SUMMARY_CHARS = 4000
_MAX_TREE_FILES = 2000


class App8ExecutionError(RuntimeError):
    pass


class SpecialistOutputError(App8ExecutionError):
    pass


class SpecialistReadClient(Protocol):
    def branch_info(self, branch: str) -> Mapping[str, Any]: ...

    def repository_tree(self, ref: str = "main") -> Mapping[str, Any]: ...

    def read_file(self, path: str, ref: str | None = None) -> Mapping[str, Any]: ...


class GuardedImplementationService(Protocol):
    """Narrow APP8C view of APP7; intentionally excludes PR/merge methods."""

    def preview(self, project: str, instruction: str) -> Any: ...

    def run(self, task_id: str) -> Any: ...

    def refresh_evidence(self, task_id: str) -> Mapping[str, Any]: ...

    def status(self, task_id: str) -> Mapping[str, Any]: ...

    def verify_current_audit(self, task_id: str) -> Mapping[str, Any]: ...


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _field(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _require_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise App8ExecutionError(f"{label} must be a full lowercase 40-hex SHA")
    return value


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise App8ExecutionError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _bounded_text(value: Any, label: str, *, limit: int = _MAX_SUMMARY_CHARS) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SpecialistOutputError(f"{label} must be non-empty text")
    text = value.strip()
    if len(text) > limit:
        raise SpecialistOutputError(f"{label} exceeds the configured character limit")
    return text


class ExactCommitReadToolset:
    """Model-facing read tools bound host-side to one immutable commit SHA."""

    def __init__(
        self,
        client: SpecialistReadClient,
        *,
        branch: str,
        expected_sha: str,
    ) -> None:
        self.client = client
        self.branch = branch
        self.expected_sha = _require_sha(expected_sha, "expected_sha")
        self._files = self._capture_tree()
        self._paths = frozenset(item["path"] for item in self._files)

    def _capture_tree(self) -> tuple[dict[str, Any], ...]:
        branch = self.client.branch_info(self.branch)
        if branch.get("commit_sha") != self.expected_sha:
            raise App8ExecutionError("branch does not resolve to the required exact commit SHA")
        tree = self.client.repository_tree(self.branch)
        if tree.get("commit_sha") != self.expected_sha:
            raise App8ExecutionError("repository tree is not bound to the required exact commit SHA")
        raw_files = tree.get("files")
        if not isinstance(raw_files, list):
            raise App8ExecutionError("repository tree file projection is invalid")
        if len(raw_files) > _MAX_TREE_FILES:
            raise App8ExecutionError("repository tree exceeds the APP8C file limit")
        files: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in raw_files:
            if not isinstance(item, Mapping):
                raise App8ExecutionError("repository tree contains an invalid file entry")
            path = item.get("path")
            sha = item.get("sha")
            if not isinstance(path, str) or not path.strip():
                raise App8ExecutionError("repository tree contains an invalid path")
            if path in seen:
                raise App8ExecutionError("repository tree contains a duplicate path")
            if not isinstance(sha, str) or not sha.strip():
                raise App8ExecutionError("repository tree contains an invalid blob identity")
            seen.add(path)
            files.append(
                {
                    "path": path,
                    "sha": sha,
                    "size": item.get("size") if isinstance(item.get("size"), int) else None,
                }
            )
        files.sort(key=lambda item: item["path"])
        return tuple(files)

    def register_into(self, registry: ToolRegistry) -> None:
        registry.register(
            "task.list_files",
            self._list_files,
            description="List the captured files for this task's immutable exact commit.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
        )
        registry.register(
            "task.read_file",
            self._read_file,
            description="Read one file from this task's immutable exact commit.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        )

    def _list_files(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        if arguments:
            raise ValueError("task.list_files accepts no arguments")
        return {
            "commit_sha": self.expected_sha,
            "files": [dict(item) for item in self._files],
        }

    def _read_file(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        if set(arguments) != {"path"}:
            raise ValueError("task.read_file accepts only path")
        path = arguments.get("path")
        if not isinstance(path, str) or not path.strip():
            raise TypeError("path must be non-empty text")
        if path not in self._paths:
            raise ValueError("path is outside the captured exact-commit tree")
        value = self.client.read_file(path, self.expected_sha)
        if not isinstance(value, Mapping):
            raise App8ExecutionError("exact file read returned an invalid payload")
        projected = dict(value)
        projected["commit_sha"] = self.expected_sha
        return projected


@dataclass(frozen=True, slots=True)
class SpecialistExecutionRecord:
    node_id: str
    role: AgentRole
    repository: str
    exact_sha: str
    model_name: str
    model_provider: str
    verdict: NodeOutcome
    summary: str
    turns: int
    tool_calls: int
    output_sha256: str
    evidence_refs: tuple[str, ...]
    instruction_fingerprint: str
    subject_artifact_sha256: str | None = None
    execution_authorized: bool = False
    repository_mutation_authorized: bool = False
    merge_authorized: bool = False
    production_actions_authorized: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": APP8_EXECUTION_SCHEMA_VERSION,
            "policy_version": APP8_EXECUTION_POLICY_VERSION,
            "node_id": self.node_id,
            "role": self.role.value,
            "repository": self.repository,
            "exact_sha": self.exact_sha,
            "model_name": self.model_name,
            "model_provider": self.model_provider,
            "verdict": self.verdict.value,
            "summary": self.summary,
            "turns": self.turns,
            "tool_calls": self.tool_calls,
            "output_sha256": self.output_sha256,
            "evidence_refs": list(self.evidence_refs),
            "instruction_fingerprint": self.instruction_fingerprint,
            "subject_artifact_sha256": self.subject_artifact_sha256,
            "execution_authorized": False,
            "repository_mutation_authorized": False,
            "merge_authorized": False,
            "production_actions_authorized": False,
        }

    def to_verification_claim(self) -> VerificationClaim:
        if self.role not in {AgentRole.VALIDATION, AgentRole.CRITIC}:
            raise App8ExecutionError("only validation/critic specialist results can become claims")
        artifact = _require_sha256(
            self.subject_artifact_sha256,
            "subject_artifact_sha256",
        )
        verdict = {
            NodeOutcome.PASS: EvidenceVerdict.PASS,
            NodeOutcome.FAIL: EvidenceVerdict.FAIL,
            NodeOutcome.ABSTAIN: EvidenceVerdict.ABSTAIN,
            NodeOutcome.REVIEW_REQUIRED: EvidenceVerdict.REVIEW_REQUIRED,
        }[self.verdict]
        return VerificationClaim(
            claim_id=f"app8c:{self.output_sha256[:24]}",
            role=self.role,
            source=ClaimSource.MODEL,
            verdict=verdict,
            repository=self.repository,
            commit_sha=self.exact_sha,
            artifact_sha256=artifact,
            evidence_refs=self.evidence_refs,
            model_name=self.model_name,
            model_provider=self.model_provider,
            instruction_fingerprint=self.instruction_fingerprint,
        )


class ReadOnlySpecialistRunner:
    """Execute one evidence/validation/critic node with exact-SHA read-only tools."""

    _ALLOWED_ROLES = frozenset(
        {AgentRole.EVIDENCE, AgentRole.VALIDATION, AgentRole.CRITIC}
    )

    def __init__(
        self,
        *,
        node: SubtaskNode,
        exact_sha: str,
        read_client: SpecialistReadClient,
        profile: ModelProfile,
        provider_client: ToolCallingClient,
        subject_artifact_sha256: str | None = None,
    ) -> None:
        if node.role not in self._ALLOWED_ROLES:
            raise App8ExecutionError("read-only specialist role is not allowed")
        if node.mutation_class is not MutationClass.READ_ONLY:
            raise App8ExecutionError("read-only specialist node must use READ_ONLY mutation class")
        if node.budget.max_tool_calls < 1:
            raise App8ExecutionError("read-only specialist requires a positive declared tool budget")
        if not profile.supports(node.agent_task()):
            raise App8ExecutionError("selected model profile does not support the specialist task")
        self.node = node
        self.exact_sha = _require_sha(exact_sha, "exact_sha")
        self.read_client = read_client
        self.profile = profile
        self.provider_client = provider_client
        self.subject_artifact_sha256 = subject_artifact_sha256
        if subject_artifact_sha256 is not None:
            _require_sha256(subject_artifact_sha256, "subject_artifact_sha256")

    def run(self) -> SpecialistExecutionRecord:
        registry = ToolRegistry()
        ExactCommitReadToolset(
            self.read_client,
            branch=self.node.branch_scope,
            expected_sha=self.exact_sha,
        ).register_into(registry)
        runner = ToolLoopRunner(
            self.provider_client,
            registry,
            budget=ToolLoopBudget(
                max_turns=self.node.budget.max_model_turns,
                max_tool_calls=self.node.budget.max_tool_calls,
                max_argument_chars=32_768,
                max_elapsed_seconds=self.node.budget.max_elapsed_seconds,
                max_model_facing_bytes=self.node.budget.max_model_facing_bytes,
            ),
        )
        result = runner.run(self._instruction())
        verdict, summary = self._parse_final(result.final_message)
        material = {
            "schema_version": APP8_EXECUTION_SCHEMA_VERSION,
            "policy_version": APP8_EXECUTION_POLICY_VERSION,
            "node_id": self.node.node_id,
            "role": self.node.role.value,
            "repository": self.node.repository,
            "exact_sha": self.exact_sha,
            "model_name": self.profile.name,
            "model_provider": self.profile.provider,
            "verdict": verdict.value,
            "summary": summary,
            "turns": result.turns,
            "tool_calls": result.tool_calls,
            "instruction_fingerprint": self.node.instruction_fingerprint,
            "subject_artifact_sha256": self.subject_artifact_sha256,
            "execution_authorized": False,
            "repository_mutation_authorized": False,
            "merge_authorized": False,
            "production_actions_authorized": False,
        }
        digest = _canonical_hash(material)
        return SpecialistExecutionRecord(
            node_id=self.node.node_id,
            role=self.node.role,
            repository=self.node.repository,
            exact_sha=self.exact_sha,
            model_name=self.profile.name,
            model_provider=self.profile.provider,
            verdict=verdict,
            summary=summary,
            turns=result.turns,
            tool_calls=result.tool_calls,
            output_sha256=digest,
            evidence_refs=(f"app8c-specialist:{digest}",),
            instruction_fingerprint=self.node.instruction_fingerprint,
            subject_artifact_sha256=self.subject_artifact_sha256,
        )

    def _instruction(self) -> str:
        subject = (
            f" Subject artifact SHA-256: {self.subject_artifact_sha256}."
            if self.subject_artifact_sha256 is not None
            else ""
        )
        return (
            f"You are the APP8C {self.node.role.value} specialist. "
            f"Repository {self.node.repository} is immutable at commit {self.exact_sha}. "
            "You may only use task.list_files and task.read_file; neither tool accepts a branch, "
            "ref, write request, PR action, merge action, deployment, training, activation, "
            "canonicalization, rollback, or credential operation. "
            "Do not claim CI or validator success unless it is present in the supplied exact-commit "
            "evidence. Return only strict JSON with exactly two fields: "
            '{"verdict":"pass|fail|abstain|review_required","summary":"..."}. '
            f"Task: {self.node.instruction}.{subject}"
        )

    @staticmethod
    def _parse_final(message: Mapping[str, Any]) -> tuple[NodeOutcome, str]:
        content = message.get("content")
        if not isinstance(content, str):
            raise SpecialistOutputError("specialist final content must be JSON text")
        try:
            value = json.loads(content)
        except json.JSONDecodeError as exc:
            raise SpecialistOutputError("specialist final content is not valid JSON") from exc
        if not isinstance(value, dict) or set(value) != {"verdict", "summary"}:
            raise SpecialistOutputError("specialist JSON must contain exactly verdict and summary")
        try:
            verdict = NodeOutcome(str(value["verdict"]))
        except ValueError as exc:
            raise SpecialistOutputError("specialist verdict is unsupported") from exc
        summary = _bounded_text(value.get("summary"), "specialist summary")
        return verdict, summary


class ImplementationDisposition(str, Enum):
    VERIFIED = "verified"
    PENDING = "pending"
    REVIEW_REQUIRED = "review_required"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ImplementationExecutionRecord:
    node_id: str
    repository: str
    task_id: str
    base_sha: str
    head_sha: str
    feature_branch: str
    model_name: str
    model_provider: str
    disposition: ImplementationDisposition
    artifact_sha256: str
    audit_verification_sha256: str | None
    evidence_refs: tuple[str, ...]
    instruction_fingerprint: str
    execution_authorized: bool = False
    pr_open_authorized: bool = False
    merge_authorized: bool = False
    production_actions_authorized: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": APP8_EXECUTION_SCHEMA_VERSION,
            "policy_version": APP8_EXECUTION_POLICY_VERSION,
            "node_id": self.node_id,
            "repository": self.repository,
            "task_id": self.task_id,
            "base_sha": self.base_sha,
            "head_sha": self.head_sha,
            "feature_branch": self.feature_branch,
            "model_name": self.model_name,
            "model_provider": self.model_provider,
            "disposition": self.disposition.value,
            "artifact_sha256": self.artifact_sha256,
            "audit_verification_sha256": self.audit_verification_sha256,
            "evidence_refs": list(self.evidence_refs),
            "instruction_fingerprint": self.instruction_fingerprint,
            "execution_authorized": False,
            "pr_open_authorized": False,
            "merge_authorized": False,
            "production_actions_authorized": False,
        }

    def to_verification_claim(self) -> VerificationClaim:
        if self.disposition is not ImplementationDisposition.VERIFIED:
            raise App8ExecutionError("implementation claim requires VERIFIED disposition")
        return VerificationClaim(
            claim_id=f"app8c:{self.artifact_sha256[:24]}",
            role=AgentRole.IMPLEMENTATION,
            source=ClaimSource.MODEL,
            verdict=EvidenceVerdict.PASS,
            repository=self.repository,
            commit_sha=self.head_sha,
            artifact_sha256=self.artifact_sha256,
            evidence_refs=self.evidence_refs,
            model_name=self.model_name,
            model_provider=self.model_provider,
            instruction_fingerprint=self.instruction_fingerprint,
        )


class GuardedImplementationBridge:
    """Reuse APP3-APP7 exact-head execution without exposing PR/merge authority."""

    def execute(
        self,
        *,
        node: SubtaskNode,
        project: str,
        expected_base_sha: str,
        producer_provider: str,
        service: GuardedImplementationService,
    ) -> ImplementationExecutionRecord:
        if node.role is not AgentRole.IMPLEMENTATION:
            raise App8ExecutionError("implementation bridge requires IMPLEMENTATION role")
        if node.mutation_class is not MutationClass.REVERSIBLE_FEATURE_BRANCH:
            raise App8ExecutionError(
                "implementation bridge requires REVERSIBLE_FEATURE_BRANCH mutation class"
            )
        base_sha = _require_sha(expected_base_sha, "expected_base_sha")
        if not producer_provider.strip():
            raise App8ExecutionError("producer_provider must not be empty")

        preview = service.preview(project, node.instruction)
        repository = _field(preview, "repository")
        preview_base = _field(preview, "base_sha")
        feature_branch = _field(preview, "feature_branch")
        task_id = _field(preview, "task_id")
        base_branch = _field(preview, "base_branch")
        if repository != node.repository:
            raise App8ExecutionError("service preview repository does not match implementation node")
        if preview_base != base_sha:
            raise App8ExecutionError("service preview base SHA does not match expected base SHA")
        if base_branch not in _PROTECTED_BRANCHES:
            raise App8ExecutionError("implementation service base branch must remain main/master")
        if not isinstance(feature_branch, str) or not feature_branch.strip():
            raise App8ExecutionError("service preview is missing feature branch")
        if feature_branch in _PROTECTED_BRANCHES:
            raise App8ExecutionError("implementation feature branch cannot be protected")
        if feature_branch != node.branch_scope:
            raise App8ExecutionError("implementation node is not bound to the preview feature branch")
        if not isinstance(task_id, str) or not task_id.startswith("task:"):
            raise App8ExecutionError("service preview is missing a valid task identity")

        run = service.run(task_id)
        run_repository = _field(run, "repository")
        run_branch = _field(run, "feature_branch")
        run_base = _field(run, "base_sha")
        head_sha = _require_sha(_field(run, "head_sha"), "implementation head_sha")
        model_name = _field(run, "model_name")
        if run_repository != node.repository or run_branch != feature_branch or run_base != base_sha:
            raise App8ExecutionError("implementation run identity differs from preview binding")
        if not isinstance(model_name, str) or not model_name.strip():
            raise App8ExecutionError("implementation run is missing model identity")
        if head_sha == base_sha:
            raise App8ExecutionError("implementation run did not advance the feature branch")

        refreshed = service.refresh_evidence(task_id)
        status = refreshed if isinstance(refreshed, Mapping) else service.status(task_id)
        commit = status.get("commit")
        if not isinstance(commit, Mapping) or commit.get("head_sha") != head_sha:
            raise App8ExecutionError("refreshed evidence is not bound to implementation HEAD")
        outcome = status.get("outcome")

        disposition = self._disposition(outcome)
        audit_sha: str | None = None
        evidence_refs = [f"app8c-task:{task_id}", f"app8c-head:{head_sha}"]
        if disposition is ImplementationDisposition.VERIFIED:
            audit = service.verify_current_audit(task_id)
            if audit.get("verified") is not True or audit.get("status") != "VERIFIED":
                raise App8ExecutionError("APP7 audit verification failed for VERIFIED implementation")
            audit_sha = _require_sha256(
                audit.get("verification_sha256"),
                "audit verification_sha256",
            )
            evidence_refs.append(f"app8c-audit:{audit_sha}")

        material = {
            "schema_version": APP8_EXECUTION_SCHEMA_VERSION,
            "policy_version": APP8_EXECUTION_POLICY_VERSION,
            "node_id": node.node_id,
            "repository": node.repository,
            "task_id": task_id,
            "base_sha": base_sha,
            "head_sha": head_sha,
            "feature_branch": feature_branch,
            "model_name": model_name,
            "model_provider": producer_provider,
            "disposition": disposition.value,
            "audit_verification_sha256": audit_sha,
            "instruction_fingerprint": node.instruction_fingerprint,
            "execution_authorized": False,
            "pr_open_authorized": False,
            "merge_authorized": False,
            "production_actions_authorized": False,
        }
        artifact_sha = _canonical_hash(material)
        return ImplementationExecutionRecord(
            node_id=node.node_id,
            repository=node.repository,
            task_id=task_id,
            base_sha=base_sha,
            head_sha=head_sha,
            feature_branch=feature_branch,
            model_name=model_name,
            model_provider=producer_provider,
            disposition=disposition,
            artifact_sha256=artifact_sha,
            audit_verification_sha256=audit_sha,
            evidence_refs=tuple(evidence_refs),
            instruction_fingerprint=node.instruction_fingerprint,
        )

    @staticmethod
    def _disposition(outcome: Any) -> ImplementationDisposition:
        if outcome == TaskOutcome.VERIFIED_SUCCESS.value:
            return ImplementationDisposition.VERIFIED
        if outcome == TaskOutcome.FAILED.value:
            return ImplementationDisposition.FAILED
        if outcome == TaskOutcome.REVIEW_REQUIRED.value:
            return ImplementationDisposition.REVIEW_REQUIRED
        return ImplementationDisposition.PENDING


def evaluate_verified_cycle(
    implementation: ImplementationExecutionRecord,
    validation: SpecialistExecutionRecord,
    critic: SpecialistExecutionRecord,
) -> GateReport:
    """Evaluate one exact-bound APP8C cycle; this never executes or widens authority."""
    producer_claim = implementation.to_verification_claim()
    validator_claim = validation.to_verification_claim()
    critic_claim = critic.to_verification_claim()
    return IndependentDisagreementGate().evaluate(
        producer_claim,
        validator_claim,
        critic_claim,
    )


def validate_execution_graph(graph: DependencyGraph) -> None:
    """Fail closed if APP8C graph roles request authority outside the guarded execution profile."""
    implementation_nodes = [
        node for node in graph.nodes if node.role is AgentRole.IMPLEMENTATION
    ]
    if len(implementation_nodes) > 1:
        raise App8ExecutionError("APP8C currently allows at most one implementation node per graph")
    for node in graph.nodes:
        if node.role is AgentRole.IMPLEMENTATION:
            if node.mutation_class is not MutationClass.REVERSIBLE_FEATURE_BRANCH:
                raise App8ExecutionError("implementation node must be reversible feature-branch only")
        elif node.mutation_class is not MutationClass.READ_ONLY:
            raise App8ExecutionError("non-implementation APP8C nodes must remain read-only")
