import gi
import pytest

gi.require_version("Adw", "1")
from gi.repository import Adw  # noqa: E402

from bloodless import actions, choices, config, gui  # noqa: E402


@pytest.fixture(autouse=True)
def state_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))


def drive(callback):
    """Build a Window on a demo mouse inside a running application, without showing it."""
    mouse = gui.demo_mouse()
    app = Adw.Application(application_id="io.github.jmcjm.BloodlessTest")
    failures = []

    def activate(application):
        try:
            callback(gui.Window(application, lambda: mouse), mouse)
        except Exception as e:  # surface assertion errors after the main loop ends
            failures.append(e)
        application.quit()

    app.connect("activate", activate)
    app.run([])
    if failures:
        raise failures[0]


def described(mouse):
    return {name: actions.describe(action)
            for name, action in config.get_buttons(mouse.read_buttons()).items()}


def test_window_shows_what_the_mouse_has():
    def check(window, mouse):
        assert window.device_row.get_subtitle() == "model 0x010, firmware F5"
        combo, entry = window.button_rows["back"]
        assert (combo.get_selected(), entry.get_text(), entry.get_visible()) == (
            choices.KEY_INDEX, "ctrl+c", True)
        combo, entry = window.button_rows["top1"]
        assert (combo.get_selected(), entry.get_visible()) == (choices.CUSTOM_INDEX, False)
        assert [row.get_value() for row in window.dpi_rows] == [600, 1000, 1600, 2400, 3200]

    drive(check)


def test_apply_writes_only_what_changed():
    def check(window, mouse):
        combo, entry = window.button_rows["forward"]
        entry.set_text("ctrl+shift+z")
        window.button_rows["top1"][0].set_selected(6)
        window.dpi_rows[0].set_value(400)
        window.backlight_row.set_value(1)
        window.apply()
        assert described(mouse) == {
            "back": "key:ctrl+c", "forward": "key:ctrl+shift+z", "top1": "dpi-up",
            "topn": "custom (0x2611 0x262e)", "top3": "custom (0x2612 0x262e)"}
        assert config.get_dpi(mouse.read_sensitivity()) == [400, 1000, 1600, 2400, 3200]
        assert mouse.get_backlight() == 1

    drive(check)


def test_apply_with_bad_key_text_writes_nothing():
    def check(window, mouse):
        before = described(mouse)
        mouse.t.sent.clear()
        window.button_rows["forward"][1].set_text("garbage+")
        window.apply()
        assert described(mouse) == before
        assert not [frame for frame in mouse.t.sent if frame[1] == 0x20]

    drive(check)


def test_apply_without_changes_writes_nothing():
    def check(window, mouse):
        mouse.t.sent.clear()
        window.apply()
        assert not [frame for frame in mouse.t.sent if frame[1] == 0x20]

    drive(check)


def test_window_without_mouse_shows_the_error():
    from bloodless.transport import DeviceError

    def no_mouse():
        raise DeviceError("no Bloody mouse found (is it plugged in?)")

    app = Adw.Application(application_id="io.github.jmcjm.BloodlessTest")
    seen = []

    def activate(application):
        window = gui.Window(application, no_mouse)
        seen.append(window.device_row.get_subtitle())
        window.apply()
        application.quit()

    app.connect("activate", activate)
    app.run([])
    assert seen == ["no Bloody mouse found (is it plugged in?)"]