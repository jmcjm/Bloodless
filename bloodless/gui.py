"""GTK4/libadwaita window: python3 -m bloodless.gui [--demo]."""
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from . import choices, config, dpi  # noqa: E402
from .blocks import BlockError  # noqa: E402
from .protocol import Mouse, WriteError  # noqa: E402
from .transport import DeviceError  # noqa: E402

BUTTON_TITLES = {"back": "Side button: back", "forward": "Side button: forward",
                 "top1": "Top button 1", "topn": "Top button N", "top3": "Top button 3"}
ERRORS = (DeviceError, BlockError, WriteError, ValueError)


def demo_mouse():
    from .fake import FakeTransport

    fixtures = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

    def load(name):
        return [int(w, 16) for w in (fixtures / name).read_text().split()]

    return Mouse(FakeTransport(load("buttons_ef_original.hex"), load("sens_ef_original.hex")),
                 sleep=lambda seconds: None)


class Window(Adw.ApplicationWindow):
    def __init__(self, app, open_mouse):
        super().__init__(application=app, title="Bloodless", default_width=520, default_height=760)
        self.open_mouse = open_mouse
        self.mouse = None

        apply_button = Gtk.Button(label="Apply", css_classes=["suggested-action"])
        apply_button.connect("clicked", lambda _b: self.apply())
        reload_button = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Reload")
        reload_button.connect("clicked", lambda _b: self.reload())
        header = Adw.HeaderBar()
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

    def toast(self, text):
        self.toasts.add_toast(Adw.Toast(title=text))

    def reload(self):
        try:
            self.mouse = self.open_mouse()
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
        except ERRORS as e:
            self.toast(f"Error: {e}")
            self.reload()
            return
        self.reload()
        self.toast("Saved to mouse")


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