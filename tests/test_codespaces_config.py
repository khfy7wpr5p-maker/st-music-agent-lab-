import json
from pathlib import Path


EXPECTED_REPOSITORIES = {
    "khfy7wpr5p-maker/st-score-editor-core": {
        "permissions": {
            "actions": "read",
            "contents": "write",
            "pull_requests": "write",
        }
    },
    "khfy7wpr5p-maker/st-score-restore-engine": {
        "permissions": {
            "actions": "read",
            "contents": "write",
            "pull_requests": "write",
        }
    },
    "khfy7wpr5p-maker/musicxml-to-guitar-tab-engine": {
        "permissions": {
            "actions": "read",
            "contents": "write",
            "pull_requests": "write",
        }
    },
    "khfy7wpr5p-maker/st-real-time-score-following-lab": {
        "permissions": {
            "actions": "read",
            "contents": "write",
            "pull_requests": "write",
        }
    },
}


def test_codespaces_cross_repo_permissions_are_explicit_and_bounded() -> None:
    config_path = Path(__file__).parents[1] / ".devcontainer" / "devcontainer.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))

    repositories = config["customizations"]["codespaces"]["repositories"]

    assert repositories == EXPECTED_REPOSITORIES
    assert all("*" not in repository for repository in repositories)
    assert all(entry.get("permissions") != "write-all" for entry in repositories.values())
