from __future__ import annotations

import tomllib
from pathlib import Path

from toss_browser_bridge import __version__


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_project_scripts_expose_expected_entrypoints() -> None:
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        pyproject = tomllib.load(handle)

    scripts = pyproject["project"]["scripts"]

    assert scripts["toss-bridge"] == "toss_browser_bridge.cli:main"
    assert scripts["toss-bridge-daemon"] == "toss_browser_bridge.daemon:main"


def test_project_version_matches_runtime_version() -> None:
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        pyproject = tomllib.load(handle)

    assert pyproject["project"]["name"] == "toss-browser-bridge"
    assert pyproject["project"]["version"] == __version__
