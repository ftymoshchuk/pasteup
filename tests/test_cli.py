import subprocess
import sys

import pytest

from pasteup import __version__, cli


def test_version_flag_prints_the_package_version(capsys) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--version"])

    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"pasteup {__version__}"


def test_serves_the_app_on_this_machine_by_default(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr("uvicorn.run", lambda app, **kwargs: calls.append((app, kwargs)))

    cli.main([])

    assert calls == [("pasteup.main:app", {"host": "127.0.0.1", "port": 8000, "reload": False})]


def test_warns_when_listening_beyond_this_machine(monkeypatch, capsys) -> None:
    monkeypatch.setattr("uvicorn.run", lambda app, **kwargs: None)

    cli.main(["--host", "0.0.0.0", "--port", "9000"])

    assert "See SECURITY.md" in capsys.readouterr().err


def test_python_dash_m_runs_the_same_command() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pasteup", "--version"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == f"pasteup {__version__}"
