# Plan

## Decisions (Dakota, 2026-10-25)

- Name: `agent-context-router`
- Delivery: a small MCP server (Python, fastmcp, matching claude-reader)
- Scope for version 1: Dakota's own repos only (agent-context, the_professional, the_academic). No third-party remotes.

## Tools

- `list_modules()`: id, one-line trigger, repo, and whether it's loaded this session
- `load_module(id)`: module text plus the repo, path and commit sha it was read at
- `search_context(query, top_k)`: search over module triggers and INDEX.md summaries, for when no trigger obviously matches

## Sync rules

- Once per repo per session window, tracked by a timestamp on disk (subagents start their own MCP processes, so in-memory state isn't shared)
- `git fetch`, then fast-forward only
- Dirty working tree, diverged branch, or offline: read the local copy, warn, never reset
- Every load reports the sha it read

## Phases

1. Baseline (done 2026-10-25, `baseline-2026-10-25.md`); keep collecting until the switch
2. Policy sort (draft 2026-10-25, `policy-sort.md`); Dakota reviews the judgment calls
3. Move procedure text into module files; write the registry
4. Build the server and tests (done 2026-10-25) (one test per sync case: current, behind, dirty, diverged, offline)
5. Slim `assemble-goose-policy.sh` output; register the server in goose and Claude Code; add to agent-context manifest and both machine sync lists
6. One week on the router, then compare against the baseline; any rule whose adherence drops goes back to always-loaded

## Measurement

- Tokens: user and subagent sessions separately, from `sessions.db` (rp-why counts user sessions only)
- Adherence: `rpwhy_ce` for implicit commands, plus a per-module check that the router loaded the module when its trigger came up (router log and spore retrievals). `rpwhy_ce` alone only measures implicit commands, so it can't show adherence for moved procedures.

## Phase 3 record (2026-10-25)

- 21 modules extracted verbatim into `agent-context/policies/modules/` by `scripts/extract-policy-modules.py`; `--check` fails if the source policy changes without re-extracting.
- Slim policy in `agent-context/policies/slim/`. Assembled work policy: 15,961 bytes, from 60,761. Every module is referenced by a trigger, and every referenced module exists.
- `POLICY_SET=slim` in `assemble-goose-policy.sh` refuses the live path unless `ROUTER_LIVE=1`. The default full output is byte-identical to the live policy.
- Comment Voice and Device Testing keep core rules always loaded (Dakota, 2026-10-25).
- Harness smoke run, device-install, one run each: slim read the module before the first device command and targeted one device; 115k input tokens vs 176k for full. One run isn't evidence; the matrix is next.

- Matrix 2026-10-25 (`results/2026-10-25-matrix.md`): slim passed every check in 15/15 runs; about 57% fewer input tokens in total. Next: server, then a delegate scenario.
- Server built (phase 4): `list_modules`, `load_module(id)`, `search_context`; 15 unit tests including one per sync case.
- Router runs 2026-10-25 (`results/2026-10-25-router.md`): v3 used the router 20/20 with every check passing, including a delegate scenario. Next: phase 5, the live switch, which needs Dakota's go-ahead.
