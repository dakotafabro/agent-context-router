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


def test_log_records_the_agent_session(setup, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "20261116_33")
    server.load_module_impl("device-testing")
    monkeypatch.delenv("AGENT_SESSION_ID")
    server.load_module_impl("device-testing")
    log = [json.loads(line) for line in (setup / "loads.jsonl").read_text().splitlines()]
    assert log[-2]["session"] == "20261116_33"
    assert "session" not in log[-1]


def test_unknown_module_lists_known(setup):
    with pytest.raises(ValueError, match="Known modules"):
        server.load_module_impl("nope")


def test_path_outside_repo_is_refused(setup):
    with pytest.raises(ValueError, match="outside its repo"):
        server.load_module_impl("escape")


def test_search_ranks_trigger_matches(setup):
    results = server.search_context_impl("install the debug build with adb on the emulator")
    assert results[0]["id"] == "device-testing"


def test_example_registry_loads_without_a_remote(monkeypatch, tmp_path):
    monkeypatch.delenv("ACR_REGISTRY", raising=False)
    monkeypatch.setenv("ACR_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("ACR_LOG", str(tmp_path / "loads.jsonl"))
    example = Path(__file__).resolve().parents[2] / "examples" / "modules.yaml"
    registry = load_registry(example, profile="work")
    missing = [m.id for m in registry.modules.values() if not registry.module_path(m).is_file()]
    assert missing == []
    assert set(registry.modules) == {"commit-messages", "pr-description", "device-testing"}
    monkeypatch.setenv("ACR_REGISTRY", str(example))
    result = server.load_module_impl("device-testing")
    assert result["repo_status"] == "local"
    assert "ANDROID_SERIAL" in result["content"]


def test_missing_registry_names_the_fix(monkeypatch, tmp_path):
    monkeypatch.setenv("ACR_REGISTRY", str(tmp_path / "nope.yaml"))
    with pytest.raises(ValueError, match="ACR_REGISTRY"):
        load_registry()


@pytest.fixture
def dirs(setup):
    repo = setup / "policy"
    (repo / "dirs").mkdir()
    (repo / "dirs" / "ship.md").write_text("# ship/\n- pr-description: when the PR text changes\n")
    path = setup / "modules.yaml"
    data = yaml.safe_load(path.read_text())
    data["modules"] = [m for m in data["modules"] if m["id"] != "escape"]
    data["dirs"] = {
        "ship": {"summary": "Getting a change merged", "repo": "policy", "file": "dirs/ship.md"},
        "review": {"summary": "Reviewing someone else's PR"},
    }
    data["modules"].append({"id": "commit-messages", "repo": "policy", "file": "modules/pr-description.md", "trigger": "Before a commit", "dir": "ship"})
    for m in data["modules"]:
        if m["id"] == "pr-description":
            m["dir"] = "ship"
    path.write_text(yaml.safe_dump(data))
    return setup


def test_list_modules_shows_dir_labels(dirs):
    entries = {m["id"]: m for m in server.list_modules_impl()}
    assert entries["pr-description"]["dir"] == "ship"
    assert "dir" not in entries["device-testing"]


def test_dir_returns_index_card_and_flags_missing_modules(dirs):
    card = server.list_modules_impl("ship/")
    assert card["dir"] == "ship"
    assert card["summary"] == "Getting a change merged"
    assert "when the PR text changes" in card["card"]
    assert [m["id"] for m in card["modules"]] == ["pr-description", "commit-messages"]
    assert card["missing_from_card"] == ["commit-messages"]
    log = [json.loads(line) for line in (dirs / "loads.jsonl").read_text().splitlines()]
    assert log[-1] == {**log[-1], "event": "index", "dir": "ship"}


def test_dir_without_card_still_lists_modules(dirs):
    card = server.list_modules_impl("review")
    assert card["card"] is None
    assert card["modules"] == []
    assert card["missing_from_card"] == []


def test_unknown_dir_lists_known(dirs):
    with pytest.raises(ValueError, match="Known dirs: review, ship"):
        server.list_modules_impl("nope")


def test_module_with_undeclared_dir_is_refused(dirs):
    path = dirs / "modules.yaml"
    data = yaml.safe_load(path.read_text())
    data["modules"][0]["dir"] = "typo"
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match="unknown dir typo"):
        load_registry()


def test_card_outside_repo_is_refused(dirs):
    path = dirs / "modules.yaml"
    data = yaml.safe_load(path.read_text())
    data["dirs"]["ship"]["file"] = "../outside.md"
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match="outside its repo"):
        server.list_modules_impl("ship")
