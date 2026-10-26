# AGENTS.md

## Always
- Plain imperative commit messages, one commit per PR.
- Never push to `main` directly.
- Target one device on every install (`adb -s <serial>`).

## Modules
Load a module before the work its trigger names, with the agent-context-router `load_module` tool. A rule above still applies when its module isn't loaded; the module adds the procedure and the exceptions.

- `commit-messages`: before writing a commit message or amending a commit
- `pr-description`: writing or updating a PR description
- `device-testing`: before any adb command or device install
