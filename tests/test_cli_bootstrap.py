from __future__ import annotations

import subprocess
import sys

import pytest

from toss_browser_bridge import cli


def test_build_daemon_command_uses_current_interpreter(monkeypatch, tmp_path) -> None:
    python = tmp_path / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "executable", str(python))
    monkeypatch.setattr(cli, "PORT", 43111)

    command = cli.build_daemon_command()

    assert command == [
        str(python),
        "-m",
        "toss_browser_bridge.daemon",
        "run",
        "--port",
        "43111",
    ]
    assert "uv" not in command
    assert "--project" not in command


def test_resolve_python_executable_rejects_missing_interpreter(monkeypatch) -> None:
    monkeypatch.setattr(sys, "executable", "/tmp/toss-bridge-missing-python")

    with pytest.raises(RuntimeError, match="current Python interpreter does not exist"):
        cli.resolve_python_executable()


def test_ensure_daemon_running_spawns_module_without_repo_checkout(monkeypatch, tmp_path) -> None:
    python = tmp_path / "venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "executable", str(python))
    monkeypatch.setattr(cli, "PORT", 42194)
    monkeypatch.setattr(cli, "ensure_runtime_dirs", lambda: None)

    token_reads = iter([None, "token-123"])
    monkeypatch.setattr(cli, "read_text_if_exists", lambda path: next(token_reads))

    port_checks = iter([False, True])
    monkeypatch.setattr(cli, "wait_for_port", lambda timeout=0.0: next(port_checks))

    popen_calls: list[list[str]] = []

    class DummyProcess:
        pass

    def fake_popen(cmd: list[str], **kwargs: object) -> DummyProcess:
        popen_calls.append(cmd)
        assert kwargs["stdout"] is subprocess.DEVNULL
        assert kwargs["stderr"] is subprocess.DEVNULL
        assert kwargs["stdin"] is subprocess.DEVNULL
        assert kwargs["start_new_session"] is True
        return DummyProcess()

    monkeypatch.setattr(cli.subprocess, "Popen", fake_popen)

    token = cli.ensure_daemon_running()

    assert token == "token-123"
    assert popen_calls == [
        [
            str(python),
            "-m",
            "toss_browser_bridge.daemon",
            "run",
            "--port",
            "42194",
        ]
    ]


def test_ensure_daemon_running_surfaces_launch_failure(monkeypatch, tmp_path) -> None:
    python = tmp_path / "venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "executable", str(python))
    monkeypatch.setattr(cli, "ensure_runtime_dirs", lambda: None)
    monkeypatch.setattr(cli, "read_text_if_exists", lambda path: None)
    monkeypatch.setattr(cli, "wait_for_port", lambda timeout=0.0: False)

    def fake_popen(cmd: list[str], **kwargs: object) -> None:
        raise OSError("spawn failed")

    monkeypatch.setattr(cli.subprocess, "Popen", fake_popen)

    with pytest.raises(RuntimeError, match="failed to launch with the installed Python environment"):
        cli.ensure_daemon_running()
