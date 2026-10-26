"""Keep a repo's local clone current, at most once per window, without ever discarding local work.

Rules: fetch, then fast-forward only. A dirty tree, another branch checked out, a diverged
branch, a local branch ahead of the remote, or a failed fetch all mean: read the local copy
and report why it wasn't updated. Nothing here resets, rebases or stashes.
"""
from __future__ import annotations

import fcntl
import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from agent_context_router.registry import Repo

DEFAULT_WINDOW_SECONDS = 30 * 60
FETCH_TIMEOUT_SECONDS = 15


def cache_dir() -> Path:
    return Path(os.environ.get("ACR_CACHE_DIR") or Path.home() / ".cache" / "agent-context-router")


@dataclass
class SyncResult:
    repo: str
    status: str
    sha: str
    warning: str = ""
    cached: bool = False


def _git(repo: Path, *args: str, timeout: float = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )


def _head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _sync(repo: Repo) -> SyncResult:
    path = repo.path
    if not (path / ".git").exists():
        return SyncResult(repo.name, "missing", "", f"No git clone at {path}")

    branch = _git(path, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    try:
        fetch = _git(path, "fetch", "--quiet", "origin", repo.branch, timeout=FETCH_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return SyncResult(repo.name, "offline", _head(path), "Fetch timed out; read the local copy")
    if fetch.returncode != 0:
        return SyncResult(repo.name, "offline", _head(path), "Fetch failed; read the local copy: " + fetch.stderr.strip()[:200])

    if branch != repo.branch:
        return SyncResult(repo.name, "other-branch", _head(path), f"{branch} is checked out, not {repo.branch}; read the local copy")

    local = _head(path)
    remote = _git(path, "rev-parse", f"origin/{repo.branch}").stdout.strip()
    if local == remote:
        return SyncResult(repo.name, "current", local)

    behind = _git(path, "merge-base", "--is-ancestor", local, remote).returncode == 0
    ahead = _git(path, "merge-base", "--is-ancestor", remote, local).returncode == 0
    if ahead:
        return SyncResult(repo.name, "ahead", local, "Local commits not pushed; read the local copy")
    if not behind:
        return SyncResult(repo.name, "diverged", local, f"{repo.branch} has diverged from origin; read the local copy")
    if _git(path, "status", "--porcelain").stdout.strip():
        return SyncResult(repo.name, "dirty", local, "Uncommitted changes; not updated, read the local copy")

    merge = _git(path, "merge", "--ff-only", "--quiet", f"origin/{repo.branch}")
    if merge.returncode != 0:
        return SyncResult(repo.name, "behind", local, "Fast-forward failed; read the local copy: " + merge.stderr.strip()[:200])
    return SyncResult(repo.name, "updated", _head(path))


def ensure_fresh(repo: Repo, window_seconds: float | None = None, now: float | None = None) -> SyncResult:
    if window_seconds is None:
        window_seconds = float(os.environ.get("ACR_SYNC_WINDOW", DEFAULT_WINDOW_SECONDS))
    now = time.time() if now is None else now
    directory = cache_dir()
    directory.mkdir(parents=True, exist_ok=True)
    state_path = directory / "sync-state.json"
    with open(directory / "sync.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        entry = state.get(repo.name)
        if entry and now - entry["checked_at"] < window_seconds and (repo.path / ".git").exists():
            sha = _head(repo.path)
            return SyncResult(repo.name, entry["status"], sha, entry.get("warning", ""), cached=True)
        result = _sync(repo)
        state[repo.name] = {"checked_at": now, **{k: v for k, v in asdict(result).items() if k != "cached"}}
        tmp = state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2))
        tmp.replace(state_path)
        return result
