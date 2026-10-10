import io

import pytest

from bloodless import cli, config
from bloodless.transport import DeviceError


@pytest.fixture(autouse=True)
def state_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    return tmp_path


def run(mouse, *argv):
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(list(argv), mouse=mouse, out=out, err=err)
    return code, out.getvalue(), err.getvalue()


def test_info(mouse):
    assert run(mouse, "info") == (0, "model 0x010 subtype 0 firmware F5\n", "")


def test_show(mouse):
    code, out, _err = run(mouse, "show")
    assert code == 0
    assert out.splitlines() == [
        "back     back", "forward  forward", "top1     dpi-up", "topn     dpi-down",
        "top3     custom (0x262a 0x262e)",
        "dpi 1    800 (selected)", "dpi 2    1000", "dpi 3    1200", "dpi 4    1600",
        "dpi 5    3200", "backlight 3"]


def test_set_button_writes_and_backs_up(mouse, state_home):
    code, out, _err = run(mouse, "set-button", "back", "key:ctrl+c")
    assert code == 0
    assert "back = key:ctrl+c" in out
    assert len(list((state_home / "bloodless" / "backups").iterdir())) == 1
    assert "back     key:ctrl+c" in run(mouse, "show")[1]


def test_set_dpi(mouse):
    assert run(mouse, "set-dpi", "4", "2100")[0] == 0
    assert "dpi 4    2100" in run(mouse, "show")[1]


def test_backlight(mouse):
    assert run(mouse, "backlight", "1") == (0, "backlight 1\n", "")
    assert run(mouse, "backlight") == (0, "backlight 1\n", "")


@pytest.mark.parametrize("argv", [("set-button", "back", "key:nope"), ("set-dpi", "9", "800"),
                                   ("set-dpi", "1", "850"), ("backlight", "7")])
def test_bad_input_is_an_error_message_and_writes_nothing(mouse, transport, argv):
    code, out, err = run(mouse, *argv)
    assert code == 1
    assert err.startswith("error: ")
    assert not [f for f in transport.sent if f[1] in (0x20, 0x2F)]


def test_missing_mouse_is_an_error_message(monkeypatch):
    def no_mouse():
        raise DeviceError("no Bloody mouse found (is it plugged in?)")

    monkeypatch.setattr(config, "open_mouse", no_mouse)
    out, err = io.StringIO(), io.StringIO()
    assert cli.main(["info"], out=out, err=err) == 1
    assert err.getvalue() == "error: no Bloody mouse found (is it plugged in?)\n"


def test_failed_readback_is_reported(mouse, transport):
    transport.corrupt_writes = True
    code, _out, err = run(mouse, "set-button", "back", "key:a")
    assert code == 1
    assert "readback" in err


def test_backup_then_restore_undoes_changes(mouse):
    _code, out, _err = run(mouse, "backup")
    path = out.strip()
    before = run(mouse, "show")[1]
    run(mouse, "set-button", "back", "key:ctrl+c")
    run(mouse, "set-dpi", "1", "400")
    assert run(mouse, "show")[1] != before
    code, out, _err = run(mouse, "restore", path)
    assert code == 0
    assert f"restored {path}" in out
    assert run(mouse, "show")[1] == before


@pytest.mark.parametrize("content", ["", "hello\n", "1a00: zz\n", "1a00: a4a4 ffff\n1b00: a4a4\n"])
def test_restore_rejects_files_that_are_not_backups(mouse, transport, tmp_path, content):
    path = tmp_path / "bad.txt"
    path.write_text(content)
    transport.sent.clear()
    code, _out, err = run(mouse, "restore", str(path))
    assert code == 1
    assert err.startswith("error: ")
    assert not [f for f in transport.sent if f[1] in (0x20, 0x2F)]


def test_restore_missing_file_is_an_error_message(mouse, tmp_path):
    code, _out, err = run(mouse, "restore", str(tmp_path / "nope.txt"))
    assert code == 1
    assert err.startswith("error: ")