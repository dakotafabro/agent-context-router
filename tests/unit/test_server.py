import json
import subprocess
from pathlib import Path

import pytest
import yaml

from agent_context_router import server
from agent_context_router.registry import load_registry


@pytest.fixture
def setup(tmp_path, monkeypatch):
    repo = tmp_path / "policy"
    (repo / "modules").mkdir(parents=True)
    (repo / "modules" / "device-testing.md").write_text("## Device Testing\n- target one device\n")
    (repo / "modules" / "pr-description.md").write_text("## PR Description Structure\nFor reviewers first\n")
    (repo / "modules" / "personal.md").write_text("## Personal Repositories\n")
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    registry = {
        "repos": {"policy": {"remote": "none", "path": str(repo), "branch": "main"}},
        "modules": [
            {"id": "device-testing", "repo": "policy", "file": "modules/device-testing.md", "trigger": "Before any adb command or device install", "profile": "work"},
            {"id": "pr-description", "repo": "policy", "file": "modules/pr-description.md", "trigger": "Writing or updating a PR description"},
            {"id": "personal-repositories", "repo": "policy", "file": "modules/personal.md", "trigger": "Working in a personal repo", "profile": "personal"},
            {"id": "escape", "repo": "policy", "file": "../outside.md", "trigger": "never"},
        ],
    }
    path = tmp_path / "modules.yaml"
    path.write_text(yaml.safe_dump(registry))
    monkeypatch.setenv("ACR_REGISTRY", str(path))
    monkeypatch.setenv("ACR_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("ACR_LOG", str(tmp_path / "loads.jsonl"))
    monkeypatch.setenv("AGENT_MACHINE", "work")
    return tmp_path


def test_profile_filters_modules(setup):
    ids = {m["id"] for m in server.list_modules_impl()}
    assert "device-testing" in ids
    assert "personal-repositories" not in ids


def test_load_module_returns_content_and_logs(setup):
    result = server.load_module_impl("device-testing")
    assert "target one device" in result["content"]
    assert result["repo_status"] in {"offline", "current"}
    log = [json.loads(line) for line in (setup / "loads.jsonl").read_text().splitlines()]
    assert log[-1]["module"] == "device-testing"


def test_unknown_module_lists_known(setup):
    with pytest.raises(ValueError, match="Known modules"):
        server.load_module_impl("nope")


def test_path_outside_repo_is_refused(setup):
    with pytest.raises(ValueError, match="outside its repo"):
        server.load_module_impl("escape")


def test_search_ranks_trigger_matches(setup):
    results = server.search_context_impl("install the debug build with adb on the emulator")
    assert results[0]["id"] == "device-testing"


def test_real_registry_files_exist():
    registry = load_registry(Path(__file__).resolve().parents[2] / "modules.yaml", profile="work")
    missing = [m.id for m in registry.modules.values() if not registry.module_path(m).is_file()]
    assert missing == []
