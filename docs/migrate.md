# Migrating an existing AGENTS.md

`agent-context-router migrate` splits one instruction file into a slim always-loaded file plus modules the router loads on demand. It has six steps, plus `decide`, which walks you through the plan's questions in the terminal. Your original file is untouched until step 5, and only if you say yes.

You approve twice: once for the split, with `decide` or by editing `plan.yaml`, and once for the exact files that will be installed, with `review`. `switch` installs only what you reviewed.

The examples use `~/.config/goose/AGENTS.md` as the source and a new folder, `~/agent-context`, for the migration. Any instruction file works the same way, such as `~/.claude/CLAUDE.md` or `~/.config/goose/.goosehints`.

## 1. plan: read the file and suggest a split

```bash
agent-context-router migrate plan ~/.config/goose/AGENTS.md ~/agent-context
```

- Splits the file into sections at its main heading level: the shallowest level with at least two headings, usually `##`. Headings inside fenced code blocks don't count. A file with fewer than two headings stays one section.
- Suggests what becomes a module. The text before the first heading always stays. Sections under about 1.2 KB stay. Larger ones are suggested as modules.
- For each suggested module, lists up to five one-line bullets with "never", "always", "before", "must", "don't" or "do not" as `keep_lines`: rules worth keeping in the always-loaded file, so they hold even if the module never loads.
- Warns about lines that look like tokens, keys or passwords. Remove them from the source before migrating, because the migration folder keeps a copy.
- Writes one file, `~/agent-context/plan.yaml`. The folder must be empty, and it can't be the source's own folder.

### Approve the split, option A: decide (guided)

```bash
agent-context-router migrate decide ~/agent-context
```

`decide` asks the plan's questions one at a time and writes your answers into `plan.yaml` as you go.

1. **Each suggested module.** It shows the heading, size and first few lines, then asks `Make this a module, or keep it loaded? [M/k/q]`. For a module it asks `When should the agent load it?` and won't move on without an answer (Enter keeps a trigger you already gave). Then it asks about each candidate rule, `Keep loaded: <rule> [Y/n/q]`.
2. **The sections staying loaded.** It lists them, numbered, and asks which to move to a module. Enter means none. Each one you pick gets the same questions as step 1.
3. **Approval.** It shows the split (sections kept, size before the module list, each module's trigger and the rules that stay loaded) and asks `Approve this split? [y/N]`. Yes sets `approved_by_person: true`, then it offers to run apply.

Details:

- Type `q` at any prompt to stop. Your answers are saved, and the next `decide` picks up at the first section you haven't answered (they're marked `decided: true` in the plan). `--revisit` asks about every section again.
- Starting `decide` withdraws any earlier approval, since your answers may change. It's set again only when you say yes at the end.
- It needs a terminal and has no `--yes`, so it can't be answered by a script or an agent. Without a terminal, use option B.
- It refuses if the source changed since the plan.

### Approve the split, option B: edit plan.yaml

For each section:

- `action`: `keep` (stays in the always-loaded file) or `module` (loaded on demand). The suggestion is a starting point based on size only. Read each one.
- `trigger`, for each module: the moment the agent should load it, phrased as "Before X" where order matters ("Before any adb command", "Writing a PR description").
- `keep_lines`: edit, add or delete.
- `id`: rename if you like (lowercase letters, digits and dashes).

Leave `heading` alone. Every module starts with the trigger `TODO: when should the agent load this?`, and the next step refuses to run until each one is replaced.

You can mix the two: answer some sections in `decide`, then finish in the file. When you've read every section's action and trigger, set `approved_by_person: true` at the top of the file. The plan starts at `false`, and `apply` refuses until it's `true`. This records that you decided the split, not only the triggers.

## 2. apply: back up, then build the new files

```bash
agent-context-router migrate apply ~/agent-context
```

It checks first, and writes nothing if any check fails:

- The source still has the hash recorded in the plan.
- `approved_by_person` is `true`, every module has a trigger, ids are unique, and the sections and headings still match the source.

Then it backs up:

- `backup/AGENTS.md`: an exact copy of the source, with permissions and modified time kept.
- `backup/manifest.json`: the source path, sha256, size, modified time and backup time.
- With git installed, the folder becomes a local repo whose first commit is the backup alone. There's no remote, and the tool never pushes. If git is missing or has no identity set, the commit is skipped with a note; the copy and manifest are still written.

Then it builds:

- `modules/<id>.md`: each module section, copied exactly, under a one-line header.
- `AGENTS.md`: the slim file. A marker line, then the kept sections exactly as they were, then a `## Modules` list with each module's trigger, its keep lines, and the folder to read module files from when the router isn't available.
- `modules.yaml`: the registry the router reads.

It commits these, then runs verify. Running apply again after editing the plan rebuilds its own files and clears any earlier review, so the new files need a new one. It refuses to touch any file in the folder that it didn't write.

## 3. verify: check that nothing was lost

```bash
agent-context-router migrate verify ~/agent-context
```

- Every non-blank line of the backup must appear in the slim file or a module, counted with repeats.
- Every module must be listed in the slim file.
- The backup must still match its recorded hash.

Text may move. It may not be dropped or reworded. On failure, verify prints each missing line. apply and switch run it too.

## 4. review: approve the exact files

```bash
agent-context-router migrate review ~/agent-context
agent-context-router migrate review ~/agent-context --diff
```

Read `~/agent-context/AGENTS.md` first. It's what your agent will see on every turn. You can edit it, or the modules, by hand, as long as verify still passes.

- Runs verify, and stops if it fails.
- Shows a summary: the source, the always-loaded size before and after, the kept sections, and each module with its size, trigger and the rules that stay loaded. `--diff` adds a unified diff from your current file to the slim file.
- Asks `Approve these files in ~/agent-context for switch? [y/N]`. Anything but `y`, a closed input, or no terminal (unless `--yes`) records nothing.
- On `y`, writes `review.json` with one sha256 over the slim file, `modules.yaml` and every module file, and commits it.

## 5. switch: install the reviewed slim file

```bash
agent-context-router migrate switch ~/agent-context
```

- Runs verify, and stops if it fails.
- Refuses if there's no review, or if the slim file, `modules.yaml` or any module changed after the review. Run review again to approve the new files.
- Checks that the source still matches the backup. If you edited it since, it stops and asks you to plan again in a new folder, so those edits are kept.
- Shows the same summary as review (`--diff` works here too), then asks `Replace ~/.config/goose/AGENTS.md with the reviewed slim file from ~/agent-context? [y/N]`. Anything but `y` cancels. With no terminal it cancels, unless `--yes` is passed.
- Copies the current file to `backup/AGENTS.md.before-switch-<timestamp>`, then writes the slim file through a temp file and a rename, so an interrupted write can't leave half a file.
- Prints the next step: register the router with `ACR_REGISTRY=~/agent-context/modules.yaml` (see the README). It doesn't edit your goose or Claude Code config.

## 6. restore: undo

```bash
agent-context-router migrate restore ~/agent-context
```

- Checks the backup against its recorded hash.
- Refuses if the file was edited after the switch, so those edits aren't lost. `--force` restores anyway, after copying the edited file aside.
- Otherwise it asks, copies the current file to `backup/AGENTS.md.before-restore-<timestamp>`, and puts the original back.

## What it never does

- Change your file before switch, or install files you didn't review.
- Write outside the migration folder, except switch and restore writing the one source file.
- Push, or add a remote.
- Touch project or subdirectory instruction files, files the source imports, or your client config.

## Limits

- Backups live only in the migration folder. Deleting the folder deletes them.
- One file per migration. Project and subdirectory files aren't handled, since moving their rules changes which rule wins.
- Setext headings (`===` or `---` underlines) aren't recognized, and Windows paths haven't been tested.

## For agents running migrate for a person

The approvals above belong to the person. Point them to `decide` in their own terminal, or show them the plan and the review summary. Don't write triggers, change `action` or set `approved_by_person` without their answer, and don't pass `--yes` to review, switch or restore. The guards can't tell an agent from a person, so this rests on the agent.
