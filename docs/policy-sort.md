# Policy sort (draft for review, 2026-10-25)

Sizes are bytes in the agent-context source files. **Always** stays in the slim AGENTS.md. **Module** moves to on-demand text with a one-line trigger left behind. **Trim** keeps the rule lines and moves the procedure. Targets marked "exists" already have a convention file holding the detail.

## Shared policy (`goose-AGENTS.md`, 45,982 bytes)

- **Always:** Purpose, Trust Boundaries (583), Machine Profiles, Timezone & Date Anchoring (526), Working Style (1,251), Writing Style (2,224), Git Remotes (970), Terminal Tab Titles (1,190)
- **Trim to a few lines:** Load Order (872), Core Policy through Operational Guardrails (about 1,700 together, mostly the routing matrix and detection rules)
- **Trim:** Commit Convention (3,716): keep the headline rules, move the exceptions and the "why" text
- **Trim:** Branch Hygiene (3,240): keep the rules, move the protocols (sync before rebase, other-session check commands) to a git module
- **Trim:** Code Comments Protocol (1,371): keep "no comments, KDoc and test markers allowed"
- **Trim:** Implicit Commands (4,968): keep each phrase and a one-line action; procedures already live in the linked conventions (exists)
- **Trim:** PR Posting Policy (5,735): keep every posting gate; move bot comment triage steps (exists: `team-conventions.md` section 4, `feature-workflow.md`)
- **Module:** PR Description Structure with its template (about 6,000). Trigger: writing or updating a PR description
- **Module:** Repository Retrieval Protocol (1,783). Trigger: reading `~/the_professional`. Its own AGENTS.md already carries the retrieval protocol
- **Module:** Workspace Routing (1,420). Trigger: creating a file and choosing which repo it belongs in
- **Module:** Language Practices (1,130). Trigger: working in a repo with `go.mod` (exists: `references/go/go-docs-index.md`)
- **Module:** Review Cadence (150). Trigger: the monthly policy review
- **Judgment call:** Comment Voice (6,884). Trigger: drafting any text addressed to a person (reviews, replies, issues, Slack). The trigger is recognizable, but the voice applies to so much output that missing it is costly. The phase 1 trim kept it always-loaded.

## Work add-on (`goose-AGENTS.work.md`, 14,588 bytes)

- **Trim:** Work Machine: Personal Project Policy (3,070): keep the gate ("before any write to a dakotafabro repo, check the exceptions"); move the exceptions list to a module
- **Trim:** Device Testing (3,565): keep one line per safety rule (foreground check, single-device install, account changes, photos, blur, cleanup); move commands and examples
- **Trim:** Android CI/CD Changes (841): keep the one-line gate
- **Trim:** Ticket Creation Policy (1,549): keep "assign to Dakota, search before filing, gate PR findings"; move detail (exists: `ticket-triage.md`)
- **Module:** Session Patterns (3,714). Trigger: a session opens with a PR or Linear URL
- **Module:** Android Repo Location (761). Trigger: working in the team Android repo
- **Module:** Personal Project NPM Protocol (1,082). Trigger: `npm install` in a personal project

## Personal add-on (`goose-AGENTS.personal.md`, 2,445 bytes)

- **Always:** Personal Machine
- **Module:** Personal Repositories (1,444). Trigger: working in a personal repo

## Estimate

- Modules and trims move roughly 34KB of the 60.6KB work-machine policy, leaving about 27KB always loaded
- Moving Comment Voice too would leave about 21KB
- These are estimates from section sizes; the real number comes from the assembled file after phase 3

## Questions for Dakota

1. Comment Voice: always-loaded or module?
2. Device Testing: is one line per safety rule enough in the always-loaded layer, with commands in the module?
3. Where new module files live: `agent-context/policies/modules/` (versioned with the policy) or `the_professional/conventions/` (next to the existing ones)?
