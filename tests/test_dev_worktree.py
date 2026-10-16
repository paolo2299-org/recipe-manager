"""Exercise lifecycle guards against real disposable Git repositories."""

import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
from urllib.request import urlopen

import pytest

from scripts.dev_worktree import Refusal, Worktrees, git

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="Host worktree lifecycle tests require Git")


@pytest.fixture
def worktrees(tmp_path):
    remote = tmp_path / "origin.git"
    repo = tmp_path / "source"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    git(repo, "config", "user.name", "Lifecycle Test")
    git(repo, "config", "user.email", "test@example.invalid")
    (repo / ".gitignore").write_text(".dev/\n.venv/\n.env\n__pycache__/\n.pytest_cache/\n")
    (repo / "tracked.txt").write_text("original\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "Initial")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-u", "origin", "main")
    manager = Worktrees(repo)
    with manager.locked():
        yield manager


def test_create_list_and_finish_retains_branch(worktrees):
    target = worktrees.create("example")
    assert git(target, "branch", "--show-current") == "codex/example"
    assert json.loads(worktrees.record_file("example").read_text())["path"] == str(target)
    (target / ".venv").mkdir()
    (target / ".venv/generated").write_text("disposable")
    (target / ".dev").mkdir()
    (target / ".dev/recipes.db").write_text("scratch")
    assert worktrees.finish("example") == "codex/example"
    assert not target.exists()
    assert not worktrees.record_file("example").exists()
    assert git(worktrees.repo, "rev-parse", "codex/example")


@pytest.mark.parametrize("name", ["../source", "", "a/b", "-oops", "UpperCase", "a" * 49])
def test_bad_names_refused(worktrees, name):
    with pytest.raises(Refusal):
        worktrees.create(name)


@pytest.mark.parametrize("file", ["tracked.txt", "new.txt", ".env", ".dev/precious.txt"])
def test_unfinished_or_unexpected_files_preserved(worktrees, file):
    target = worktrees.create("unfinished")
    path = target / file
    path.parent.mkdir(exist_ok=True)
    path.write_text("must survive")
    with pytest.raises(Refusal, match="Uncommitted|Ignored file"):
        worktrees.finish("unfinished")
    assert path.read_text() == "must survive"
    assert worktrees.record_file("unfinished").exists()


def test_unpushed_commit_refused_then_pushed_commit_allowed(worktrees):
    target = worktrees.create("changes")
    (target / "tracked.txt").write_text("changed")
    git(target, "commit", "-am", "Work")
    with pytest.raises(Refusal, match="not preserved"):
        worktrees.finish("changes")
    assert target.exists()
    git(target, "push", "-u", "origin", "codex/changes")
    worktrees.finish("changes")
    assert not target.exists()


def test_fetch_failure_preserves_environment(worktrees):
    target = worktrees.create("offline")
    git(worktrees.repo, "remote", "set-url", "origin", str(worktrees.repo / "no-remote"))
    with pytest.raises(Refusal):
        worktrees.finish("offline")
    assert target.exists()


def test_stale_remote_ref_does_not_authorize_cleanup(worktrees):
    target = worktrees.create("stale")
    git(target, "commit", "--allow-empty", "-m", "New commit")
    git(target, "push", "origin", "codex/stale")
    # Delete directly at the bare remote, leaving local tracking data stale.
    remote = Path(git(worktrees.repo, "remote", "get-url", "origin"))
    git(remote, "update-ref", "-d", "refs/heads/codex/stale")
    with pytest.raises(Refusal, match="not preserved"):
        worktrees.finish("stale")
    assert target.exists()


@pytest.mark.parametrize("change", ["detach", "branch", "lock", "record", "symlink"])
def test_changed_identity_refused(worktrees, change):
    target = worktrees.create("identity")
    if change == "detach":
        git(target, "switch", "--detach")
    elif change == "branch":
        git(target, "switch", "-c", "other")
    elif change == "lock":
        git(worktrees.repo, "worktree", "lock", str(target))
    elif change == "record":
        record = json.loads(worktrees.record_file("identity").read_text())
        record["path"] = str(worktrees.main)
        worktrees.record_file("identity").write_text(json.dumps(record))
    else:
        (target / ".dev").symlink_to(worktrees.repo, target_is_directory=True)
    with pytest.raises(Refusal):
        worktrees.finish("identity")
    assert target.exists()


def test_unmanaged_worktree_never_removed(worktrees):
    target = worktrees.parent / "manual"
    git(worktrees.repo, "worktree", "add", "-b", "manual", str(target))
    with pytest.raises(Refusal, match="No valid managed"):
        worktrees.finish("manual")
    assert target.exists()


def test_finish_from_target_refused(worktrees, monkeypatch):
    target = worktrees.create("current")
    monkeypatch.chdir(target)
    with pytest.raises(Refusal, match="retained checkout"):
        worktrees.finish("current")
    assert target.exists()


def test_dirty_source_and_duplicate_names_refused(worktrees):
    worktrees.create("unique")
    with pytest.raises(Refusal, match="already exists"):
        worktrees.create("unique")
    (worktrees.repo / "new.txt").write_text("unfinished")
    with pytest.raises(Refusal, match="Source checkout"):
        worktrees.create("another")


def test_two_live_environments_cleanup_is_isolated(worktrees):
    source = Path(__file__).resolve().parents[1]
    shutil.copytree(source / "app", worktrees.repo / "app", ignore=shutil.ignore_patterns("__pycache__"))
    (worktrees.repo / "scripts").mkdir()
    shutil.copy2(source / "scripts/dev_session.py", worktrees.repo / "scripts/dev_session.py")
    shutil.copy2(source / "scripts/dev_config.py", worktrees.repo / "scripts/dev_config.py")
    git(worktrees.repo, "add", ".")
    git(worktrees.repo, "commit", "-m", "App for lifecycle test")
    git(worktrees.repo, "push", "origin", "main")
    targets = [worktrees.create(name) for name in ("alpha", "beta")]
    env = {**os.environ, "DEV_CONFIG_DISABLED": "1", "DEV_HOST": "127.0.0.1", "AUTH_ENABLED": "false"}

    def server(target, command):
        return subprocess.run(
            [sys.executable, str(target / "scripts/dev_session.py"), command],
            cwd=target, env=env, capture_output=True, text=True, timeout=40,
        )

    try:
        sessions = []
        for target in targets:
            (target / ".venv/bin").mkdir(parents=True)
            # Reuse this test suite's dependencies without installing packages
            # for each fixture; setup/uv is independently exercised by make setup.
            interpreter = target / ".venv/bin/python"
            interpreter.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} "$@"\n')
            interpreter.chmod(0o755)
            result = server(target, "start-detached")
            assert result.returncode == 0, result.stdout + result.stderr
            sessions.append(json.loads((target / ".dev/session.json").read_text()))
        assert sessions[0]["port"] != sessions[1]["port"]
        assert sessions[0]["database"] != sessions[1]["database"]
        assert sessions[0]["playwright_session"] != sessions[1]["playwright_session"]
        # A failed guard must not even stop the target's running server.
        (targets[0] / "unfinished.txt").write_text("keep me")
        with pytest.raises(Refusal, match="Uncommitted"):
            worktrees.finish("alpha")
        assert worktrees.server_running(targets[0])
        (targets[0] / "unfinished.txt").unlink()
        worktrees.finish("alpha")
        assert not targets[0].exists()
        assert worktrees.server_running(targets[1])
        with urlopen(sessions[1]["url"] + "/health", timeout=5) as response:
            assert response.status == 200
        worktrees.finish("beta")
        assert not targets[1].exists()
    finally:
        for target in targets:
            if target.exists():
                server(target, "stop")
