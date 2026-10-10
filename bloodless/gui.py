"""GTK4/libadwaita window: python3 -m bloodless.gui [--demo]."""
import sys
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk  # noqa: E402

from . import actions, choices, config, dpi, udev  # noqa: E402
from .actions import Key  # noqa: E402
from .blocks import BlockError  # noqa: E402
from .protocol import Mouse, WriteError  # noqa: E402
from .transport import AccessDenied, DeviceError  # noqa: E402

BUTTON_TITLES = {"back": "Side button: back", "forward": "Side button: forward",
                 "top1": "Top button 1", "topn": "Top button N", "top3": "Top button 3"}
ERRORS = (DeviceError, BlockError, WriteError, ValueError)

KEY_UNIT = 44  # pixels per keyboard unit, the pitch of a letter key
KEY_GAP = 4


def _row(y, x, *keys):
    """Place keys left to right from x; a key is a name or (name, width in units)."""
    placed = []
    for key in keys:
        name, width = key if isinstance(key, tuple) else (key, 1)
        placed.append((x, y, width, name))
        x += width
    return placed


# A standard ANSI (US / US International) tenkeyless keyboard as (x, y, width, key)
# in keyboard units: a 15 unit wide main block with the navigation cluster beside it.
# Modifier keys toggle combinations and appear on both sides; every other key is an
# ordinary key (at most one selected at a time).
MAIN_WIDTH = 15
NAV_X = MAIN_WIDTH + 0.5
KEYBOARD = (
    _row(0, 0, "esc") + _row(0, 2, "f1", "f2", "f3", "f4")
    + _row(0, 6.5, "f5", "f6", "f7", "f8") + _row(0, 11, "f9", "f10", "f11", "f12")
    + _row(0, NAV_X, "printscreen", "scrolllock", "pause")
    + _row(1.5, 0, "`", *"1234567890-=", ("backspace", 2))
    + _row(1.5, NAV_X, "insert", "home", "pageup")
    + _row(2.5, 0, ("tab", 1.5), *"qwertyuiop[]", ("\\", 1.5))
    + _row(2.5, NAV_X, "delete", "end", "pagedown")
    + _row(3.5, 0, ("capslock", 1.75), *"asdfghjkl;'", ("enter", 2.25))
    + _row(4.5, 0, ("shift", 2.25), *"zxcvbnm,./", ("shift", 2.75))
    + _row(4.5, NAV_X + 1, "up")
    + _row(5.5, 0, ("ctrl", 1.25), ("super", 1.25), ("alt", 1.25), ("space", 6.25),
           ("alt", 1.25), ("super", 1.25), ("menu", 1.25), ("ctrl", 1.25))
    + _row(5.5, NAV_X, "left", "down", "right")
)
MODIFIER_KEYS = ("ctrl", "shift", "alt", "super")
KEY_LABELS = {"esc": "Esc", "backspace": "Backspace", "tab": "Tab", "enter": "Enter",
              "capslock": "Caps Lock", "shift": "Shift", "ctrl": "Ctrl", "alt": "Alt",
              "super": "Super", "menu": "Menu", "space": "", "insert": "Ins",
              "home": "Home", "pageup": "PgUp", "delete": "Del", "end": "End",
              "pagedown": "PgDn", "printscreen": "PrtSc", "scrolllock": "ScrLk",
              "pause": "Pause", "up": "↑", "down": "↓", "left": "←", "right": "→"}
KEY_LABELS.update({f"f{n}": f"F{n}" for n in range(1, 13)})
# Keys get their size from the layout, not from the theme's button padding.
KEY_CSS = "button.key { padding: 0; min-width: 0; min-height: 0; font-weight: normal; }"


def _install_key_css():
    provider = Gtk.CssProvider()
    try:
        provider.load_from_string(KEY_CSS)
    except AttributeError:  # GTK < 4.12
        provider.load_from_data(KEY_CSS.encode())
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                              Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def demo_mouse():
    from .fake import FakeTransport

    fixtures = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

    def load(name):
        return [int(w, 16) for w in (fixtures / name).read_text().split()]

    return Mouse(FakeTransport(load("buttons_ef_original.hex"), load("sens_ef_original.hex")),
                 sleep=lambda seconds: None)


class KeyDialog(Adw.Window):
    """Pick a key combination by clicking keys on a picture of a keyboard.

    A window of its own, so the keyboard is not squeezed into the narrow main window.
    """

    def __init__(self, window, name):
        super().__init__(title="Choose keys", transient_for=window, modal=True,
                         resizable=False)
        self.window, self.name = window, name
        self.mod_toggles, self.key_toggles = {}, {}
        mods, key_name = [], None
        text = window.button_rows[name][1].get_text().strip()
        if text:
            try:
                action = actions.parse("key:" + text)
            except ValueError:
                action = None
            if isinstance(action, Key):
                mods = [n for n, b in actions.MOD_BITS.items() if action.modifiers & b]
                key_name = next((n for n, u in actions.KEYS.items() if u == action.usage), None)
                if not mods and key_name in MODIFIER_KEYS:  # a lone modifier, e.g. "ctrl"
                    mods, key_name = [key_name], None
        _install_key_css()
        self.keyboard = Gtk.Fixed(halign=Gtk.Align.CENTER)
        for x, y, width, key in KEYBOARD:
            toggle = Gtk.ToggleButton(label=KEY_LABELS.get(key, key.upper()))
            toggle.add_css_class("key")
            toggle.set_size_request(int(width * KEY_UNIT) - KEY_GAP, KEY_UNIT - KEY_GAP)
            self.keyboard.put(toggle, int(x * KEY_UNIT), int(y * KEY_UNIT))
            if key in self.mod_toggles:  # the right-hand twin of a modifier
                self.mod_toggles[key].bind_property(
                    "active", toggle, "active",
                    GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE)
            elif key in MODIFIER_KEYS:
                self.mod_toggles[key] = toggle
                toggle.set_active(key in mods)
                toggle.connect("toggled", self._on_toggled)
            else:
                self.key_toggles[key] = toggle
                toggle.set_active(key == key_name)
                toggle.connect("toggled", self._on_key_toggled)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _b: self.close())
        self.apply_button = Gtk.Button(label="Apply", css_classes=["suggested-action"])
        self.apply_button.connect("clicked", lambda _b: self.write_back())
        header = Adw.HeaderBar(show_start_title_buttons=False, show_end_title_buttons=False)
        header.pack_start(cancel)
        header.pack_end(self.apply_button)
        self.keyboard.set_margin_top(12)
        self.keyboard.set_margin_bottom(12)
        self.keyboard.set_margin_start(12)
        self.keyboard.set_margin_end(12)
        view = Adw.ToolbarView(content=self.keyboard)
        view.add_top_bar(header)
        self.set_content(view)
        escape = Gtk.ShortcutController()
        escape.add_shortcut(Gtk.Shortcut(trigger=Gtk.ShortcutTrigger.parse_string("Escape"),
                                         action=Gtk.NamedAction.new("window.close")))
        self.add_controller(escape)
        self._update()

    def _on_key_toggled(self, toggle):
        if toggle.get_active():  # at most one ordinary key at a time
            for other in self.key_toggles.values():
                if other is not toggle:
                    other.set_active(False)
        self._update()

    def _on_toggled(self, _toggle):
        self._update()

    def _update(self):
        self.apply_button.set_sensitive(bool(self.combo_text()))

    def combo_text(self):
        """The selected combination as text for the entry row, e.g. 'ctrl+shift+t'."""
        mods = [n for n in MODIFIER_KEYS if self.mod_toggles[n].get_active()]
        keys = [n for n, t in self.key_toggles.items() if t.get_active()]
        return "+".join(mods + keys[:1])

    def write_back(self):
        text = self.combo_text()
        if text:
            self.window.button_rows[self.name][1].set_text(text)
        self.close()


class Window(Adw.ApplicationWindow):
    DEFAULT_WIDTH = 520
    DEFAULT_HEIGHT = 760

    def __init__(self, app, open_mouse):
        super().__init__(application=app, title="Bloodless", default_width=self.DEFAULT_WIDTH,
                         default_height=self.DEFAULT_HEIGHT)
        self.open_mouse = open_mouse
        self.mouse = None
        self.busy = False
        self.level_reports = True

        apply_button = Gtk.Button(label="Apply", css_classes=["suggested-action"])
        apply_button.connect("clicked", lambda _b: self.apply())
        reload_button = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Reload")
        reload_button.connect("clicked", lambda _b: self.reload())
        self.apply_button, self.reload_button = apply_button, reload_button
        self.spinner = Gtk.Spinner()
        self.spinner.set_visible(False)  # GTK4 widgets are visible by default
        header = Adw.HeaderBar()
        header.pack_start(self.spinner)
        header.pack_start(reload_button)
        header.pack_end(apply_button)

        self.device_row = Adw.ActionRow(title="Mouse")
        device_group = Adw.PreferencesGroup(title="Device")
        device_group.add(self.device_row)

        button_group = Adw.PreferencesGroup(
            title="Buttons", description="Left, right and middle buttons are not editable.")
        labels = Gtk.StringList.new([label for label, _name in choices.PRESETS])
        self.button_rows = {}
        for name, title in BUTTON_TITLES.items():
            combo = Adw.ComboRow(title=title, model=labels)
            entry = Adw.EntryRow(title="Key combination, e.g. ctrl+c")
            keys_button = Gtk.Button(label="Keys…", valign=Gtk.Align.CENTER)
            keys_button.connect("clicked", lambda _b, n=name: self.open_key_dialog(n))
            entry.add_suffix(keys_button)
            combo.connect("notify::selected", self.on_choice_changed, entry)
            button_group.add(combo)
            button_group.add(entry)
            self.button_rows[name] = (combo, entry)

        dpi_group = Adw.PreferencesGroup(
            title="DPI levels", description="Values above 1600 are approximate.")
        self.dpi_rows = []
        for n in range(1, 6):
            row = Adw.SpinRow.new_with_range(dpi.MIN_DPI, dpi.MAX_DPI, dpi.STEP)
            row.set_title(f"Level {n}")
            dpi_group.add(row)
            self.dpi_rows.append(row)

        self.backlight_row = Adw.SpinRow.new_with_range(0, 3, 1)
        self.backlight_row.set_title("Brightness")
        light_group = Adw.PreferencesGroup(title="Backlight")
        light_group.add(self.backlight_row)

        page = Adw.PreferencesPage()
        for group in (device_group, button_group, dpi_group, light_group):
            page.add(group)
        self.toasts = Adw.ToastOverlay(child=page)
        self.access_banner = Adw.Banner(title="Your user is not allowed to access the mouse",
                                        button_label="Grant access")
        self.access_banner.connect("button-clicked", lambda _b: self.install_udev_rule())
        view = Adw.ToolbarView(content=self.toasts)
        view.add_top_bar(header)
        view.add_top_bar(self.access_banner)
        self.set_content(view)
        self.reload()
        # Follow DPI button presses while the window is open.
        timer = GLib.timeout_add_seconds(1, self._tick)
        self.connect("close-request", lambda _w: GLib.source_remove(timer) and False)

    def on_choice_changed(self, combo, _param, entry):
        entry.set_visible(combo.get_selected() == choices.KEY_INDEX)

    def new_key_dialog(self, name):
        return KeyDialog(self, name)

    def open_key_dialog(self, name):
        dialog = KeyDialog(self, name)
        dialog.present()
        return dialog

    def _gtk_sleep(self, seconds):
        """Sleep like time.sleep, but keep the UI alive by pumping the main loop."""
        end = time.time() + seconds
        context = GLib.main_context_default()
        while time.time() < end:
            if context.pending():
                context.iteration(False)
            else:
                time.sleep(0.01)

    def _set_busy(self, busy):
        self.busy = busy
        self.spinner.set_visible(busy)
        self.spinner.set_spinning(busy)
        self.apply_button.set_sensitive(not busy)
        self.reload_button.set_sensitive(not busy)

    def toast(self, text):
        self.toasts.add_toast(Adw.Toast(title=text))

    def reload(self):
        try:
            self.mouse = self.open_mouse()
            self.mouse.sleep = self._gtk_sleep
            info = self.mouse.info()
            self.buttons = self.mouse.read_buttons()
            self.sens = self.mouse.read_sensitivity()
            self.backlight = self.mouse.get_backlight()
        except ERRORS as e:
            self.mouse = None
            self.device_row.set_subtitle(str(e))
            self.access_banner.set_revealed(isinstance(e, AccessDenied))
            return
        self.access_banner.set_revealed(False)
        self.device_row.set_subtitle(
            f"model 0x{info['model']:03x}, firmware {info['firmware']:02X}")
        self.original = config.get_buttons(self.buttons)
        for name, (combo, entry) in self.button_rows.items():
            index, key_text = choices.choice_for(self.original[name])
            combo.set_selected(index)
            entry.set_text(key_text)
            entry.set_visible(index == choices.KEY_INDEX)
        levels = config.get_dpi(self.sens)
        for n, row in enumerate(self.dpi_rows):
            row.set_visible(n < len(levels))
            if n < len(levels):
                row.set_value(levels[n])
        self.backlight_row.set_value(self.backlight)
        self.level_reports = True
        self.refresh_current_level()

    def install_udev_rule(self, spawn=None):
        """Install the udev rule with administrator rights, then try the mouse again."""
        self._set_busy(True)
        try:
            process = (spawn or self._spawn_on_host)(udev.install_command())
        except GLib.Error as e:
            self._udev_rule_done(f"could not ask for administrator rights: {e.message}")
            return
        process.communicate_utf8_async(None, None, self._on_udev_rule_exit)

    def _spawn_on_host(self, argv):
        launcher = Gio.SubprocessLauncher.new(Gio.SubprocessFlags.STDERR_PIPE)
        launcher.set_environ([f"{k}={v}" for k, v in udev.host_env().items()])
        return launcher.spawnv(argv)

    def _on_udev_rule_exit(self, process, result):
        try:
            _ok, _out, stderr = process.communicate_utf8_finish(result)
        except GLib.Error as e:
            self._udev_rule_done(e.message)
            return
        status = process.get_exit_status() if process.get_if_exited() else 1
        self._udev_rule_done(udev.failure(status, stderr or ""))

    def _udev_rule_done(self, problem):
        self._set_busy(False)
        if problem:
            self.toast(f"Error: {problem}")
            return
        self.reload()
        if self.mouse is not None:
            self.toast("Access granted")

    def refresh_current_level(self):
        """Mark the DPI level the mouse is using."""
        if self.mouse is None or self.busy:  # never interleave with a block write
            return
        current = self.sens.selected
        if self.level_reports:
            try:
                reported = self.mouse.current_level()
            except ERRORS:
                return
            if reported is None:
                self.level_reports = False  # do not stall the UI asking a silent mouse
            elif reported < self.sens.count:
                current = reported
        for n, row in enumerate(self.dpi_rows):
            row.set_subtitle("In use" if n == current else "")

    def _tick(self):
        self.refresh_current_level()
        return True

    def apply(self):
        if self.mouse is None:
            self.toast("No mouse connected")
            return
        self._set_busy(True)
        try:
            wanted = {name: choices.action_for(combo.get_selected(), entry.get_text(),
                                               self.original[name])
                      for name, (combo, entry) in self.button_rows.items()}
            levels = [int(row.get_value()) for row in self.dpi_rows[:self.sens.count]]
            backlight = int(self.backlight_row.get_value())
            buttons_changed = wanted != self.original
            dpi_changed = levels != config.get_dpi(self.sens)
            if buttons_changed or dpi_changed:
                config.save_backup(self.mouse)
            if buttons_changed:
                for name, action in wanted.items():
                    if action != self.original[name]:
                        config.set_button(self.buttons, name, action)
                self.mouse.write_buttons(self.buttons)
            if dpi_changed:
                current = config.get_dpi(self.sens)
                for n, value in enumerate(levels, start=1):
                    if value != current[n - 1]:
                        config.set_dpi(self.sens, n, value)
                self.mouse.write_sensitivity(self.sens)
            if backlight != self.backlight:
                self.mouse.set_backlight(backlight)
            self.reload()
            self.toast("Saved to mouse")
        except ERRORS as e:
            self.toast(f"Error: {e}")
            self.reload()
        finally:
            self._set_busy(False)


def main(argv=None):
    argv = sys.argv if argv is None else argv
    open_mouse = config.open_mouse
    if "--demo" in argv:
        mouse = demo_mouse()
        open_mouse = lambda: mouse  # noqa: E731
    app = Adw.Application(application_id="io.github.jmcjm.Bloodless")
    app.connect("activate", lambda a: Window(a, open_mouse).present())
    return app.run([argv[0]])


if __name__ == "__main__":
    sys.exit(main())