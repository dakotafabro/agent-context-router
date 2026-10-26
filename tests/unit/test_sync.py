import subprocess
from pathlib import Path

import pytest

from agent_context_router.registry import Repo
from agent_context_router.sync import ensure_fresh


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True)


def head(cwd):
    return subprocess.run(["git", "-C", str(cwd), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


def commit(cwd, name, text):
    (Path(cwd) / name).write_text(text)
    git(cwd, "add", name)
    git(cwd, "-c", "core.hooksPath=/dev/null", "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "-m", f"edit {name}")


@pytest.fixture
def repos(tmp_path, monkeypatch):
    monkeypatch.setenv("ACR_CACHE_DIR", str(tmp_path / "cache"))
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    seed = tmp_path / "seed"
    subprocess.run(["git", "clone", "-q", str(remote), str(seed)], check=True, capture_output=True)
    git(seed, "checkout", "-q", "-b", "main")
    commit(seed, "m.md", "v1\n")
    git(seed, "push", "-q", "origin", "main")
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", "-b", "main", str(remote), str(clone)], check=True, capture_output=True)
    return {"remote": remote, "seed": seed, "clone": clone, "repo": Repo("r", str(remote), clone, "main")}


def test_current(repos):
    result = ensure_fresh(repos["repo"], window_seconds=0)
    assert result.status == "current"
    assert result.sha == head(repos["clone"])


def test_behind_fast_forwards(repos):
    commit(repos["seed"], "m.md", "v2\n")
    git(repos["seed"], "push", "-q", "origin", "main")
    result = ensure_fresh(repos["repo"], window_seconds=0)
    assert result.status == "updated"
    assert result.sha == head(repos["seed"])
    assert (repos["clone"] / "m.md").read_text() == "v2\n"


def test_dirty_is_not_updated(repos):
    commit(repos["seed"], "m.md", "v2\n")
    git(repos["seed"], "push", "-q", "origin", "main")
    (repos["clone"] / "local.txt").write_text("work in progress\n")
    before = head(repos["clone"])
    result = ensure_fresh(repos["repo"], window_seconds=0)
    assert result.status == "dirty"
    assert result.sha == before
    assert (repos["clone"] / "local.txt").exists()
    assert (repos["clone"] / "m.md").read_text() == "v1\n"


def test_diverged_is_not_updated(repos):
    commit(repos["seed"], "m.md", "remote change\n")
    git(repos["seed"], "push", "-q", "origin", "main")
    commit(repos["clone"], "other.md", "local change\n")
    before = head(repos["clone"])
    result = ensure_fresh(repos["repo"], window_seconds=0)
    assert result.status == "diverged"
    assert result.sha == before


def test_ahead_is_reported(repos):
    commit(repos["clone"], "other.md", "local only\n")
    result = ensure_fresh(repos["repo"], window_seconds=0)
    assert result.status == "ahead"


def test_offline_reads_local(repos):
    git(repos["clone"], "remote", "set-url", "origin", str(repos["remote"]) + "-gone")
    result = ensure_fresh(repos["repo"], window_seconds=0)
    assert result.status == "offline"
    assert result.sha == head(repos["clone"])


def test_other_branch_is_not_updated(repos):
    git(repos["clone"], "checkout", "-q", "-b", "feature")
    commit(repos["seed"], "m.md", "v2\n")
    git(repos["seed"], "push", "-q", "origin", "main")
    result = ensure_fresh(repos["repo"], window_seconds=0)
    assert result.status == "other-branch"
    assert (repos["clone"] / "m.md").read_text() == "v1\n"


def test_missing_clone(tmp_path, monkeypatch):
    monkeypatch.setenv("ACR_CACHE_DIR", str(tmp_path / "cache"))
    result = ensure_fresh(Repo("r", "x", tmp_path / "nope", "main"), window_seconds=0)
    assert result.status == "missing"


def test_window_skips_fetch(repos):
    first = ensure_fresh(repos["repo"], window_seconds=600, now=1000)
    commit(repos["seed"], "m.md", "v2\n")
    git(repos["seed"], "push", "-q", "origin", "main")
    second = ensure_fresh(repos["repo"], window_seconds=600, now=1100)
    assert second.cached
    assert second.sha == first.sha
    third = ensure_fresh(repos["repo"], window_seconds=600, now=2000)
    assert not third.cached
    assert third.status == "updated"
