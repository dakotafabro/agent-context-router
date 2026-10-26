from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_REGISTRY = Path(__file__).resolve().parents[2] / "modules.yaml"


@dataclass(frozen=True)
class Repo:
    name: str
    remote: str
    path: Path
    branch: str = "main"


@dataclass(frozen=True)
class Module:
    id: str
    repo: str
    file: str
    trigger: str
    profile: str | None = None


@dataclass(frozen=True)
class Registry:
    repos: dict[str, Repo]
    modules: dict[str, Module]

    def module_path(self, module: Module) -> Path:
        repo = self.repos[module.repo]
        root = repo.path.resolve()
        path = (root / module.file).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"Module {module.id} points outside its repo: {module.file}")
        return path


def machine_profile() -> str:
    env = os.environ.get("AGENT_MACHINE", "").strip()
    if env in ("work", "personal"):
        return env
    marker = Path.home() / ".agent-machine"
    if marker.is_file():
        value = marker.read_text().strip()
        if value in ("work", "personal"):
            return value
    return "work"


def load_registry(path: Path | None = None, profile: str | None = None) -> Registry:
    path = Path(os.environ.get("ACR_REGISTRY", "") or path or DEFAULT_REGISTRY)
    data = yaml.safe_load(path.read_text())
    profile = profile or machine_profile()
    repos = {
        name: Repo(
            name=name,
            remote=spec["remote"],
            path=Path(os.path.expanduser(spec["path"])),
            branch=spec.get("branch", "main"),
        )
        for name, spec in data["repos"].items()
    }
    modules: dict[str, Module] = {}
    for spec in data["modules"]:
        module = Module(
            id=spec["id"],
            repo=spec["repo"],
            file=spec["file"],
            trigger=spec["trigger"],
            profile=spec.get("profile"),
        )
        if module.repo not in repos:
            raise ValueError(f"Module {module.id} names unknown repo {module.repo}")
        if module.id in modules:
            raise ValueError(f"Duplicate module id {module.id}")
        if module.profile in (None, profile):
            modules[module.id] = module
    return Registry(repos=repos, modules=modules)
