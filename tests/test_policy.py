import unittest

from st_music_agent_lab import Action, ActionRequest, AuthorityMode, PolicyEngine, TaskSpec


class PolicyEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = PolicyEngine()

    def test_read_only_task_can_run_bounded_tests(self) -> None:
        task = TaskSpec(
            task_id="a1-read",
            objective="run fixture tests",
            target_repository="fixture/repo",
            capabilities=frozenset({Action.RUN_BOUNDED_SANDBOX_TESTS}),
        )
        decision = self.policy.evaluate(task, ActionRequest(Action.RUN_BOUNDED_SANDBOX_TESTS))
        self.assertTrue(decision.allowed)

    def test_ungranted_action_is_denied(self) -> None:
        task = TaskSpec("a1-deny", "inspect", "fixture/repo")
        decision = self.policy.evaluate(task, ActionRequest(Action.READ_REPOSITORY))
        self.assertFalse(decision.allowed)

    def test_default_branch_write_is_denied_even_when_capability_is_granted(self) -> None:
        task = TaskSpec(
            task_id="a1-main",
            objective="write fixture",
            target_repository="fixture/repo",
            mode=AuthorityMode.BRANCH_WRITE,
            capabilities=frozenset({Action.WRITE_BOUNDED_TASK_FILES}),
            allowed_paths=("src",),
        )
        decision = self.policy.evaluate(
            task,
            ActionRequest(Action.WRITE_BOUNDED_TASK_FILES, target_branch="main", path="src/x.py"),
        )
        self.assertFalse(decision.allowed)

    def test_hard_denial_cannot_be_self_granted(self) -> None:
        task = TaskSpec(
            task_id="a1-force",
            objective="attempt unsafe action",
            target_repository="fixture/repo",
            mode=AuthorityMode.PR_WRITE,
            capabilities=frozenset({Action.FORCE_PUSH}),
        )
        decision = self.policy.evaluate(task, ActionRequest(Action.FORCE_PUSH))
        self.assertFalse(decision.allowed)

    def test_write_path_must_be_bounded(self) -> None:
        task = TaskSpec(
            task_id="a1-path",
            objective="bounded edit",
            target_repository="fixture/repo",
            mode=AuthorityMode.BRANCH_WRITE,
            capabilities=frozenset({Action.WRITE_BOUNDED_TASK_FILES}),
            allowed_paths=("src/st_music_agent_lab",),
        )
        allowed = self.policy.evaluate(
            task,
            ActionRequest(
                Action.WRITE_BOUNDED_TASK_FILES,
                target_branch="task/a1",
                path="src/st_music_agent_lab/policy.py",
            ),
        )
        denied = self.policy.evaluate(
            task,
            ActionRequest(
                Action.WRITE_BOUNDED_TASK_FILES,
                target_branch="task/a1",
                path="contracts/AGENT_AUTHORITY_V0.json",
            ),
        )
        self.assertTrue(allowed.allowed)
        self.assertFalse(denied.allowed)


if __name__ == "__main__":
    unittest.main()
