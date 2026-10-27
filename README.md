# agent-context-router

An MCP server that loads agent instructions on demand.

A long AGENTS.md costs tokens on every request, and most of it applies to only a few tasks. agent-context-router splits it in two: a slim AGENTS.md that holds the rules for every turn and lists the rest as **modules**, each with a trigger, and this server, which reads a module when the agent reaches the work its trigger names. Modules live in ordinary git repos. Before reading one, the router fast-forwards the local clone from its remote (at most once every 30 minutes, and never over local work), then returns the module text with the commit it read.

It works with any MCP client. It's tested with [goose](https://github.com/aaif-goose/goose) and Claude Code.

[HUMAN.md](HUMAN.md) covers what changes for you once it's set up, what stays your call, and how to turn it off.

## Results

In a test harness of four scenarios with five runs each, the agent used the router in all 20 runs and passed every behavior check. Median input tokens per run, slim AGENTS.md plus router vs the full AGENTS.md:

- **Device install:** 84,964 vs 206,044
- **PR description:** 60,782 vs 180,964
- **Review comment:** 61,231 vs 117,576
- **Delegated device install:** 139,984 vs 265,154. The subagent loaded the device module on its own before any device command, in 5 of 5 runs.

These come from a small fixture, so real sessions with long conversations will save less as a percentage. Method, rounds and raw data: [`docs/results/2026-10-25-router.md`](docs/results/2026-10-25-router.md) and [`docs/results/`](docs/results/).

## Quick start

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/dakotafabro/agent-context-router.git
cd agent-context-router
uv sync
```

Try it with the bundled example, which has three modules and a slim AGENTS.md in [`examples/`](examples/):

```bash
ACR_REGISTRY="$PWD/examples/modules.yaml" uv run agent-context-router
```

### Register it in goose

Add this under `extensions:` in `~/.config/goose/config.yaml`, with your clone's absolute path:

```yaml
  agent-context-router:
    enabled: true
    type: stdio
    name: agent-context-router
    description: Loads agent instruction modules on demand
    cmd: uv
    args: [run, --directory, /path/to/agent-context-router, agent-context-router]
    envs:
      ACR_REGISTRY: /path/to/agent-context-router/examples/modules.yaml
    timeout: 60
```

Or try it for one session without editing config:

```bash
goose session --with-extension "ACR_REGISTRY=/path/to/agent-context-router/examples/modules.yaml uv run --directory /path/to/agent-context-router agent-context-router"
```

### Register it in Claude Code

```bash
claude mcp add -s user agent-context-router \
  -e ACR_REGISTRY=/path/to/agent-context-router/examples/modules.yaml \
  -- uv run --directory /path/to/agent-context-router agent-context-router
```

Then copy [`examples/AGENTS.md`](examples/AGENTS.md) into a project (or your global hints file) and ask the agent to write a PR description. It should call `load_module` with `pr-description` before writing.

Checked on 2026-10-26 in both clients with the bundled example: goose v1.56.0 (`--with-extension`) loaded `pr-description` before writing a PR description, and Claude Code 2.1.42 (`claude -p` with `--mcp-config`, project settings only) loaded `commit-messages` before writing a commit message. Each load appeared in the router's log.

## Tools

- `list_modules`: every module available on this machine, with its trigger
- `load_module(id)`: the module's text, plus the commit it was read at, the repo's sync status and any warning
- `search_context(query, top_k)`: modules that match a task description, for when no trigger obviously applies

Each `load_module` and `search_context` call is appended to `~/.local/state/agent-context-router/loads.jsonl`, so you can see which modules agents actually load.

## Migrating an existing AGENTS.md

The router never changes your config or your instruction files. To split a file you already have, use `migrate`, which works on one file at a time and keeps the original until you choose to switch:

```bash
uv run agent-context-router migrate plan ~/.config/goose/AGENTS.md ~/agent-context
uv run agent-context-router migrate decide ~/agent-context   # answers the plan's questions, then offers to run apply
uv run agent-context-router migrate apply ~/agent-context
uv run agent-context-router migrate review ~/agent-context
uv run agent-context-router migrate switch ~/agent-context
```

- **`plan`** reads the source and writes only `plan.yaml`, into a folder that must be empty. It splits the file at its main heading level, suggests sections over about 1.2 KB as modules, picks out one-line "never / always / before" rules to keep loaded, and warns about anything that looks like a secret.
- **`decide`** asks the plan's questions in the terminal: for each suggested module, keep it loaded or make it a module, when it should load, and which of its rules stay loaded; then which kept sections to move; then whether you approve the split. Answers are saved as you go, so `q` pauses and the next run resumes. It needs a terminal. You can edit `plan.yaml` by hand instead, and set `approved_by_person: true` yourself.
- **`apply`** refuses until the plan is approved (`approved_by_person: true`). It copies the source into `backup/` with its sha256, then writes `modules/`, a slim `AGENTS.md` and `modules.yaml` into the same folder. With git installed, the folder becomes a repo whose first commit is the untouched original, with no remote. It refuses a plan with a module that has no trigger, or a source that changed since the plan, and it won't overwrite files in the folder it didn't write.
- **`verify`** checks that every non-blank line of the original is in the slim file or a module. Text may move; it may not be dropped or reworded. `apply` and `switch` run it too.
- **`review`** shows what switch would install (sizes, kept sections, each module's trigger and kept rules, and a diff with `--diff`), asks for your approval, and records one hash over those exact files.
- **`switch`** installs only the reviewed files: it refuses if anything changed after the review. It shows the summary again and asks before replacing the source, refuses if the source changed since the backup, and copies the current file aside first. It doesn't ask when there's no terminal, so it never switches unattended unless you pass `--yes`.
- **`restore`** puts the original back. It refuses if the file was edited after the switch (pass `--force` to restore anyway; the edited file is copied aside first).

Which sections stay loaded is your call: `plan` only suggests. The full walkthrough, including where you approve each change, is in [`docs/migrate.md`](docs/migrate.md). Project and subdirectory AGENTS.md files aren't handled yet, since moving their rules changes which rule wins. On the author's 60 KB policy, `plan` found 36 sections and suggested 15 as modules; after `apply`, the always-loaded file was 13 KB and `verify` found all 330 lines of the original.

## Writing the slim AGENTS.md

The pattern that held up in testing:

1. **Keep the rules that apply every turn**, and keep a one-line version of any safety rule even when its module has the detail. A rule should still hold if its module never loads.
2. **List each module with a trigger** that names the moment to load it, phrased as "before X" where order matters.
3. **Name the router as the way to load, not one of two options.** When the policy offered "call the tool or read the file," the agent read the file in 18 of 20 runs and skipped the sync.
4. **Give the exact call.** In clients with tool discovery (goose Code Mode), a policy that left the agent guessing the parameter name cost a failed call and two discovery round trips per load.
5. **Tell delegates which module to load.** A subagent gets its own context, so name the module id in its instructions when its task hits a trigger.

See [`examples/AGENTS.md`](examples/AGENTS.md).

## Registry

The registry is a YAML file. The router reads it from `ACR_REGISTRY`, or from `~/.config/agent-context-router/modules.yaml` when that's unset.

```yaml
repos:
  team-policy:
    remote: git@github.com:your-org/agent-policy.git
    path: ~/src/agent-policy
    branch: main
  local:
    path: .

modules:
  - {id: pr-description, repo: team-policy, file: modules/pr-description.md, trigger: "Writing or updating a PR description"}
  - {id: device-testing, repo: team-policy, file: modules/device-testing.md, trigger: "Before any adb command or device install", profile: work}
```

- `path` may start with `~`, and a relative path is resolved from the registry file's directory.
- A repo without `remote` is read as it is, with status `local`.
- A module with `profile` loads only on machines with that profile, from `AGENT_MACHINE` or `~/.agent-machine` (`work` or `personal`, default `work`). A module without one loads everywhere.
- A module's `file` must stay inside its repo.

## Sync

For repos with a remote, the router fetches and fast-forwards only. It never resets, rebases or stashes. When it can't update, it reads the local copy and says why, so the agent can tell you the module may be stale:

- `current`, `updated`: up to date with the remote
- `dirty`, `ahead`, `diverged`, `other-branch`, `behind`: local state it won't overwrite
- `offline`: the fetch failed or timed out (15 seconds)
- `missing`: no clone at `path`

## Configuration

- `ACR_REGISTRY`: registry file
- `ACR_SYNC_WINDOW`: seconds between fetches of the same repo (default 1800)
- `ACR_CACHE_DIR`: sync state (default `~/.cache/agent-context-router`)
- `ACR_LOG`: load log (default `~/.local/state/agent-context-router/loads.jsonl`)
- `AGENT_MACHINE`: machine profile

## Development

```bash
uv run pytest
```

`tests/harness/run.py` is the scenario harness behind the results above. It runs each scenario in an isolated goose root (its own `GOOSE_PATH_ROOT`, so your sessions and config aren't touched), with fake `adb`, `gradlew` and `iterm-title` that only log their calls. It builds both policies with the author's policy repo, so to run it against your own, point `ACR_POLICY_REPO` at a repo with a `scripts/assemble-goose-policy.sh` that honors `POLICY_SET=full|slim`. `ACR_GOOSE_CONFIG` sets the goose config to copy provider settings from.

## Background

- [`docs/migrate.md`](docs/migrate.md): the migrate steps in full
- [`docs/plan.md`](docs/plan.md): decisions, build phases and measurement
- [`docs/baseline-2026-10-25.md`](docs/baseline-2026-10-25.md): token and adherence numbers before the router
- [`docs/policy-sort.md`](docs/policy-sort.md): how each section of a 60 KB AGENTS.md was sorted into always-loaded or on demand
- [aaif-goose/goose#13148](https://github.com/aaif-goose/goose/issues/13148): found while measuring the baseline. goose reloads a parent directory's hints file for each new subdirectory, which multiplies the cost of a long AGENTS.md.

## License

Apache 2.0
