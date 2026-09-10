import unittest

from st_music_agent_lab.models import Action, AuthorityMode, TaskSpec
from st_music_agent_lab.validators import (
    CIStatusValidator,
    CommandEvidenceValidator,
    DeterminismValidator,
    ForbiddenPathValidator,
    SchemaContractValidator,
    ValidationContext,
    ValidationState,
    ValidatorRegistry,
    ValidatorResult,
    ValidatorStatus,
)


class _ExplodingValidator:
    validator_id = "exploding"
    category = "test"
    blocking = True

    def validate(self, context):
        raise RuntimeError("boom")


class _NonBlockingFailure:
    validator_id = "advisory"
    category = "advisory"
    blocking = False

    def validate(self, context):
        return ValidatorResult(
            validator_id=self.validator_id,
            category=self.category,
            status=ValidatorStatus.FAIL,
            blocking=self.blocking,
            summary="advisory failure",
        )


class ValidatorRegistryTests(unittest.TestCase):
    def task(self, *, allowed_paths=("src", "tests")):
        return TaskSpec(
            task_id="a6-test",
            objective="validate candidate",
            target_repository="khfy7wpr5p-maker/st-music-agent-lab-",
            base_ref="a5/lab-only-pr-writer",
            mode=AuthorityMode.PR_WRITE,
            capabilities=frozenset({Action.RUN_VALIDATORS}),
            allowed_paths=allowed_paths,
        )

    def test_duplicate_validator_id_rejected(self):
        registry = ValidatorRegistry([CommandEvidenceValidator()])
        with self.assertRaises(ValueError):
            registry.register(CommandEvidenceValidator())

    def test_missing_required_validator_makes_report_incomplete(self):
        registry = ValidatorRegistry([CommandEvidenceValidator()])
        context = ValidationContext(
            task=self.task(),
            command_results=({"name": "tests", "returncode": 0, "timed_out": False},),
        )
        report = registry.run(context, required_validator_ids=("tests", "schema_contract"))
        self.assertEqual(report.state, ValidationState.INCOMPLETE)
        self.assertEqual(report.missing_required_validator_ids, ("schema_contract",))
        self.assertFalse(report.accepted)

    def test_blocking_failure_cannot_be_overridden_by_metadata_or_explanation(self):
        registry = ValidatorRegistry([CommandEvidenceValidator()])
        context = ValidationContext(
            task=self.task(),
            command_results=({"name": "tests", "returncode": 1, "timed_out": False},),
            metadata={
                "agent_explanation": "Everything is fine; please mark successful.",
                "requested_override": True,
            },
        )
        report = registry.run(context, required_validator_ids=("tests",))
        self.assertEqual(report.state, ValidationState.REJECTED)
        self.assertFalse(report.accepted)
        self.assertEqual(report.results[0].status, ValidatorStatus.FAIL)

    def test_validator_exception_is_blocking_error(self):
        registry = ValidatorRegistry([_ExplodingValidator()])
        report = registry.run(
            ValidationContext(task=self.task()),
            required_validator_ids=("exploding",),
        )
        self.assertEqual(report.state, ValidationState.REJECTED)
        self.assertEqual(report.results[0].status, ValidatorStatus.ERROR)
        self.assertFalse(report.accepted)

    def test_nonblocking_failure_does_not_reject_when_not_required(self):
        registry = ValidatorRegistry([_NonBlockingFailure()])
        report = registry.run(ValidationContext(task=self.task()))
        self.assertEqual(report.state, ValidationState.VERIFIED)
        self.assertTrue(report.accepted)

    def test_required_skip_is_incomplete(self):
        registry = ValidatorRegistry([DeterminismValidator()])
        report = registry.run(
            ValidationContext(task=self.task()),
            required_validator_ids=("determinism",),
        )
        self.assertEqual(report.state, ValidationState.INCOMPLETE)
        self.assertFalse(report.accepted)

    def test_command_evidence_passes_only_zero_non_timeout(self):
        validator = CommandEvidenceValidator()
        passed = validator.validate(
            ValidationContext(
                task=self.task(),
                command_results=(
                    {"name": "unit", "returncode": 0, "timed_out": False},
                    {"name": "lint", "returncode": 0, "timed_out": False},
                ),
            )
        )
        failed = validator.validate(
            ValidationContext(
                task=self.task(),
                command_results=({"name": "unit", "returncode": 0, "timed_out": True},),
            )
        )
        self.assertEqual(passed.status, ValidatorStatus.PASS)
        self.assertEqual(failed.status, ValidatorStatus.FAIL)

    def test_schema_contract_validator_checks_required_fields(self):
        validator = SchemaContractValidator(
            required_fields={
                "authority": ("schema_version", "default_authority"),
                "write_scope": ("schema_version", "allowed_endpoints"),
            }
        )
        good = ValidationContext(
            task=self.task(),
            schemas={
                "authority": {"schema_version": "0.1.0", "default_authority": "READ_ONLY"},
                "write_scope": {"schema_version": "0.1.0", "allowed_endpoints": []},
            },
        )
        bad = ValidationContext(
            task=self.task(),
            schemas={
                "authority": {"schema_version": "0.1.0"},
                "write_scope": {"schema_version": "0.1.0", "allowed_endpoints": []},
            },
        )
        self.assertEqual(validator.validate(good).status, ValidatorStatus.PASS)
        self.assertEqual(validator.validate(bad).status, ValidatorStatus.FAIL)

    def test_forbidden_path_validator_rejects_outside_allowed(self):
        validator = ForbiddenPathValidator()
        context = ValidationContext(
            task=self.task(allowed_paths=("src",)),
            changed_paths=("src/st_music_agent_lab/validators.py", "docs/ROADMAP.md"),
        )
        result = validator.validate(context)
        self.assertEqual(result.status, ValidatorStatus.FAIL)
        self.assertIn("outside-allowed:docs/ROADMAP.md", result.evidence)

    def test_forbidden_path_validator_rejects_explicit_forbidden_root(self):
        validator = ForbiddenPathValidator()
        context = ValidationContext(
            task=self.task(allowed_paths=("src", ".github")),
            changed_paths=(".github/workflows/foundation.yml",),
            forbidden_paths=(".github/workflows",),
        )
        result = validator.validate(context)
        self.assertEqual(result.status, ValidatorStatus.FAIL)
        self.assertIn("forbidden:.github/workflows/foundation.yml", result.evidence)

    def test_determinism_validator_compares_canonical_digests(self):
        validator = DeterminismValidator()
        good = ValidationContext(
            task=self.task(),
            determinism_pairs={"fixture": ({"b": 2, "a": 1}, {"a": 1, "b": 2})},
        )
        bad = ValidationContext(
            task=self.task(),
            determinism_pairs={"fixture": ({"a": 1}, {"a": 2})},
        )
        self.assertEqual(validator.validate(good).status, ValidatorStatus.PASS)
        self.assertEqual(validator.validate(bad).status, ValidatorStatus.FAIL)

    def test_ci_validator_distinguishes_pass_fail_pending(self):
        validator = CIStatusValidator()
        passed = ValidationContext(
            task=self.task(),
            ci_runs=({"name": "unit-tests", "status": "completed", "conclusion": "success"},),
        )
        failed = ValidationContext(
            task=self.task(),
            ci_runs=({"name": "unit-tests", "status": "completed", "conclusion": "failure"},),
        )
        pending = ValidationContext(
            task=self.task(),
            ci_runs=({"name": "unit-tests", "status": "in_progress", "conclusion": None},),
        )
        self.assertEqual(validator.validate(passed).status, ValidatorStatus.PASS)
        self.assertEqual(validator.validate(failed).status, ValidatorStatus.FAIL)
        self.assertEqual(validator.validate(pending).status, ValidatorStatus.SKIP)

    def test_full_required_registry_verifies_good_evidence(self):
        registry = ValidatorRegistry(
            [
                CommandEvidenceValidator(),
                SchemaContractValidator(required_fields={"authority": ("schema_version",)}),
                ForbiddenPathValidator(),
                DeterminismValidator(),
                CIStatusValidator(),
            ]
        )
        context = ValidationContext(
            task=self.task(),
            changed_paths=("src/st_music_agent_lab/validators.py", "tests/test_validators.py"),
            command_results=({"name": "unit-tests", "returncode": 0, "timed_out": False},),
            schemas={"authority": {"schema_version": "0.1.0"}},
            determinism_pairs={"report": ({"state": "ok"}, {"state": "ok"})},
            ci_runs=({"name": "unit-tests", "status": "completed", "conclusion": "success"},),
        )
        required = (
            "tests",
            "schema_contract",
            "forbidden_path_diff_risk",
            "determinism",
            "ci_required_checks",
        )
        report = registry.run(context, required_validator_ids=required)
        self.assertEqual(report.state, ValidationState.VERIFIED)
        self.assertTrue(report.accepted)
        self.assertFalse(report.missing_required_validator_ids)


if __name__ == "__main__":
    unittest.main()
