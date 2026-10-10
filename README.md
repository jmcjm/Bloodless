# Bloodless

Configure A4Tech Bloody V7 / V7M mice on Linux without the vendor's Windows software:
side buttons, the three top buttons, DPI levels and backlight brightness.

Supported: firmware family `V_P3305_010` (reported as model `0x010`). Other Bloody models are
refused; see `REVERSE_ENGINEERING.md` for how to add one.

## Install

Builds are attached to every [release](https://github.com/jmcjm/Bloodless/releases) and to
every run of the GitHub workflows:

- **Flatpak**: `flatpak install --user Bloodless.flatpak`, then `flatpak run io.github.jmcjm.Bloodless`.
- **AppImage**: `chmod +x Bloodless-*.AppImage`, then run it. Without arguments it opens the
  window; with arguments it is the command line (`./Bloodless-*.AppImage show`). It carries
  its own Python, GTK and C library; tested on Debian 12, Ubuntu 24.04 and Fedora 44 (the
  command line also on Debian 11).
- **From source**: Python 3.11+, and for the window PyGObject with GTK 4 and libadwaita 1.5+.

Whichever you use, your user must be allowed to open the mouse's hidraw node. If it is not,
the window shows a "Grant access" button and the command line suggests
`install-udev-rule`; both ask for administrator rights once and install the udev rule from
`data/70-bloodless.rules`, without replugging the mouse.

## Use

```sh
python3 -m bloodless                     # window
python3 -m bloodless.cli info
python3 -m bloodless.cli show
python3 -m bloodless.cli set-button back key:ctrl+c
python3 -m bloodless.cli set-button top1 dpi-up
python3 -m bloodless.cli set-dpi 2 1000
python3 -m bloodless.cli backlight 2
python3 -m bloodless.cli backup
python3 -m bloodless.cli install-udev-rule
python3 -m bloodless.cli restore ~/.local/state/bloodless/backups/20261010-220000.txt
```

Buttons: `back`, `forward`, `top1`, `topn`, `top3`. Actions: `disabled`, `left`, `right`,
`middle`, `back`, `forward`, `dpi-up`, `dpi-down`, `key:<combination>` such as `key:f5` or
`key:ctrl+shift+a`.

Every change first saves both config blocks to `~/.local/state/bloodless/backups/`.

DPI values are stored as sensor register pairs; the conversion is fitted to observed data.
Values up to 1600 are exact under that fit, higher ones may land up to 100 DPI away, and the
program shows the value it actually stored.

## Development

```sh
python3 -m pytest -q
python3 -m bloodless.gui --demo          # window on a simulated mouse
```

`PROTOCOL.md` documents the protocol, `REVERSE_ENGINEERING.md` how it was worked out.