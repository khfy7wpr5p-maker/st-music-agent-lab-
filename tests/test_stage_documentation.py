from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
ARCHITECTURE = ROOT / "docs" / "architecture.md"


def test_documented_package_version_matches_pyproject() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = project["project"]["version"]
    readme = README.read_text(encoding="utf-8")

    assert f"Package version: `{version}`." in readme


def test_readme_and_architecture_include_completed_app8_chain() -> None:
    readme = README.read_text(encoding="utf-8")
    architecture = ARCHITECTURE.read_text(encoding="utf-8")

    for stage in ("APP8A", "APP8B", "APP8C", "APP8D", "APP8E"):
        assert stage in readme
        assert stage in architecture

    assert "A1-A26 guarded core + APP1-APP8E bounded runnable application" in architecture
    assert "docs/app8-operational-pilot.md" in readme
