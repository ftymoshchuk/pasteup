import shlex
import socket
import subprocess
import sys
import threading
import time

import pytest
import uvicorn

from pasteup import __version__, cli, shortcut
from pasteup.main import app


@pytest.fixture
def launch(monkeypatch):
    """Run `pasteup` with the server, the browser and the port probe replaced."""
    served, opened, scheduled = [], [], []
    monkeypatch.setattr("uvicorn.run", lambda target, **kwargs: served.append((target, kwargs)))
    monkeypatch.setattr("webbrowser.open", opened.append)
    monkeypatch.setattr(cli, "_open_when_ready", scheduled.append)
    monkeypatch.setattr(cli, "_can_open_browser", lambda host: True)
    ports = {}
    monkeypatch.setattr(cli, "_probe", lambda host, port: ports.get(port, "free"))

    def run(*argv):
        cli.main(list(argv))
        return served, opened, scheduled

    run.ports = ports
    return run


def test_version_flag_prints_the_package_version(capsys) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--version"])

    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"pasteup {__version__}"


def test_serves_the_app_on_this_machine_and_opens_it(launch, capsys) -> None:
    served, opened, scheduled = launch()

    assert served == [
        ("pasteup.main:app", {"host": "127.0.0.1", "port": 8000, "reload": False, "log_level": "warning"})
    ]
    assert scheduled == ["http://127.0.0.1:8000/"]
    output = capsys.readouterr().out
    assert "Pasteup is running at http://127.0.0.1:8000/" in output
    assert "press Ctrl+C to stop it" in output


def test_no_browser_leaves_the_browser_alone(launch, capsys) -> None:
    served, opened, scheduled = launch("--no-browser")

    assert served and not scheduled and not opened
    assert "Open that address in your browser." in capsys.readouterr().out


def test_a_running_pasteup_is_opened_instead_of_started_twice(launch, capsys) -> None:
    launch.ports[8000] = "pasteup"

    served, opened, _ = launch()

    assert served == []
    assert opened == ["http://127.0.0.1:8000/"]
    assert "already running at http://127.0.0.1:8000/" in capsys.readouterr().out


def test_moves_to_the_next_free_port_when_another_program_has_the_default(launch, capsys) -> None:
    launch.ports.update({8000: "busy", 8001: "busy"})

    served, _, scheduled = launch()

    assert served[0][1]["port"] == 8002
    assert scheduled == ["http://127.0.0.1:8002/"]
    assert "Port 8000 is taken by another program, so Pasteup is using 8002." in capsys.readouterr().out


def test_a_port_chosen_on_purpose_is_not_swapped(launch) -> None:
    launch.ports[9000] = "busy"

    with pytest.raises(SystemExit) as exit_info:
        launch("--port", "9000")

    assert "Port 9000 is in use by another program" in str(exit_info.value.code)


@pytest.mark.parametrize("port", ["0", "70000", "eighty"])
def test_a_port_outside_the_valid_range_is_refused(port, capsys) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--port", port])

    assert exit_info.value.code == 2
    assert "--port" in capsys.readouterr().err


def test_warns_when_listening_beyond_this_machine(launch, capsys) -> None:
    launch("--host", "0.0.0.0", "--port", "9000")

    assert "See SECURITY.md" in capsys.readouterr().err


def test_a_wildcard_address_is_opened_through_this_machine(launch) -> None:
    _, _, scheduled = launch("--host", "0.0.0.0")

    assert scheduled == ["http://127.0.0.1:8000/"]


def test_python_dash_m_runs_the_same_command() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pasteup", "--version"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == f"pasteup {__version__}"


def test_no_browser_without_a_display_on_linux(monkeypatch) -> None:
    """Python would fall back to a text browser that takes over the terminal."""
    monkeypatch.setattr(sys, "platform", "linux")
    for name in ("BROWSER", "DISPLAY", "WAYLAND_DISPLAY"):
        monkeypatch.delenv(name, raising=False)

    assert not cli._can_open_browser("127.0.0.1")

    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    assert cli._can_open_browser("127.0.0.1")
    assert not cli._can_open_browser("192.168.1.20")


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_probe_tells_pasteup_from_other_programs() -> None:
    port = _free_port()
    assert cli._probe("127.0.0.1", port) == "free"

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        assert cli._probe("127.0.0.1", port) == "pasteup"
    finally:
        server.should_exit = True
        thread.join(timeout=10)

    with socket.socket() as other_program:
        # The port can still hold the closed server's connections in TIME_WAIT.
        other_program.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        other_program.bind(("127.0.0.1", port))
        other_program.listen()
        assert cli._probe("127.0.0.1", port) == "busy"


def test_shortcut_flag_writes_the_launcher_and_exits(launch, monkeypatch, capsys) -> None:
    monkeypatch.setattr(shortcut, "create_shortcut", lambda: "Made a launcher.")

    served, _, _ = launch("--shortcut")

    assert served == []
    assert capsys.readouterr().out.strip() == "Made a launcher."


def test_macos_shortcut_runs_this_python(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "Desktop").mkdir()

    message = shortcut.create_shortcut("darwin")

    launcher = tmp_path / "Desktop" / "Pasteup.command"
    assert str(launcher) in message
    assert launcher.stat().st_mode & 0o111
    script = launcher.read_text()
    assert script.startswith("#!/bin/sh\n")
    assert shlex.split(script.splitlines()[-1]) == ["exec", sys.executable, "-m", "pasteup"]
    subprocess.run(["sh", "-n", str(launcher)], check=True)


def test_windows_shortcut_runs_this_python(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(shortcut, "_windows_desktop", lambda: tmp_path)

    shortcut.create_shortcut("win32")

    script = (tmp_path / "Pasteup.bat").read_bytes().decode("utf-8")
    assert script.startswith("@echo off\r\nchcp 65001 >nul\r\n")
    assert f'\r\n"{sys.executable}" -m pasteup\r\n' in script
    assert "\n" not in script.replace("\r\n", "")


def test_linux_shortcut_is_an_applications_menu_entry(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    message = shortcut.create_shortcut("linux")

    entry = (tmp_path / "applications" / "pasteup.desktop").read_text()
    assert "applications menu" in message
    assert f'Exec="{sys.executable}" -m pasteup' in entry
    assert "Terminal=true" in entry


def test_desktop_entry_quoting_follows_the_specification() -> None:
    assert shortcut._desktop_exec_argument('/opt/my "py"/$HOME/100%') == '"/opt/my \\\\"py\\\\"/\\\\$HOME/100%%"'
