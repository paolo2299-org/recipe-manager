"""Tests for the native development-server launcher."""

import stat
import subprocess

import pytest

from scripts import dev_session


def test_detached_start_reports_ready_session(monkeypatch, tmp_path, capsys):
    state_dir = tmp_path / ".dev"
    log_file = state_dir / "server.log"
    monkeypatch.setattr(dev_session, "STATE_DIR", state_dir)
    monkeypatch.setattr(dev_session, "LOG_FILE", log_file)
    monkeypatch.setattr(dev_session, "lock_is_held", lambda: False)

    calls = 0

    def session(_command):
        nonlocal calls
        calls += 1
        if calls == 1:
            return None
        return {
            "pid": 1234,
            "url": "http://127.0.0.1:12345",
            "database": str(state_dir / "recipes.db"),
            "playwright_session": "recipe-test",
        }

    monkeypatch.setattr(dev_session, "active_session", session)

    class Process:
        pid = 1234

        def poll(self):
            return None

    def popen(command, **options):
        assert command[-1] == "start"
        assert options["start_new_session"] is True
        assert options["stdin"] == subprocess.DEVNULL
        assert options["stderr"] == subprocess.STDOUT
        return Process()

    monkeypatch.setattr(dev_session.subprocess, "Popen", popen)

    assert dev_session.start_detached() == 0
    assert "Dev URL: http://127.0.0.1:12345" in capsys.readouterr().out
    assert stat.S_IMODE(log_file.stat().st_mode) == 0o600


def test_detached_start_reports_early_exit(monkeypatch, tmp_path):
    state_dir = tmp_path / ".dev"
    monkeypatch.setattr(dev_session, "STATE_DIR", state_dir)
    monkeypatch.setattr(dev_session, "LOG_FILE", state_dir / "server.log")
    monkeypatch.setattr(dev_session, "active_session", lambda _command: None)
    monkeypatch.setattr(dev_session, "lock_is_held", lambda: False)

    class Process:
        pid = 1234
        returncode = 2

        def poll(self):
            return self.returncode

    monkeypatch.setattr(dev_session.subprocess, "Popen", lambda *_args, **_kwargs: Process())

    with pytest.raises(SystemExit, match="exited with status 2"):
        dev_session.start_detached()
    assert (state_dir / "server.log").exists()
