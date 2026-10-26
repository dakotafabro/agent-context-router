# agent-context-router

A small MCP server that loads agent context on demand. A slim, always-loaded AGENTS.md holds the rules that apply on every turn; everything else is a module in a linked repo, read only when a task needs it. Before reading, the router checks the local clone, fast-forwards it from the remote once per session if it's behind, and returns the commit it read.

**Status:** modules and slim policy written (in agent-context), test harness working. No server code yet.

- `docs/plan.md`: decisions, build phases and measurement
- `docs/baseline-2026-10-25.md`: token and adherence numbers before the router
- `docs/policy-sort.md`: every policy section sorted into always-loaded or on-demand, with its trigger
- `modules.yaml`: module registry
- `tests/harness/`: scenario runs in isolated goose roots with a fake `adb`, `gradlew` and `iterm-title`; `run.py --policy full|slim`

Tracked in dakotafabro/aaif-working-groups #1. Background: `aaif-working-groups/ideas/context-router.md` and `sources/003-context-router-prior-art.md`.
