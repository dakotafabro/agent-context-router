from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from fastmcp import FastMCP

from agent_context_router.registry import load_registry
from agent_context_router.sync import ensure_fresh

INSTRUCTIONS = """Loads agent policy modules on demand.

The always-loaded AGENTS.md lists each module with a trigger. Before doing the work a trigger
names, call load_module with that id. Use list_modules to see every module, and search_context
when no trigger obviously matches. Each load reports the repo commit it read and any reason the
local copy couldn't be updated.
"""

mcp = FastMCP("Agent Context Router", instructions=INSTRUCTIONS)


def _log_path() -> Path:
    return Path(os.environ.get("ACR_LOG") or Path.home() / ".local" / "state" / "agent-context-router" / "loads.jsonl")


def _log(event: dict) -> None:
    path = _log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps({"ts": time.time(), **event}) + "\n")


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2}


def list_modules_impl() -> list[dict]:
    registry = load_registry()
    return [
        {"id": m.id, "trigger": m.trigger, "repo": m.repo, "file": m.file}
        for m in registry.modules.values()
    ]


def load_module_impl(module_id: str) -> dict:
    registry = load_registry()
    module = registry.modules.get(module_id)
    if module is None:
        known = ", ".join(sorted(registry.modules))
        raise ValueError(f"Unknown module '{module_id}'. Known modules: {known}")
    sync = ensure_fresh(registry.repos[module.repo])
    path = registry.module_path(module)
    if not path.is_file():
        raise ValueError(f"Module {module_id} file is missing: {path} (repo status: {sync.status})")
    _log({"event": "load", "module": module_id, "repo": module.repo, "sha": sync.sha, "status": sync.status, "cached": sync.cached})
    return {
        "id": module_id,
        "repo": module.repo,
        "file": module.file,
        "sha": sync.sha,
        "repo_status": sync.status,
        "warning": sync.warning,
        "content": path.read_text(),
    }


def search_context_impl(query: str, top_k: int = 5) -> list[dict]:
    registry = load_registry()
    terms = _words(query)
    scored = []
    for m in registry.modules.values():
        head = ""
        try:
            path = registry.module_path(m)
        except ValueError:
            continue
        if path.is_file():
            head = "\n".join(line for line in path.read_text().splitlines() if line.startswith("#"))
        score = 3 * len(terms & _words(m.id + " " + m.trigger)) + len(terms & _words(head))
        if score:
            scored.append((score, m))
    scored.sort(key=lambda x: (-x[0], x[1].id))
    _log({"event": "search", "query": query, "results": [m.id for _, m in scored[:top_k]]})
    return [{"id": m.id, "trigger": m.trigger, "score": s} for s, m in scored[:top_k]]


@mcp.tool()
def list_modules() -> str:
    """List every policy module available on this machine, with the trigger that says when to load it."""
    return json.dumps(list_modules_impl(), indent=2)


@mcp.tool()
def load_module(id: str) -> str:  # noqa: A002 - matches the call shown in AGENTS.md
    """Load a policy module's full text. Call before the work its trigger names.

    Args:
        id: The module id from the AGENTS.md module list or list_modules (e.g. "device-testing").

    Returns:
        JSON with the module content, the repo commit sha it was read at, the repo sync status
        (current, updated, local, dirty, ahead, diverged, other-branch, offline, missing) and any warning.
    """
    return json.dumps(load_module_impl(id), indent=2)


@mcp.tool()
def search_context(query: str, top_k: int = 5) -> str:
    """Find modules relevant to a task when no trigger obviously matches.

    Args:
        query: A short description of the work about to happen.
        top_k: Maximum number of modules to return.
    """
    return json.dumps(search_context_impl(query, top_k), indent=2)


def main() -> None:
    mcp.run()
