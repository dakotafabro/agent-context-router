# agent-context-router - what changes for you

Your agent stops carrying every instruction on every turn. A slim AGENTS.md keeps the rules that always apply, and the agent loads the rest, one module at a time, when it reaches the work a module's trigger names. This page is for you, not the agent.

## How to read it

Check which modules your agent actually loads. Each load is a line in `~/.local/state/agent-context-router/loads.jsonl`, with the module id, the commit it was read at, and whether the repo was current. A module that never shows up either has a trigger the agent doesn't recognize or isn't needed.

When an answer looks off, look at the `repo_status` the agent got back. Anything other than `current`, `updated` or `local` means it read a local copy that may be stale, and the warning says why.

## When to override it

- **A rule didn't apply.** Its module probably didn't load. Make the trigger name the moment more plainly ("Before any adb command"), or move a one-line version of the rule into the slim AGENTS.md, so it holds even without the module.
- **The router isn't running** (a client without it, a delegate with extensions off). A slim file made by migrate names the module folder, so the agent can read the files directly. If yours doesn't, add that line.
- **You answered a `decide` question wrong.** Run `agent-context-router migrate decide <folder> --revisit` before switching, or fix it in `plan.yaml`. Then apply and review again.
- **A migration doesn't look right.** Run `agent-context-router migrate restore <folder>` to put your original file back.

## Reserved for human judgment

- **What stays always loaded and what becomes a module.** `migrate plan` suggests a split from section sizes alone. Which rules matter on every turn depends on your work and on the risk if a rule is missed. `migrate decide` asks you about each section in the terminal and ends with "Approve this split?"; you can also edit `plan.yaml` and set `approved_by_person: true` yourself.
- **Each module's trigger.** The trigger decides when a rule applies, so it has to say what you mean. migrate won't apply a plan until every trigger is replaced.
- **The exact files that get installed.** `migrate review` shows a summary (and a diff with `--diff`) and records your approval as a hash of the files. `switch` refuses anything that changed after that.
- **Replacing your instruction file.** `migrate switch` asks again, and won't proceed without a terminal unless `--yes` is passed.

`decide` only runs in a terminal and has no `--yes`, so nothing can answer it for you there. The other guards can't tell you from an agent. If an agent runs migrate for you, it should hand you `decide` in your own terminal or show you the plan and the review summary and wait for your answer, and never set `approved_by_person` or pass `--yes` itself.

## What it reads, writes and sends

- Reads: the registry (`ACR_REGISTRY`, or `~/.config/agent-context-router/modules.yaml`) and the module files it names.
- Writes: `loads.jsonl` and sync state under `~/.cache/agent-context-router/`. Before reading a module from a repo with a remote, it fetches and fast-forwards that clone at most every 30 minutes, and never over local changes. `migrate` writes only into the migration folder you name, except `switch` and `restore`, which write the one file you migrated.
- Sends: nothing beyond `git fetch` from the remotes in your registry. migrate adds no remote and never pushes.

## Turn it off

Disable the `agent-context-router` extension in goose, or run `claude mcp remove agent-context-router` in Claude Code. A slim AGENTS.md made by migrate still works without the router, since it names the module folder for the agent to read directly. To go back to your original file, run `agent-context-router migrate restore <folder>`.
