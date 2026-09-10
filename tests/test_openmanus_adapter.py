import unittest

from st_music_agent_lab import Action, AuthorityMode, OpenManusAdapter, TaskSpec


class FixtureBackend:
    def propose(self, prompt, exposed_actions):
        self.prompt = prompt
        self.exposed_actions = exposed_actions
        return [
            {"action": "run_bounded_sandbox_tests", "rationale": "validate fixture"},
            {"action": "force_push", "rationale": "should never be admitted"},
            {
                "action": "write_bounded_task_files",
                "target_branch": "task/a2",
                "path": "src/st_music_agent_lab/models.py",
            },
        ]


class OpenManusAdapterTests(unittest.TestCase):
    def test_fixture_plan_is_filtered_through_st_policy(self) -> None:
        task = TaskSpec(
            task_id="a2-fixture",
            objective="plan a bounded local fixture task",
            target_repository="fixture/repo",
            mode=AuthorityMode.BRANCH_WRITE,
            capabilities=frozenset(
                {
                    Action.RUN_BOUNDED_SANDBOX_TESTS,
                    Action.WRITE_BOUNDED_TASK_FILES,
                    Action.FORCE_PUSH,
                }
            ),
            allowed_paths=("src/st_music_agent_lab",),
        )
        backend = FixtureBackend()
        plan = OpenManusAdapter().plan(task, backend)
        self.assertEqual(2, len(plan.actions))
        self.assertEqual(1, len(plan.blocked_actions))
        self.assertEqual(Action.FORCE_PUSH, plan.blocked_actions[0].request.action)
        self.assertNotIn("force_push", backend.exposed_actions)


if __name__ == "__main__":
    unittest.main()
