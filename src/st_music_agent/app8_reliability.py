from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .app8_supervision import AgentRole, NodeOutcome
from .contracts import AgentTask, ModelProfile

APP8_RELIABILITY_SCHEMA_VERSION = "1.0.0"
APP8_RELIABILITY_POLICY_VERSION = "2026-09-12.app8b.v1"

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_PROJECT_KEY = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,127}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class CriticSelectionError(LookupError):
    pass


class GateContractError(ValueError):
    pass


class ReliabilityError(ValueError):
    pass


class ClaimSource(str, Enum):
    MODEL = "model"
    DETERMINISTIC = "deterministic"


class EvidenceVerdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    ABSTAIN = "abstain"
    UNAVAILABLE = "unavailable"
    REVIEW_REQUIRED = "review_required"


class GateDisposition(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    REVIEW_REQUIRED = "review_required"
    ABSTAIN = "abstain"


class ReliabilityDisposition(str, Enum):
    INSUFFICIENT_DATA = "insufficient_data"
    STABLE = "stable"
    WATCH = "watch"
    REVIEW = "review"


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class IndependentCriticSelection:
    model_name: str
    provider: str
    producer_model_name: str
    producer_provider: str
    provider_diverse: bool
    model_diverse: bool
    selection_fingerprint: str
    execution_authorized: bool = False
    repository_mutation_authorized: bool = False
    merge_authorized: bool = False
    production_actions_authorized: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": APP8_RELIABILITY_SCHEMA_VERSION,
            "model_name": self.model_name,
            "provider": self.provider,
            "producer_model_name": self.producer_model_name,
            "producer_provider": self.producer_provider,
            "provider_diverse": self.provider_diverse,
            "model_diverse": self.model_diverse,
            "selection_fingerprint": self.selection_fingerprint,
            "execution_authorized": False,
            "repository_mutation_authorized": False,
            "merge_authorized": False,
            "production_actions_authorized": False,
        }


class IndependentCriticSelector:
    """Select a compatible critic while excluding the producer model identity."""

    def __init__(self, models: Iterable[ModelProfile]) -> None:
        self._models = tuple(models)
        if not self._models:
            raise ValueError("at least one model profile is required")

    def select(
        self,
        task: AgentTask,
        *,
        producer_model_name: str,
        producer_provider: str,
    ) -> IndependentCriticSelection:
        if not producer_model_name.strip() or not producer_provider.strip():
            raise ValueError("producer model identity must not be empty")
        candidates = [
            model
            for model in self._models
            if model.supports(task) and model.name != producer_model_name
        ]
        if not candidates:
            raise CriticSelectionError("no independent compatible critic model is available")

        selected = max(
            candidates,
            key=lambda model: (
                model.provider != producer_provider,
                model.preference,
                model.context_window_tokens,
                model.name,
            ),
        )
        base = {
            "schema_version": APP8_RELIABILITY_SCHEMA_VERSION,
            "policy_version": APP8_RELIABILITY_POLICY_VERSION,
            "task": {
                "kind": task.kind.value,
                "needs_vision": task.needs_vision,
                "needs_tools": task.needs_tools,
                "minimum_context_tokens": task.minimum_context_tokens,
            },
            "producer_model_name": producer_model_name,
            "producer_provider": producer_provider,
            "selected_model_name": selected.name,
            "selected_provider": selected.provider,
            "provider_diverse": selected.provider != producer_provider,
            "model_diverse": selected.name != producer_model_name,
            "execution_authorized": False,
            "repository_mutation_authorized": False,
            "merge_authorized": False,
            "production_actions_authorized": False,
        }
        return IndependentCriticSelection(
            model_name=selected.name,
            provider=selected.provider,
            producer_model_name=producer_model_name,
            producer_provider=producer_provider,
            provider_diverse=selected.provider != producer_provider,
            model_diverse=True,
            selection_fingerprint=_canonical_hash(base),
        )


@dataclass(frozen=True, slots=True)
class VerificationClaim:
    claim_id: str
    role: AgentRole
    source: ClaimSource
    verdict: EvidenceVerdict
    repository: str
    commit_sha: str
    artifact_sha256: str
    evidence_refs: tuple[str, ...]
    model_name: str | None = None
    model_provider: str | None = None
    instruction_fingerprint: str | None = None
    claim_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.claim_id):
            raise GateContractError("claim_id has an invalid format")
        if self.role not in {
            AgentRole.IMPLEMENTATION,
            AgentRole.VALIDATION,
            AgentRole.CRITIC,
        }:
            raise GateContractError("verification claim role is not gate-compatible")
        if not _REPOSITORY.fullmatch(self.repository):
            raise GateContractError("repository must use owner/name form")
        if not _COMMIT_SHA.fullmatch(self.commit_sha):
            raise GateContractError("commit_sha must be a full lowercase 40-hex SHA")
        if not _SHA256.fullmatch(self.artifact_sha256):
            raise GateContractError("artifact_sha256 must be a lowercase SHA-256 digest")
        if not self.evidence_refs or any(not ref.strip() for ref in self.evidence_refs):
            raise GateContractError("evidence_refs must contain non-empty values")
        if self.source is ClaimSource.MODEL:
            if not self.model_name or not self.model_name.strip():
                raise GateContractError("model claim requires model_name")
            if not self.model_provider or not self.model_provider.strip():
                raise GateContractError("model claim requires model_provider")
        elif self.model_name is not None or self.model_provider is not None:
            raise GateContractError("deterministic claim must not declare model identity")
        if self.role in {AgentRole.IMPLEMENTATION, AgentRole.CRITIC} and self.source is not ClaimSource.MODEL:
            raise GateContractError("implementation and critic claims must be model claims")
        if self.instruction_fingerprint is not None and not _SHA256.fullmatch(
            self.instruction_fingerprint
        ):
            raise GateContractError("instruction_fingerprint must be a SHA-256 digest")
        object.__setattr__(self, "claim_fingerprint", _canonical_hash(self._base_dict()))

    def _base_dict(self) -> dict[str, Any]:
        return {
            "schema_version": APP8_RELIABILITY_SCHEMA_VERSION,
            "claim_id": self.claim_id,
            "role": self.role.value,
            "source": self.source.value,
            "verdict": self.verdict.value,
            "repository": self.repository,
            "commit_sha": self.commit_sha,
            "artifact_sha256": self.artifact_sha256,
            "evidence_refs": list(self.evidence_refs),
            "model_name": self.model_name,
            "model_provider": self.model_provider,
            "instruction_fingerprint": self.instruction_fingerprint,
        }

    def as_dict(self) -> dict[str, Any]:
        return {**self._base_dict(), "claim_fingerprint": self.claim_fingerprint}


@dataclass(frozen=True, slots=True)
class GateReport:
    disposition: GateDisposition
    repository: str
    commit_sha: str
    artifact_sha256: str
    producer_claim_fingerprint: str
    validator_claim_fingerprint: str
    critic_claim_fingerprint: str
    critic_independent: bool
    provider_diverse: bool
    reasons: tuple[str, ...]
    report_fingerprint: str
    execution_authorized: bool = False
    repository_mutation_authorized: bool = False
    merge_authorized: bool = False
    production_actions_authorized: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": APP8_RELIABILITY_SCHEMA_VERSION,
            "policy_version": APP8_RELIABILITY_POLICY_VERSION,
            "disposition": self.disposition.value,
            "repository": self.repository,
            "commit_sha": self.commit_sha,
            "artifact_sha256": self.artifact_sha256,
            "producer_claim_fingerprint": self.producer_claim_fingerprint,
            "validator_claim_fingerprint": self.validator_claim_fingerprint,
            "critic_claim_fingerprint": self.critic_claim_fingerprint,
            "critic_independent": self.critic_independent,
            "provider_diverse": self.provider_diverse,
            "reasons": list(self.reasons),
            "report_fingerprint": self.report_fingerprint,
            "execution_authorized": False,
            "repository_mutation_authorized": False,
            "merge_authorized": False,
            "production_actions_authorized": False,
        }


class IndependentDisagreementGate:
    """Require exact binding plus an independent critic before consensus is accepted."""

    def evaluate(
        self,
        producer: VerificationClaim,
        validator: VerificationClaim,
        critic: VerificationClaim,
    ) -> GateReport:
        self._require_roles(producer, validator, critic)
        reasons: list[str] = []
        bindings = {
            (claim.repository, claim.commit_sha, claim.artifact_sha256)
            for claim in (producer, validator, critic)
        }
        if len(bindings) != 1:
            reasons.append("claims are not bound to the same repository/commit/artifact")

        critic_independent = critic.model_name != producer.model_name
        provider_diverse = critic.model_provider != producer.model_provider
        if not critic_independent:
            reasons.append("critic model identity matches producer model")
        if (
            producer.instruction_fingerprint is not None
            and critic.instruction_fingerprint is not None
            and producer.instruction_fingerprint == critic.instruction_fingerprint
        ):
            reasons.append("critic instruction fingerprint matches producer instruction")

        verdicts = (producer.verdict, validator.verdict, critic.verdict)
        if any(verdict is EvidenceVerdict.UNAVAILABLE for verdict in verdicts):
            disposition = GateDisposition.ABSTAIN
            reasons.append("at least one required claim is unavailable")
        elif any(verdict is EvidenceVerdict.ABSTAIN for verdict in verdicts):
            disposition = GateDisposition.ABSTAIN
            reasons.append("at least one required claim abstained")
        elif any(verdict is EvidenceVerdict.REVIEW_REQUIRED for verdict in verdicts):
            disposition = GateDisposition.REVIEW_REQUIRED
            reasons.append("at least one required claim requests review")
        elif reasons:
            disposition = GateDisposition.REVIEW_REQUIRED
        elif len(set(verdicts)) != 1:
            disposition = GateDisposition.REVIEW_REQUIRED
            reasons.append("producer, validator, and critic disagree")
        elif verdicts[0] is EvidenceVerdict.PASS:
            disposition = GateDisposition.ACCEPT
        else:
            disposition = GateDisposition.REJECT

        repository, commit_sha, artifact_sha256 = (
            producer.repository,
            producer.commit_sha,
            producer.artifact_sha256,
        )
        base = {
            "schema_version": APP8_RELIABILITY_SCHEMA_VERSION,
            "policy_version": APP8_RELIABILITY_POLICY_VERSION,
            "disposition": disposition.value,
            "repository": repository,
            "commit_sha": commit_sha,
            "artifact_sha256": artifact_sha256,
            "producer_claim_fingerprint": producer.claim_fingerprint,
            "validator_claim_fingerprint": validator.claim_fingerprint,
            "critic_claim_fingerprint": critic.claim_fingerprint,
            "critic_independent": critic_independent,
            "provider_diverse": provider_diverse,
            "reasons": reasons,
            "execution_authorized": False,
            "repository_mutation_authorized": False,
            "merge_authorized": False,
            "production_actions_authorized": False,
        }
        return GateReport(
            disposition=disposition,
            repository=repository,
            commit_sha=commit_sha,
            artifact_sha256=artifact_sha256,
            producer_claim_fingerprint=producer.claim_fingerprint,
            validator_claim_fingerprint=validator.claim_fingerprint,
            critic_claim_fingerprint=critic.claim_fingerprint,
            critic_independent=critic_independent,
            provider_diverse=provider_diverse,
            reasons=tuple(reasons),
            report_fingerprint=_canonical_hash(base),
        )

    @staticmethod
    def _require_roles(
        producer: VerificationClaim,
        validator: VerificationClaim,
        critic: VerificationClaim,
    ) -> None:
        if producer.role is not AgentRole.IMPLEMENTATION:
            raise GateContractError("producer claim must use implementation role")
        if validator.role is not AgentRole.VALIDATION:
            raise GateContractError("validator claim must use validation role")
        if critic.role is not AgentRole.CRITIC:
            raise GateContractError("critic claim must use critic role")


@dataclass(frozen=True, slots=True)
class ReliabilityObservation:
    observation_id: str
    project_key: str
    role: AgentRole
    model_name: str
    model_provider: str
    outcome: NodeOutcome
    model_turns: int
    tool_calls: int
    retry_count: int = 0
    validator_failure_count: int = 0
    stale_evidence_attempts: int = 0
    policy_denied_tool_calls: int = 0
    disagreement_count: int = 0
    human_override_count: int = 0
    sha_mismatch_count: int = 0
    budget_exhaustion_count: int = 0
    regression_escape_count: int = 0
    observation_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.observation_id):
            raise ReliabilityError("observation_id has an invalid format")
        if not _PROJECT_KEY.fullmatch(self.project_key):
            raise ReliabilityError("project_key has an invalid format")
        if not self.model_name.strip() or not self.model_provider.strip():
            raise ReliabilityError("model identity must not be empty")
        counters = {
            "model_turns": self.model_turns,
            "tool_calls": self.tool_calls,
            "retry_count": self.retry_count,
            "validator_failure_count": self.validator_failure_count,
            "stale_evidence_attempts": self.stale_evidence_attempts,
            "policy_denied_tool_calls": self.policy_denied_tool_calls,
            "disagreement_count": self.disagreement_count,
            "human_override_count": self.human_override_count,
            "sha_mismatch_count": self.sha_mismatch_count,
            "budget_exhaustion_count": self.budget_exhaustion_count,
            "regression_escape_count": self.regression_escape_count,
        }
        if any(value < 0 for value in counters.values()):
            raise ReliabilityError("reliability counters must be >= 0")
        object.__setattr__(self, "observation_fingerprint", _canonical_hash(self._base_dict()))

    def _base_dict(self) -> dict[str, Any]:
        return {
            "schema_version": APP8_RELIABILITY_SCHEMA_VERSION,
            "observation_id": self.observation_id,
            "project_key": self.project_key,
            "role": self.role.value,
            "model_name": self.model_name,
            "model_provider": self.model_provider,
            "outcome": self.outcome.value,
            "model_turns": self.model_turns,
            "tool_calls": self.tool_calls,
            "retry_count": self.retry_count,
            "validator_failure_count": self.validator_failure_count,
            "stale_evidence_attempts": self.stale_evidence_attempts,
            "policy_denied_tool_calls": self.policy_denied_tool_calls,
            "disagreement_count": self.disagreement_count,
            "human_override_count": self.human_override_count,
            "sha_mismatch_count": self.sha_mismatch_count,
            "budget_exhaustion_count": self.budget_exhaustion_count,
            "regression_escape_count": self.regression_escape_count,
        }

    def as_dict(self) -> dict[str, Any]:
        return {**self._base_dict(), "observation_fingerprint": self.observation_fingerprint}


@dataclass(frozen=True, slots=True)
class ReliabilitySummary:
    project_key: str
    role: AgentRole
    model_name: str
    model_provider: str
    attempts: int
    successes: int
    failures: int
    abstentions: int
    review_required: int
    success_rate: float
    failure_rate: float
    unresolved_rate: float
    mean_model_turns: float
    mean_tool_calls: float
    retries: int
    validator_failures: int
    stale_evidence_attempts: int
    policy_denied_tool_calls: int
    disagreements: int
    human_overrides: int
    sha_mismatches: int
    budget_exhaustions: int
    regression_escapes: int
    disposition: ReliabilityDisposition
    summary_fingerprint: str
    auto_apply: bool = False
    privilege_change_authorized: bool = False
    execution_authorized: bool = False
    production_actions_authorized: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": APP8_RELIABILITY_SCHEMA_VERSION,
            "policy_version": APP8_RELIABILITY_POLICY_VERSION,
            "project_key": self.project_key,
            "role": self.role.value,
            "model_name": self.model_name,
            "model_provider": self.model_provider,
            "attempts": self.attempts,
            "successes": self.successes,
            "failures": self.failures,
            "abstentions": self.abstentions,
            "review_required": self.review_required,
            "success_rate": self.success_rate,
            "failure_rate": self.failure_rate,
            "unresolved_rate": self.unresolved_rate,
            "mean_model_turns": self.mean_model_turns,
            "mean_tool_calls": self.mean_tool_calls,
            "retries": self.retries,
            "validator_failures": self.validator_failures,
            "stale_evidence_attempts": self.stale_evidence_attempts,
            "policy_denied_tool_calls": self.policy_denied_tool_calls,
            "disagreements": self.disagreements,
            "human_overrides": self.human_overrides,
            "sha_mismatches": self.sha_mismatches,
            "budget_exhaustions": self.budget_exhaustions,
            "regression_escapes": self.regression_escapes,
            "disposition": self.disposition.value,
            "summary_fingerprint": self.summary_fingerprint,
            "auto_apply": False,
            "privilege_change_authorized": False,
            "execution_authorized": False,
            "production_actions_authorized": False,
        }


class ReliabilityAdvisor:
    """Produce transparent, advisory reliability summaries; never auto-change authority."""

    def __init__(self, *, minimum_attempts: int = 5) -> None:
        if minimum_attempts < 1:
            raise ValueError("minimum_attempts must be >= 1")
        self.minimum_attempts = minimum_attempts

    def summarize(
        self,
        observations: Iterable[ReliabilityObservation],
    ) -> tuple[ReliabilitySummary, ...]:
        grouped: dict[
            tuple[str, AgentRole, str, str], list[ReliabilityObservation]
        ] = defaultdict(list)
        for observation in observations:
            grouped[
                (
                    observation.project_key,
                    observation.role,
                    observation.model_name,
                    observation.model_provider,
                )
            ].append(observation)

        summaries = [
            self._summarize_group(key, values)
            for key, values in grouped.items()
        ]
        summaries.sort(
            key=lambda item: (
                item.project_key,
                item.role.value,
                item.model_provider,
                item.model_name,
            )
        )
        return tuple(summaries)

    def _summarize_group(
        self,
        key: tuple[str, AgentRole, str, str],
        observations: list[ReliabilityObservation],
    ) -> ReliabilitySummary:
        project_key, role, model_name, model_provider = key
        attempts = len(observations)
        successes = sum(item.outcome is NodeOutcome.PASS for item in observations)
        failures = sum(item.outcome is NodeOutcome.FAIL for item in observations)
        abstentions = sum(item.outcome is NodeOutcome.ABSTAIN for item in observations)
        review_required = sum(
            item.outcome is NodeOutcome.REVIEW_REQUIRED for item in observations
        )
        success_rate = successes / attempts
        failure_rate = failures / attempts
        unresolved_rate = (abstentions + review_required) / attempts
        mean_model_turns = sum(item.model_turns for item in observations) / attempts
        mean_tool_calls = sum(item.tool_calls for item in observations) / attempts
        retries = sum(item.retry_count for item in observations)
        validator_failures = sum(item.validator_failure_count for item in observations)
        stale_evidence_attempts = sum(item.stale_evidence_attempts for item in observations)
        policy_denied_tool_calls = sum(item.policy_denied_tool_calls for item in observations)
        disagreements = sum(item.disagreement_count for item in observations)
        human_overrides = sum(item.human_override_count for item in observations)
        sha_mismatches = sum(item.sha_mismatch_count for item in observations)
        budget_exhaustions = sum(item.budget_exhaustion_count for item in observations)
        regression_escapes = sum(item.regression_escape_count for item in observations)

        disposition = self._disposition(
            attempts=attempts,
            failure_rate=failure_rate,
            unresolved_rate=unresolved_rate,
            retries=retries,
            disagreements=disagreements,
            human_overrides=human_overrides,
            sha_mismatches=sha_mismatches,
            budget_exhaustions=budget_exhaustions,
            regression_escapes=regression_escapes,
        )
        base = {
            "schema_version": APP8_RELIABILITY_SCHEMA_VERSION,
            "policy_version": APP8_RELIABILITY_POLICY_VERSION,
            "project_key": project_key,
            "role": role.value,
            "model_name": model_name,
            "model_provider": model_provider,
            "attempts": attempts,
            "successes": successes,
            "failures": failures,
            "abstentions": abstentions,
            "review_required": review_required,
            "success_rate": success_rate,
            "failure_rate": failure_rate,
            "unresolved_rate": unresolved_rate,
            "mean_model_turns": mean_model_turns,
            "mean_tool_calls": mean_tool_calls,
            "retries": retries,
            "validator_failures": validator_failures,
            "stale_evidence_attempts": stale_evidence_attempts,
            "policy_denied_tool_calls": policy_denied_tool_calls,
            "disagreements": disagreements,
            "human_overrides": human_overrides,
            "sha_mismatches": sha_mismatches,
            "budget_exhaustions": budget_exhaustions,
            "regression_escapes": regression_escapes,
            "disposition": disposition.value,
            "auto_apply": False,
            "privilege_change_authorized": False,
            "execution_authorized": False,
            "production_actions_authorized": False,
        }
        return ReliabilitySummary(
            project_key=project_key,
            role=role,
            model_name=model_name,
            model_provider=model_provider,
            attempts=attempts,
            successes=successes,
            failures=failures,
            abstentions=abstentions,
            review_required=review_required,
            success_rate=success_rate,
            failure_rate=failure_rate,
            unresolved_rate=unresolved_rate,
            mean_model_turns=mean_model_turns,
            mean_tool_calls=mean_tool_calls,
            retries=retries,
            validator_failures=validator_failures,
            stale_evidence_attempts=stale_evidence_attempts,
            policy_denied_tool_calls=policy_denied_tool_calls,
            disagreements=disagreements,
            human_overrides=human_overrides,
            sha_mismatches=sha_mismatches,
            budget_exhaustions=budget_exhaustions,
            regression_escapes=regression_escapes,
            disposition=disposition,
            summary_fingerprint=_canonical_hash(base),
        )

    def _disposition(
        self,
        *,
        attempts: int,
        failure_rate: float,
        unresolved_rate: float,
        retries: int,
        disagreements: int,
        human_overrides: int,
        sha_mismatches: int,
        budget_exhaustions: int,
        regression_escapes: int,
    ) -> ReliabilityDisposition:
        if attempts < self.minimum_attempts:
            return ReliabilityDisposition.INSUFFICIENT_DATA
        if (
            regression_escapes > 0
            or sha_mismatches > 0
            or failure_rate > 0.25
            or disagreements / attempts > 0.25
            or human_overrides / attempts > 0.25
            or budget_exhaustions / attempts > 0.25
        ):
            return ReliabilityDisposition.REVIEW
        if (
            failure_rate > 0.10
            or unresolved_rate > 0.20
            or retries / attempts > 0.50
            or disagreements > 0
            or human_overrides > 0
            or budget_exhaustions > 0
        ):
            return ReliabilityDisposition.WATCH
        return ReliabilityDisposition.STABLE
