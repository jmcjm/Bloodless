"""GTK4/libadwaita window: python3 -m bloodless.gui [--demo]."""
import sys
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from . import actions, choices, config, dpi  # noqa: E402
from .actions import Key  # noqa: E402
from .blocks import BlockError  # noqa: E402
from .protocol import Mouse, WriteError  # noqa: E402
from .transport import DeviceError  # noqa: E402

BUTTON_TITLES = {"back": "Side button: back", "forward": "Side button: forward",
                 "top1": "Top button 1", "topn": "Top button N", "top3": "Top button 3"}
ERRORS = (DeviceError, BlockError, WriteError, ValueError)

# A full-size ANSI keyboard: each row is a list of (column, key, column span),
# 15 units wide, like the physical layout. Modifier keys toggle combinations;
# every other key is an ordinary key (at most one selected at a time).
KEYBOARD_ROWS = [
    [(0, "esc", 1)] + [(1 + i, f"f{1 + i}", 1) for i in range(12)],
    [(0, "`", 1)] + [(1 + i, str(1 + i), 1) for i in range(10)]
    + [(11, "-", 1), (12, "=", 1), (13, "backspace", 2)],
    [(0, "tab", 2)] + [(2 + i, "qwertyuiop"[i], 1) for i in range(10)]
    + [(12, "[", 1), (13, "]", 1), (14, "\\", 1)],
    [(0 + i, "asdfghjkl"[i], 1) for i in range(9)]
    + [(9, ";", 1), (10, "'", 1), (11, "enter", 4)],
    [(0, "shift", 3)] + [(3 + i, "zxcvbnm"[i], 1) for i in range(7)]
    + [(10, ",", 1), (11, ".", 1), (12, "/", 1)],
    [(0, "ctrl", 2), (2, "super", 2), (4, "alt", 2), (6, "space", 9)],
    [(12, "insert", 1), (13, "home", 1), (14, "pageup", 1)],
    [(12, "delete", 1), (13, "end", 1), (14, "pagedown", 1)],
    [(13, "up", 1)],
    [(12, "left", 1), (13, "down", 1), (14, "right", 1)],
]
MODIFIER_KEYS = ("ctrl", "shift", "alt", "super")
KEY_LABELS = {"esc": "Esc", "backspace": "Bksp", "tab": "Tab", "enter": "Enter",
              "shift": "Shift", "ctrl": "Ctrl", "alt": "Alt", "super": "Super",
              "space": "Space", "insert": "Ins", "home": "Home", "pageup": "PgUp",
              "delete": "Del", "end": "End", "pagedown": "PgDn",
              "up": "↑", "down": "↓", "left": "←", "right": "→"}
KEY_LABELS.update({f"f{n}": f"F{n}" for n in range(1, 13)})
# Compact keys so the whole keyboard fits the default window width.
KEY_CSS = "button.key { padding: 0 2px; min-width: 20px; min-height: 22px; font-size: 75%; }"


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


class KeyDialog(Adw.Dialog):
    """Pick a key combination by clicking keys on a picture of a keyboard."""

    def __init__(self, window, name):
        super().__init__(title="Choose keys")
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
        grid = Gtk.Grid(row_spacing=3, column_spacing=3)
        for r, row in enumerate(KEYBOARD_ROWS):
            for c, key, span in row:
                toggle = Gtk.ToggleButton(label=KEY_LABELS.get(key, key.upper()))
                toggle.add_css_class("key")
                grid.attach(toggle, c, r, span, 1)
                if key in MODIFIER_KEYS:
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
        buttons = Gtk.Box(spacing=6, halign=Gtk.Align.END)
        buttons.append(cancel)
        buttons.append(self.apply_button)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                        margin_top=8, margin_bottom=8, margin_start=8, margin_end=8)
        outer.append(grid)
        outer.append(buttons)
        self.set_child(outer)
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
        view = Adw.ToolbarView(content=self.toasts)
        view.add_top_bar(header)
        self.set_content(view)
        self.reload()

    def on_choice_changed(self, combo, _param, entry):
        entry.set_visible(combo.get_selected() == choices.KEY_INDEX)

    def new_key_dialog(self, name):
        return KeyDialog(self, name)

    def open_key_dialog(self, name):
        dialog = KeyDialog(self, name)
        dialog.present(self)
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
            return
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