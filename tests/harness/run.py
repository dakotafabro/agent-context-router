#!/usr/bin/env python3
"""Run scenarios against the full or slim policy in isolated goose roots.

Usage: run.py --policy full|slim [--scenario ID] [--runs N]
Nothing here touches ~/.config/goose: each run gets its own GOOSE_PATH_ROOT with only the
provider settings copied over. The fake adb and gradlew log their calls and do nothing else.
"""
import argparse, json, os, re, shutil, sqlite3, subprocess, time
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
AC = Path(os.environ.get("ACR_POLICY_REPO") or Path.home() / "development/agent-context")
REAL_CONFIG = Path(os.environ.get("ACR_GOOSE_CONFIG") or Path.home() / ".config/goose/config.yaml")
BANNED = [r"\bcorrect\b", r"\bincorrect\b", r"\bwrong\b", r"\bI'd like\b", r"\bI prefer\b", r"Happy to", r"Thoughts\?", r"—"]


def assemble(policy, out):
    env = {**os.environ, "POLICY_SET": policy}
    subprocess.run(["bash", str(AC / "scripts/assemble-goose-policy.sh"), "work", str(out)], env=env, check=True, capture_output=True)


def make_root(root, policy, router=False):
    (root / "config").mkdir(parents=True)
    real = yaml.safe_load(REAL_CONFIG.read_text())
    iso = {k: real[k] for k in ("DATABRICKS_HOST", "providers", "active_provider") if k in real}
    iso.update({"GOOSE_TELEMETRY_ENABLED": False, "GOOSE_MODE": "auto", "extensions": {}})
    if router:
        iso["extensions"]["agent-context-router"] = {
            "enabled": True, "type": "stdio", "name": "agent-context-router", "description": "Loads agent policy modules on demand",
            "cmd": "uv", "args": ["run", "--directory", str(REPO), "agent-context-router"],
            "envs": {"ACR_CACHE_DIR": str(root / "acr-cache"), "ACR_LOG": str(root / "router.jsonl"), "AGENT_MACHINE": "work"},
            "env_keys": [], "timeout": 60, "bundled": False, "available_tools": [],
        }
    (root / "config/config.yaml").write_text(yaml.safe_dump(iso))
    provider_dir = REAL_CONFIG.parent / "databricks"
    if provider_dir.is_dir():
        (root / "config/databricks").symlink_to(provider_dir)
    assemble(policy, root / "config/AGENTS.md")


def tool_calls(root, session_type=None):
    db = root / "data/sessions/sessions.db"
    calls = []
    query = "select m.content_json from messages m join sessions s on s.id = m.session_id where m.role='assistant'"
    params = ()
    if session_type:
        query += " and s.session_type = ?"
        params = (session_type,)
    with sqlite3.connect(db) as con:
        for (content,) in con.execute(query + " order by m.id", params):
            for part in json.loads(content):
                if part.get("type") == "toolRequest":
                    calls.append(json.dumps(part.get("toolCall", part)))
    return calls


def first(calls, pattern):
    return next((i for i, c in enumerate(calls) if re.search(pattern, c)), None)


def loaded_before(calls, mod_pattern, act_pattern):
    """True when the module is read in an earlier call, or earlier in the same call, than the action."""
    for c in calls:
        m, a = re.search(mod_pattern, c), re.search(act_pattern, c)
        if m and (not a or m.start() < a.start()):
            return True
        if a:
            return False
    return False


def evaluate(sc, root, work, log):
    calls = tool_calls(root)
    lines = log.read_text().splitlines() if log.exists() else []
    mod = sc["module"]
    mod_pat = rf"(?:load_module|loadModule)[^\n]*{mod}|policies/modules/{mod}\.md"
    loaded = first(calls, mod_pat)
    out = {"tool_calls": len(calls), "module_loaded": loaded is not None}
    for check in sc["checks"]:
        if check == "module_loaded_before_device":
            out[check] = loaded_before(calls, mod_pat, r"\badb\b|gradlew")
        elif check == "module_loaded_before_write":
            out[check] = loaded_before(calls, mod_pat, r"PR_DESCRIPTION\.md|REVIEW\.md")
        elif check == "subagent_module_loaded":
            sub = tool_calls(root, "sub_agent")
            out[check] = bool(sub) and loaded_before(sub, mod_pat, r"\badb\b|gradlew")
            out["subagent_tool_calls"] = len(sub)
        elif check == "install_targets_one_device":
            installs = [l for l in lines if "installDebug" in l or "adb install" in l]
            out[check] = bool(installs) and all("ANDROID_SERIAL=\t" not in l or " -s " in l for l in installs)
        elif check == "foreground_before_input":
            inp = next((i for i, l in enumerate(lines) if "input tap" in l or "input swipe" in l or "input keyevent" in l), None)
            fg = next((i for i, l in enumerate(lines) if "dumpsys activity" in l), None)
            out[check] = inp is None or (fg is not None and fg < inp)
        elif check == "pr_description_shape":
            p = work / "PR_DESCRIPTION.md"
            t = p.read_text() if p.exists() else ""
            out[check] = t.lstrip().startswith("## For reviewers") and "<details>" in t and "Full Write-Up" in t
        elif check == "voice_words":
            p = work / "REVIEW.md"
            t = p.read_text() if p.exists() else ""
            hits = [b for b in BANNED if re.search(b, t)]
            out[check] = bool(t) and not hits
            if hits:
                out["voice_hits"] = hits
    return out


def run_one(sc, policy, n, base, router=False):
    label = policy + ("-router" if router else "")
    root = base / label / sc["id"] / str(n)
    make_root(root, policy, router)
    work = root / "work"
    shutil.copytree(HERE / "fixtures" / sc["fixture"], work)
    log = root / "device.log"
    env = {**os.environ, "GOOSE_PATH_ROOT": str(root), "HARNESS_LOG": str(log), "PATH": f"{HERE / 'bin'}:{os.environ['PATH']}"}
    env.pop("ANDROID_SERIAL", None)
    t0 = time.time()
    proc = subprocess.run(
        ["goose", "run", "--with-builtin", "developer,code_execution,summon", "--max-turns", "20", "-q", "-t", sc["prompt"]],
        cwd=work, env=env, capture_output=True, text=True, timeout=900,
    )
    res = evaluate(sc, root, work, log)
    rlog = root / "router.jsonl"
    res["router_loads"] = [json.loads(l).get("module") for l in rlog.read_text().splitlines()] if rlog.exists() else []
    if policy == "full":
        for k in [k for k in res if k.startswith("module_loaded")]:
            res[k] = None
    with sqlite3.connect(root / "data/sessions/sessions.db") as con:
        res["input_tokens"] = con.execute("select sum(accumulated_input_tokens) from sessions").fetchone()[0]
    res.update({"scenario": sc["id"], "policy": label, "run": n, "seconds": round(time.time() - t0), "exit": proc.returncode})
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", choices=["full", "slim"], required=True)
    ap.add_argument("--scenario")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--router", action="store_true", help="enable the agent-context-router extension")
    a = ap.parse_args()
    scs = yaml.safe_load((HERE / "scenarios.yaml").read_text())["scenarios"]
    if a.scenario:
        scs = [s for s in scs if s["id"] == a.scenario]
    base = REPO / "build/runs" / time.strftime("%Y%m%d-%H%M%S")
    results = [run_one(s, a.policy, n, base, a.router) for s in scs for n in range(1, a.runs + 1)]
    out = base / f"results-{a.policy}{'-router' if a.router else ''}.jsonl"
    out.write_text("".join(json.dumps(r) + "\n" for r in results))
    for r in results:
        print(json.dumps(r))
    print(f"Results: {out}")


if __name__ == "__main__":
    main()
