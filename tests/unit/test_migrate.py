import json
import subprocess

import pytest
import yaml

from agent_context_router import migrate
from agent_context_router.migrate import MigrateError

LONG = "\n".join(f"- step {n}: run the thing with care and check the output" for n in range(30))

SOURCE = f"""# My agent rules

Short intro that stays.

## Always
- Never push to main.
- Use plain commit messages.

## Device Testing
- Always target one device with adb -s.
{LONG}

```bash
## not a heading inside a fence
adb devices
```

## PR Descriptions
- Open with For reviewers.
{LONG}
"""


@pytest.fixture(autouse=True)
def isolated_git(monkeypatch, tmp_path):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for key in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(key, "Test")
    for key in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(key, "test@example.com")


@pytest.fixture
def source(tmp_path):
    home = tmp_path / "home" / ".config" / "goose"
    home.mkdir(parents=True)
    path = home / "AGENTS.md"
    path.write_text(SOURCE)
    return path


def set_triggers(folder, approved=True, **triggers):
    path = folder / "plan.yaml"
    data = yaml.safe_load(path.read_text())
    data["approved_by_person"] = approved
    for entry in data["sections"]:
        if entry["id"] in triggers:
            entry["trigger"] = triggers[entry["id"]]
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def planned(source, tmp_path):
    folder = tmp_path / "migration"
    migrate.plan(source, folder)
    set_triggers(folder, **{"device-testing": "Before any adb command", "pr-descriptions": "Writing a PR description"})
    return folder


def test_split_ignores_headings_in_fences():
    headings = [s.heading for s in migrate.split_sections(SOURCE)]
    assert headings == ["", "Always", "Device Testing", "PR Descriptions"]


def test_split_without_two_headings_is_one_section():
    assert [s.heading for s in migrate.split_sections("just text\n## one\nmore")] == [""]


def test_plan_writes_only_the_plan_and_suggests_modules(source, tmp_path):
    folder = tmp_path / "migration"
    before = source.read_text()
    data = migrate.plan(source, folder)
    assert [p.name for p in folder.iterdir()] == ["plan.yaml"]
    assert source.read_text() == before
    actions = {e["id"]: e["action"] for e in data["sections"]}
    assert actions == {"preamble": "keep", "always": "keep", "device-testing": "module", "pr-descriptions": "module"}
    device = next(e for e in data["sections"] if e["id"] == "device-testing")
    assert device["keep_lines"] == ["- Always target one device with adb -s."]


def test_plan_refuses_a_folder_that_isnt_empty(source, tmp_path):
    folder = tmp_path / "migration"
    folder.mkdir()
    (folder / "notes.md").write_text("mine")
    with pytest.raises(MigrateError, match="isn't empty"):
        migrate.plan(source, folder)


def test_plan_refuses_the_source_folder(source):
    with pytest.raises(MigrateError, match="separate"):
        migrate.plan(source, source.parent)


def test_plan_warns_about_secrets(tmp_path):
    path = tmp_path / "src" / "AGENTS.md"
    path.parent.mkdir()
    path.write_text("## A\nuse ghp_" + "a" * 30 + "\n## B\nok\n")
    data = migrate.plan(path, tmp_path / "m")
    assert data["warnings"] == ["line 2: looks like a GitHub token. Remove it from the source before migrating; the migration folder keeps a copy."]


def test_apply_refuses_modules_without_triggers(source, tmp_path):
    folder = tmp_path / "migration"
    migrate.plan(source, folder)
    with pytest.raises(MigrateError, match="needs a trigger"):
        migrate.apply(folder)
    assert not (folder / "backup").exists()


def test_plan_starts_unapproved_and_apply_refuses_it(source, tmp_path):
    folder = tmp_path / "migration"
    data = migrate.plan(source, folder)
    assert data["approved_by_person"] is False
    set_triggers(folder, approved=False, **{"device-testing": "Before any adb command", "pr-descriptions": "Writing a PR description"})
    with pytest.raises(MigrateError, match="approved_by_person"):
        migrate.apply(folder)
    assert not (folder / "backup").exists()


def reviewed(source, tmp_path):
    folder = planned(source, tmp_path)
    migrate.apply(folder)
    assert migrate.review(folder, lambda q: True, show=lambda text: None)["status"] == "approved"
    return folder


def test_summary_shows_sizes_sections_triggers_and_kept_rules(source, tmp_path):
    folder = planned(source, tmp_path)
    migrate.apply(folder)
    text = migrate.summary(folder)
    assert f"from {len(SOURCE.encode()):,}" in text
    assert "Kept sections (2): (text before the first heading); Always" in text
    assert "- device-testing (" in text and "): Before any adb command" in text
    assert "    stays loaded: Always target one device with adb -s." in text
    diff = migrate.summary(folder, diff=True)
    assert "-- step 3: run the thing" in diff
    assert "+- `pr-descriptions`: Writing a PR description" in diff


def test_review_declined_records_nothing(source, tmp_path):
    folder = planned(source, tmp_path)
    migrate.apply(folder)
    shown = []
    assert migrate.review(folder, lambda q: False, show=shown.append)["status"] == "not approved"
    assert "Modules (2):" in shown[0]
    assert not (folder / "review.json").exists()


def test_switch_refuses_without_a_review(source, tmp_path):
    folder = planned(source, tmp_path)
    migrate.apply(folder)
    with pytest.raises(MigrateError, match="No review yet"):
        migrate.switch(folder, lambda q: True, show=lambda text: None)
    assert source.read_text() == SOURCE


@pytest.mark.parametrize("edit", ["AGENTS.md", "modules/device-testing.md", "modules.yaml"])
def test_switch_refuses_files_changed_after_review(source, tmp_path, edit):
    folder = reviewed(source, tmp_path)
    path = folder / edit
    path.write_text(path.read_text() + "\n# added after review\n")
    with pytest.raises(MigrateError, match="changed after the review"):
        migrate.switch(folder, lambda q: True, show=lambda text: None)
    assert source.read_text() == SOURCE


def test_apply_again_clears_the_review(source, tmp_path):
    folder = reviewed(source, tmp_path)
    migrate.apply(folder)
    assert not (folder / "review.json").exists()


def test_apply_refuses_a_changed_source(source, tmp_path):
    folder = planned(source, tmp_path)
    source.write_text(SOURCE + "\n- a new rule\n")
    with pytest.raises(MigrateError, match="changed since the plan"):
        migrate.apply(folder)


def test_apply_backs_up_splits_and_verifies(source, tmp_path):
    folder = planned(source, tmp_path)
    result = migrate.apply(folder)
    assert result["ok"], result["problems"]
    assert source.read_text() == SOURCE
    assert (folder / "backup" / "AGENTS.md").read_text() == SOURCE
    manifest = json.loads((folder / "backup" / "manifest.json").read_text())
    assert manifest["sha256"] == migrate.sha256(SOURCE)
    slim = (folder / "AGENTS.md").read_text()
    assert slim.startswith(migrate.MARKER_PREFIX)
    assert "## Always\n- Never push to main." in slim
    assert "- `device-testing`: Before any adb command" in slim
    assert "  - Always target one device with adb -s." in slim
    assert "step 3:" not in slim
    module = (folder / "modules" / "device-testing.md").read_text()
    assert "## not a heading inside a fence" in module
    registry = yaml.safe_load((folder / "modules.yaml").read_text())
    assert [m["id"] for m in registry["modules"]] == ["device-testing", "pr-descriptions"]
    log = subprocess.run(["git", "-C", str(folder), "log", "--format=%s"], capture_output=True, text=True).stdout.split("\n")
    assert log[:2] == ["Split AGENTS.md into a slim file and 2 modules", "Back up AGENTS.md before migrating"]
    first = subprocess.run(["git", "-C", str(folder), "show", "HEAD~1:backup/AGENTS.md"], capture_output=True, text=True).stdout
    assert first == SOURCE
    assert subprocess.run(["git", "-C", str(folder), "remote"], capture_output=True, text=True).stdout == ""


def test_example_registry_from_apply_loads_through_the_router(source, tmp_path, monkeypatch):
    folder = planned(source, tmp_path)
    migrate.apply(folder)
    from agent_context_router import server

    monkeypatch.setenv("ACR_REGISTRY", str(folder / "modules.yaml"))
    monkeypatch.setenv("ACR_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("ACR_LOG", str(tmp_path / "loads.jsonl"))
    result = server.load_module_impl("pr-descriptions")
    assert result["repo_status"] == "local"
    assert "- Open with For reviewers." in result["content"]


def test_verify_fails_on_a_dropped_or_reworded_line(source, tmp_path):
    folder = planned(source, tmp_path)
    migrate.apply(folder)
    path = folder / "modules" / "device-testing.md"
    path.write_text(path.read_text().replace("- step 7: run the thing", "- step 7: do the thing"))
    result = migrate.verify(folder)
    assert not result["ok"]
    assert any("step 7" in p for p in result["problems"])


def test_switch_refuses_a_changed_target_then_installs_and_restores(source, tmp_path):
    folder = reviewed(source, tmp_path)
    source.write_text(SOURCE + "\n- edited after the backup\n")
    with pytest.raises(MigrateError, match="changed since the backup"):
        migrate.switch(folder, lambda q: True, show=lambda text: None)
    source.write_text(SOURCE)

    assert migrate.switch(folder, lambda q: False, show=lambda text: None)["status"] == "cancelled"
    assert source.read_text() == SOURCE

    result = migrate.switch(folder, lambda q: True, show=lambda text: None)
    assert result["status"] == "switched"
    assert source.read_text() == (folder / "AGENTS.md").read_text()
    assert open(result["copy"]).read() == SOURCE

    restored = migrate.restore(folder, lambda q: True)
    assert restored["status"] == "restored"
    assert source.read_text() == SOURCE


def test_restore_refuses_an_edited_file_unless_forced(source, tmp_path):
    folder = reviewed(source, tmp_path)
    migrate.switch(folder, lambda q: True, show=lambda text: None)
    source.write_text(source.read_text() + "\n- my new rule\n")
    with pytest.raises(MigrateError, match="edited after the switch"):
        migrate.restore(folder, lambda q: True)
    result = migrate.restore(folder, lambda q: True, force=True)
    assert source.read_text() == SOURCE
    assert "- my new rule" in open(result["copy"]).read()


def test_apply_leaves_files_it_didnt_write(source, tmp_path):
    folder = planned(source, tmp_path)
    migrate.apply(folder)
    (folder / "modules" / "mine.md").write_text("hand written")
    with pytest.raises(MigrateError, match="wasn't written by migrate"):
        migrate.apply(folder)
    assert (folder / "modules" / "mine.md").read_text() == "hand written"


def test_cli_without_a_terminal_never_switches(source, tmp_path, capsys):
    folder = planned(source, tmp_path)
    assert migrate.cli(["apply", str(folder)]) == 0
    assert migrate.cli(["review", str(folder)]) == 1
    assert not (folder / "review.json").exists()
    migrate.review(folder, lambda q: True, show=lambda text: None)
    assert migrate.cli(["switch", str(folder)]) == 1
    assert source.read_text() == SOURCE


def test_closed_stdin_at_the_prompt_means_no(monkeypatch):
    monkeypatch.setattr(migrate.sys.stdin, "isatty", lambda: True, raising=False)

    def closed(_prompt):
        raise EOFError

    monkeypatch.setattr("builtins.input", closed)
    assert migrate._ask("Approve?") is False


def scripted(*answers):
    queue = list(answers)
    asked = []

    def ask(question):
        asked.append(question)
        return queue.pop(0)

    ask.asked = asked
    ask.left = queue
    return ask


def fresh_plan(source, tmp_path):
    folder = tmp_path / "migration"
    migrate.plan(source, folder)
    return folder


def plan_entries(folder):
    return {e["id"]: e for e in yaml.safe_load((folder / "plan.yaml").read_text())["sections"]}


def test_decide_walks_modules_then_kept_sections_then_approval(source, tmp_path):
    folder = fresh_plan(source, tmp_path)
    shown = []
    ask = scripted(
        "",
        "Before any adb command",
        "",
        "k",
        "1",
        "Before pushing",
        "n",
        "y",
    )
    result = migrate.decide(folder, ask, show=shown.append)
    assert result == {"status": "approved", "modules": 2}
    assert ask.left == []
    entries = plan_entries(folder)
    assert entries["device-testing"]["action"] == "module"
    assert entries["device-testing"]["trigger"] == "Before any adb command"
    assert entries["device-testing"]["keep_lines"] == ["- Always target one device with adb -s."]
    assert entries["pr-descriptions"]["action"] == "keep"
    assert entries["always"]["action"] == "module"
    assert entries["always"]["trigger"] == "Before pushing"
    assert entries["always"]["keep_lines"] == []
    assert all(e["decided"] for e in entries.values())
    assert yaml.safe_load((folder / "plan.yaml").read_text())["approved_by_person"] is True
    assert any("[1/2] Device Testing" in text for text in shown)
    assert any("1. Always" in text for text in shown)
    assert migrate.apply(folder)["ok"]


def test_decide_insists_on_a_trigger(source, tmp_path):
    folder = fresh_plan(source, tmp_path)
    shown = []
    ask = scripted("m", "", "Before any adb command", "y", "q")
    assert migrate.decide(folder, ask, show=shown.append)["status"] == "paused"
    assert any("A module needs a trigger" in text for text in shown)
    assert plan_entries(folder)["device-testing"]["trigger"] == "Before any adb command"


def test_decide_pauses_and_resumes_where_it_left_off(source, tmp_path):
    folder = fresh_plan(source, tmp_path)
    first = scripted("m", "Before any adb command", "y", "q")
    assert migrate.decide(folder, first, show=lambda text: None)["status"] == "paused"
    entries = plan_entries(folder)
    assert entries["device-testing"]["decided"] is True
    assert "decided" not in entries["pr-descriptions"]
    assert yaml.safe_load((folder / "plan.yaml").read_text())["approved_by_person"] is False

    second = scripted("m", "Writing a PR description", "", "y")
    assert migrate.decide(folder, second, show=lambda text: None)["status"] == "approved"
    assert not any("Device Testing" in q for q in second.asked)
    assert plan_entries(folder)["device-testing"]["trigger"] == "Before any adb command"


def test_decide_declined_approval_leaves_the_plan_unapproved(source, tmp_path):
    folder = fresh_plan(source, tmp_path)
    ask = scripted("m", "Before any adb command", "y", "m", "Writing a PR description", "", "")
    assert migrate.decide(folder, ask, show=lambda text: None)["status"] == "not approved"
    assert yaml.safe_load((folder / "plan.yaml").read_text())["approved_by_person"] is False
    with pytest.raises(MigrateError, match="approved_by_person"):
        migrate.apply(folder)


def test_decide_again_withdraws_an_earlier_approval(source, tmp_path):
    folder = planned(source, tmp_path)
    ask = scripted("q")
    migrate.decide(folder, ask, show=lambda text: None, revisit=True)
    assert yaml.safe_load((folder / "plan.yaml").read_text())["approved_by_person"] is False


def test_decide_refuses_a_changed_source(source, tmp_path):
    folder = fresh_plan(source, tmp_path)
    source.write_text(SOURCE + "\n- new\n")
    with pytest.raises(MigrateError, match="changed since the plan"):
        migrate.decide(folder, scripted(), show=lambda text: None)


def test_decide_rejects_numbers_out_of_range(source, tmp_path):
    folder = fresh_plan(source, tmp_path)
    shown = []
    ask = scripted("k", "k", "9", "x", "", "n")
    assert migrate.decide(folder, ask, show=shown.append)["status"] == "not approved"
    assert sum("Use numbers from 1 to" in text for text in shown) == 2


def test_cli_decide_needs_a_terminal(source, tmp_path, capsys):
    folder = fresh_plan(source, tmp_path)
    assert migrate.cli(["decide", str(folder)]) == 2
    assert "needs a terminal" in capsys.readouterr().err


BPM_BLOCK = """<!-- bpm:start -->

### Conventions

- **possibility-matrix** v0.3.0 (global) - 900 tokens

**Total token cost:** 900 tokens

<!-- bpm:end -->
"""


@pytest.fixture
def bpm_source(source):
    source.write_text(SOURCE + "\n## Packages\n" + LONG + "\n\n" + BPM_BLOCK)
    return source


def test_plan_keeps_the_bpm_block_loaded(bpm_source, tmp_path):
    folder = fresh_plan(bpm_source, tmp_path)
    entry = plan_entries(folder)["packages"]
    assert entry["bytes"] > migrate.MODULE_MIN_BYTES
    assert entry["action"] == "keep"
    assert entry["managed_by"] == "bpm"
    warnings = yaml.safe_load((folder / "plan.yaml").read_text())["warnings"]
    assert any("Packages holds a block that bpm rewrites" in w for w in warnings)


def test_apply_refuses_to_move_the_bpm_block(bpm_source, tmp_path):
    folder = planned(bpm_source, tmp_path)
    path = folder / "plan.yaml"
    data = yaml.safe_load(path.read_text())
    for entry in data["sections"]:
        if entry["id"] == "packages":
            entry["action"] = "module"
            entry["trigger"] = "Installing packages"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    with pytest.raises(MigrateError, match="packages: holds a block that bpm rewrites"):
        migrate.apply(folder)


def test_apply_leaves_the_bpm_block_in_the_slim_file(bpm_source, tmp_path):
    folder = planned(bpm_source, tmp_path)
    migrate.apply(folder)
    slim = (folder / "AGENTS.md").read_text()
    assert BPM_BLOCK.strip() in slim
    assert "bpm:start" not in "".join(p.read_text() for p in (folder / "modules").glob("*.md"))


def test_decide_never_offers_the_bpm_block(bpm_source, tmp_path):
    folder = fresh_plan(bpm_source, tmp_path)
    shown = []
    ask = scripted("k", "k", "", "y")
    assert migrate.decide(folder, ask, show=shown.append)["status"] == "approved"
    assert ask.left == []
    assert not any("Packages" in text for text in shown)
    assert plan_entries(folder)["packages"]["action"] == "keep"
