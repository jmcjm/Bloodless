import io
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from bloodless import cli, config, udev
from bloodless.transport import AccessDenied, DeviceError, HidrawTransport


def test_rule_matches_the_file_shipped_for_manual_installs():
    shipped = Path(__file__).parent.parent / "data" / "70-bloodless.rules"
    assert shipped.read_text().strip() == udev.RULE


def test_script_writes_the_rule_and_reloads_udev(tmp_path):
    """Run the real shell script, as an ordinary user, against stand-ins for root's world."""
    rule_path = tmp_path / "70-bloodless.rules"
    calls = tmp_path / "calls"
    (tmp_path / "udevadm").write_text(f'#!/bin/sh\necho "$@" >> "{calls}"\n')
    (tmp_path / "udevadm").chmod(0o755)
    env = {"PATH": f"{tmp_path}:{os.environ['PATH']}"}
    subprocess.run(["sh", "-c", udev.script(str(rule_path))], env=env, check=True)
    assert rule_path.read_text() == udev.RULE + "\n"
    assert calls.read_text().splitlines() == [
        "control --reload", "trigger --subsystem-match=hidraw --settle"]


def test_script_does_not_reload_when_the_rule_cannot_be_written(tmp_path):
    calls = tmp_path / "calls"
    (tmp_path / "udevadm").write_text(f'#!/bin/sh\necho "$@" >> "{calls}"\n')
    (tmp_path / "udevadm").chmod(0o755)
    env = {"PATH": f"{tmp_path}:{os.environ['PATH']}"}
    done = subprocess.run(["sh", "-c", udev.script(str(tmp_path / "missing" / "x.rules"))],
                          env=env, capture_output=True)
    assert done.returncode != 0
    assert not calls.exists()


def test_install_command_uses_pkexec(monkeypatch):
    monkeypatch.setattr(os.path, "exists", lambda path: False)
    assert udev.install_command() == ["pkexec", "sh", "-c", udev.script()]


def test_install_command_escapes_the_flatpak_sandbox(monkeypatch):
    monkeypatch.setattr(os.path, "exists", lambda path: path == "/.flatpak-info")
    assert udev.install_command()[:3] == ["flatpak-spawn", "--host", "pkexec"]


def test_host_env_drops_what_an_appimage_sets():
    env = udev.host_env({"HOME": "/home/u", "DISPLAY": ":0", "LD_LIBRARY_PATH": "/tmp/x/lib",
                         "LD_PRELOAD": "hooks.so", "PYTHONHOME": "/tmp/x/usr",
                         "GI_TYPELIB_PATH": "/tmp/x", "APPDIR": "/tmp/x", "PATH": "/tmp/x/bin"})
    assert env == {"HOME": "/home/u", "DISPLAY": ":0", "PATH": udev.HOST_PATH}


@pytest.mark.parametrize("code, stderr, expected", [
    (0, "", None),
    (126, "Request dismissed", "administrator rights were not granted"),
    (127, "", "administrator rights were not granted"),
    (1, "sh: cannot create /etc/udev/rules.d/x: Read-only file system\n", "Read-only file system"),
    (2, "", "exit code 2"),
])
def test_failure_messages(code, stderr, expected):
    message = udev.failure(code, stderr)
    assert message is None if expected is None else expected in message


def test_install_runs_the_command_with_a_clean_environment():
    seen = {}

    def run(argv, env, capture_output, text):
        seen.update(argv=argv, env=env)
        return SimpleNamespace(returncode=0, stderr="")

    udev.install(run)
    assert seen["argv"] == udev.install_command()
    assert seen["env"]["PATH"] == udev.HOST_PATH


def test_install_reports_a_dismissed_password_prompt():
    with pytest.raises(DeviceError, match="not granted"):
        udev.install(lambda *a, **k: SimpleNamespace(returncode=126, stderr=""))


def test_install_without_pkexec_tells_how_to_do_it_by_hand():
    def run(*args, **kwargs):
        raise FileNotFoundError("pkexec")

    with pytest.raises(DeviceError, match="70-bloodless.rules"):
        udev.install(run)


def test_opening_a_node_without_permission_is_access_denied(monkeypatch):
    def refuse(path, flags):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(os, "open", refuse)
    with pytest.raises(AccessDenied, match="/dev/hidraw5: Permission denied"):
        HidrawTransport("/dev/hidraw5")


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    return cli.main(list(argv), out=out, err=err), out.getvalue(), err.getvalue()


def test_cli_hints_at_the_fix_when_access_is_denied(monkeypatch):
    def denied():
        raise AccessDenied("cannot open /dev/hidraw5: Permission denied")

    monkeypatch.setattr(config, "open_mouse", denied)
    assert run_cli("info") == (1, "", "error: cannot open /dev/hidraw5: Permission denied\n"
                               "Run the install-udev-rule command to grant access.\n")


def test_cli_install_udev_rule_does_not_need_the_mouse(monkeypatch):
    monkeypatch.setattr(config, "open_mouse", lambda: pytest.fail("mouse was opened"))
    monkeypatch.setattr(udev, "install", lambda: None)
    assert run_cli("install-udev-rule") == (0, f"installed {udev.RULE_PATH}\n", "")


def test_cli_install_udev_rule_reports_failure(monkeypatch):
    def fail():
        raise DeviceError("administrator rights were not granted")

    monkeypatch.setattr(udev, "install", fail)
    assert run_cli("install-udev-rule") == (1, "", "error: administrator rights were not granted\n")
