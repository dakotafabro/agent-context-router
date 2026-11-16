from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_REGISTRY = Path.home() / ".config" / "agent-context-router" / "modules.yaml"


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
    dir: str | None = None


@dataclass(frozen=True)
class Directory:
    name: str
    summary: str = ""
    repo: str | None = None
    file: str | None = None


@dataclass(frozen=True)
class Registry:
    repos: dict[str, Repo]
    modules: dict[str, Module]
    dirs: dict[str, Directory] = field(default_factory=dict)

    def _inside(self, repo_name: str, file: str, what: str) -> Path:
        root = self.repos[repo_name].path.resolve()
        path = (root / file).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"{what} points outside its repo: {file}")
        return path

    def module_path(self, module: Module) -> Path:
        return self._inside(module.repo, module.file, f"Module {module.id}")

    def card_path(self, directory: Directory) -> Path | None:
        if not directory.file:
            return None
        return self._inside(directory.repo or "", directory.file, f"Directory {directory.name}")


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


def _repo_path(value: str, base: Path) -> Path:
    path = Path(os.path.expanduser(value))
    return path if path.is_absolute() else (base / path).resolve()


def load_registry(path: Path | None = None, profile: str | None = None) -> Registry:
    path = Path(os.path.expanduser(os.environ.get("ACR_REGISTRY", "") or path or DEFAULT_REGISTRY))
    if not path.is_file():
        raise ValueError(f"No module registry at {path}. Set ACR_REGISTRY or create {DEFAULT_REGISTRY}; see examples/modules.yaml")
    data = yaml.safe_load(path.read_text())
    profile = profile or machine_profile()
    repos = {
        name: Repo(
            name=name,
            remote=spec.get("remote", ""),
            path=_repo_path(spec["path"], path.parent),
            branch=spec.get("branch", "main"),
        )
        for name, spec in data["repos"].items()
    }
    dirs: dict[str, Directory] = {}
    for name, spec in (data.get("dirs") or {}).items():
        spec = spec or {}
        directory = Directory(name=name, summary=spec.get("summary", ""), repo=spec.get("repo"), file=spec.get("file"))
        if directory.file and directory.repo not in repos:
            raise ValueError(f"Directory {name} names unknown repo {directory.repo}")
        dirs[name] = directory
    modules: dict[str, Module] = {}
    for spec in data["modules"]:
        module = Module(
            id=spec["id"],
            repo=spec["repo"],
            file=spec["file"],
            trigger=spec["trigger"],
            profile=spec.get("profile"),
            dir=spec.get("dir"),
        )
        if module.repo not in repos:
            raise ValueError(f"Module {module.id} names unknown repo {module.repo}")
        if module.dir is not None and module.dir not in dirs:
            raise ValueError(f"Module {module.id} names unknown dir {module.dir}; declare it under dirs")
        if module.id in modules:
            raise ValueError(f"Duplicate module id {module.id}")
        if module.profile in (None, profile):
            modules[module.id] = module
    return Registry(repos=repos, modules=modules, dirs=dirs)
