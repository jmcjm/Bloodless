import gi
import pytest

gi.require_version("Adw", "1")
from gi.repository import Adw, GLib  # noqa: E402

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


def test_saving_is_visible_while_writing():
    def check(window, mouse):
        assert mouse.sleep == window._gtk_sleep      # the GUI pumps GTK while the mouse pauses
        assert not window.spinner.get_spinning()
        assert not window.spinner.get_visible()
        seen = []

        def spy(_seconds):
            seen.append((window.spinner.get_spinning(), window.spinner.get_visible(),
                         window.apply_button.get_sensitive(),
                         window.reload_button.get_sensitive()))

        mouse.sleep = spy
        window.button_rows["forward"][1].set_text("ctrl+shift+t")
        window.apply()
        assert seen
        assert all(spinning and visible and not apply_sensitive and not reload_sensitive
                   for spinning, visible, apply_sensitive, reload_sensitive in seen)
        assert not window.spinner.get_spinning()
        assert not window.spinner.get_visible()
        assert window.apply_button.get_sensitive()
        assert window.reload_button.get_sensitive()
        assert described(mouse)["forward"] == "key:ctrl+shift+t"

    drive(check)


def test_failed_apply_stops_the_spinner_and_unlocks_the_buttons():
    def check(window, mouse):
        window.button_rows["forward"][1].set_text("garbage+")
        window.apply()
        assert not window.spinner.get_spinning()
        assert not window.spinner.get_visible()
        assert window.apply_button.get_sensitive()
        assert window.reload_button.get_sensitive()

    drive(check)


def test_the_save_pause_pumps_the_main_loop():
    def check(window, mouse):
        ran = []

        def idle():
            ran.append(True)
            return GLib.SOURCE_REMOVE

        GLib.idle_add(idle)
        window._gtk_sleep(0.05)
        assert ran == [True]

    drive(check)


def test_key_dialog_fits_the_default_window_width():
    def check(window, _mouse):
        window.button_rows["forward"][1].set_text("")
        dialog = window.new_key_dialog("forward")
        _minimum, natural = dialog.get_child().get_preferred_size()
        assert natural.width <= gui.Window.DEFAULT_WIDTH
        assert natural.height <= gui.Window.DEFAULT_HEIGHT

    drive(check)


def test_key_dialog_builds_a_combo_from_toggles():
    def check(window, _mouse):
        window.button_rows["forward"][1].set_text("")   # open on an empty combination
        dialog = window.new_key_dialog("forward")
        assert dialog.combo_text() == ""                  # nothing selected, Apply disabled
        assert not dialog.apply_button.get_sensitive()
        dialog.mod_toggles["ctrl"].set_active(True)
        dialog.mod_toggles["shift"].set_active(True)
        dialog.key_toggles["t"].set_active(True)
        assert dialog.combo_text() == "ctrl+shift+t"
        assert dialog.apply_button.get_sensitive()
        dialog.key_toggles["y"].set_active(True)         # a second key deselects the first
        assert dialog.combo_text() == "ctrl+shift+y"
        assert not dialog.key_toggles["t"].get_active()
        dialog.key_toggles["y"].set_active(False)
        dialog.mod_toggles["shift"].set_active(False)
        assert dialog.combo_text() == "ctrl"              # a modifier alone is a valid combo

    drive(check)


def test_key_dialog_presets_the_current_entry_text():
    def check(window, _mouse):
        window.button_rows["forward"][1].set_text("ctrl+shift+t")
        dialog = window.new_key_dialog("forward")
        assert dialog.mod_toggles["ctrl"].get_active()
        assert dialog.mod_toggles["shift"].get_active()
        assert not dialog.mod_toggles["alt"].get_active()
        assert dialog.key_toggles["t"].get_active()
        assert not dialog.key_toggles["y"].get_active()

    drive(check)


def test_keys_dialog_apply_writes_the_choice_to_the_entry():
    def check(window, mouse):
        dialog = window.new_key_dialog("forward")
        dialog.mod_toggles["ctrl"].set_active(True)
        dialog.key_toggles["v"].set_active(True)
        dialog.apply_button.emit("clicked")
        assert window.button_rows["forward"][1].get_text() == "ctrl+v"
        window.apply()
        assert described(mouse)["forward"] == "key:ctrl+v"