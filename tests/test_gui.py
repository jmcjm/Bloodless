import gi
import pytest

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

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


def test_keyboard_is_a_standard_ansi_layout():
    rows = {}
    for x, y, width, key in gui.KEYBOARD:
        assert key in actions.KEYS
        if x < gui.MAIN_WIDTH:
            rows.setdefault(y, []).append((x, width, key))
    function_row, *block = [rows[y] for y in sorted(rows)]
    assert [key for _x, _width, key in function_row] == ["esc"] + [f"f{n}" for n in range(1, 13)]
    for row in block:                                    # no gaps, no overlaps, 15 units wide
        edge = 0
        for x, width, _key in row:
            assert x == edge
            edge += width
        assert edge == gui.MAIN_WIDTH
    assert [[(key, width) for _x, width, key in row if width != 1] for row in block] == [
        [("backspace", 2)],
        [("tab", 1.5), ("\\", 1.5)],
        [("capslock", 1.75), ("enter", 2.25)],
        [("shift", 2.25), ("shift", 2.75)],
        [("ctrl", 1.25), ("super", 1.25), ("alt", 1.25), ("space", 6.25),
         ("alt", 1.25), ("super", 1.25), ("menu", 1.25), ("ctrl", 1.25)]]
    assert "".join(key for row in block for _x, _width, key in row if len(key) == 1) == (
        "`1234567890-=qwertyuiop[]\\asdfghjkl;'zxcvbnm,./")


def test_key_dialog_is_a_window_of_its_own_with_full_size_keys():
    def check(window, _mouse):
        dialog = window.new_key_dialog("forward")
        assert isinstance(dialog, Gtk.Window)            # not clipped by the main window
        assert dialog.get_transient_for() is window
        assert dialog.get_modal()
        _minimum, natural = dialog.keyboard.get_preferred_size()
        assert natural.width > gui.Window.DEFAULT_WIDTH
        toggle = dialog.keyboard.get_first_child()
        count = 0
        while toggle is not None:                        # no label pushes a key past its slot
            wanted_width, wanted_height = toggle.get_size_request()
            _minimum, natural = toggle.get_preferred_size()
            assert (natural.width, natural.height) == (wanted_width, wanted_height)
            assert wanted_width >= 40 and wanted_height >= 40
            count += 1
            toggle = toggle.get_next_sibling()
        assert count == len(gui.KEYBOARD)

    drive(check)


def test_key_dialog_right_hand_modifiers_mirror_the_left_ones():
    def check(window, _mouse):
        window.button_rows["forward"][1].set_text("shift+a")
        dialog = window.new_key_dialog("forward")
        twins = {}
        toggle = dialog.keyboard.get_first_child()
        while toggle is not None:
            twins.setdefault(toggle.get_label(), []).append(toggle)
            toggle = toggle.get_next_sibling()
        for label in ("Ctrl", "Shift", "Alt", "Super"):
            assert len(twins[label]) == 2
        assert all(toggle.get_active() for toggle in twins["Shift"])
        left, right = twins["Ctrl"]
        right.set_active(True)
        assert left.get_active()
        assert dialog.combo_text() == "ctrl+shift+a"
        left.set_active(False)
        assert not right.get_active()
        assert dialog.combo_text() == "shift+a"

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

def test_dpi_level_in_use_is_marked_and_follows_the_mouse():
    def check(window, mouse):
        marks = lambda: [row.get_subtitle() for row in window.dpi_rows]  # noqa: E731
        assert marks() == ["", "", "", "", "In use"]  # the fixture has level 5 selected
        mouse.t.level = 1
        window.refresh_current_level()
        assert marks() == ["", "In use", "", "", ""]

    drive(check)


def test_level_refresh_never_runs_during_a_write():
    def check(window, mouse):
        window.busy = True
        mouse.t.sent.clear()
        window.refresh_current_level()
        assert mouse.t.sent == []

    drive(check)


def test_silent_mouse_is_asked_only_once():
    def check(window, mouse):
        mouse.t.silent = True
        window.reload()
        asked = len([f for f in mouse.t.sent if f[1] == 0x0C])
        window.refresh_current_level()
        window.refresh_current_level()
        assert len([f for f in mouse.t.sent if f[1] == 0x0C]) == asked
        assert [row.get_subtitle() for row in window.dpi_rows] == ["", "", "", "", "In use"]

    drive(check)


def window_without_access(application):
    """A window whose mouse refuses access until the udev rule is 'installed'."""
    from bloodless.transport import AccessDenied

    mouse = gui.demo_mouse()
    state = {"granted": False}

    def open_mouse():
        if not state["granted"]:
            raise AccessDenied("cannot open /dev/hidraw5: Permission denied")
        return mouse

    return gui.Window(application, open_mouse), state


class FakeProcess:
    """Stands in for the pkexec process: finishes at once with the given exit status."""

    def __init__(self, status, stderr="", on_run=None):
        self.status, self.stderr, self.on_run = status, stderr, on_run

    def communicate_utf8_async(self, _stdin, _cancellable, callback):
        if self.on_run:
            self.on_run()
        callback(self, None)

    def communicate_utf8_finish(self, _result):
        return True, None, self.stderr

    def get_if_exited(self):
        return True

    def get_exit_status(self):
        return self.status


def run_in_app(check):
    app = Adw.Application(application_id="io.github.jmcjm.BloodlessTest")
    failures = []

    def activate(application):
        try:
            check(application)
        except Exception as e:
            failures.append(e)
        application.quit()

    app.connect("activate", activate)
    app.run([])
    if failures:
        raise failures[0]


def test_banner_offers_to_grant_access_only_when_access_is_denied():
    def check(application):
        window, _state = window_without_access(application)
        assert window.access_banner.get_revealed()
        assert "Permission denied" in window.device_row.get_subtitle()
        assert not gui.Window(application, gui.demo_mouse).access_banner.get_revealed()

    run_in_app(check)


def test_granting_access_installs_the_rule_and_loads_the_mouse():
    def check(application):
        window, state = window_without_access(application)
        spawned = []

        def spawn(argv):
            spawned.append(argv)
            return FakeProcess(0, on_run=lambda: state.update(granted=True))

        window.install_udev_rule(spawn)
        assert spawned == [gui.udev.install_command()]
        assert window.mouse is not None
        assert not window.access_banner.get_revealed()
        assert not window.busy
        assert window.device_row.get_subtitle() == "model 0x010, firmware F5"

    run_in_app(check)


def test_dismissed_password_prompt_keeps_the_banner_and_unlocks_the_window():
    def check(application):
        window, _state = window_without_access(application)
        window.install_udev_rule(lambda argv: FakeProcess(126, "Request dismissed"))
        assert window.mouse is None
        assert window.access_banner.get_revealed()
        assert not window.busy
        assert window.apply_button.get_sensitive()

    run_in_app(check)


def test_missing_pkexec_is_reported_and_unlocks_the_window():
    def check(application):
        window, _state = window_without_access(application)

        def spawn(argv):
            raise GLib.Error("Failed to execute child process “pkexec”")

        window.install_udev_rule(spawn)
        assert not window.busy
        assert window.access_banner.get_revealed()

    run_in_app(check)


def test_granting_access_runs_a_real_process_without_blocking_the_window():
    """The real spawn path, with a harmless command in place of pkexec."""
    def check(application):
        window, _state = window_without_access(application)
        window.install_udev_rule(
            lambda argv: window._spawn_on_host(["sh", "-c", "echo no such luck >&2; exit 3"]))
        assert window.busy  # the call returned while the process is still being waited for
        context = GLib.main_context_default()
        deadline = GLib.get_monotonic_time() + 5_000_000
        while window.busy and GLib.get_monotonic_time() < deadline:
            context.iteration(True)
        assert not window.busy
        assert window.access_banner.get_revealed()

    run_in_app(check)
