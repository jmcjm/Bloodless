"""Command line interface: python3 -m bloodless.cli <command>."""
import argparse
import sys

from . import actions, config
from .blocks import BlockError
from .protocol import WriteError
from .transport import DeviceError


def build_parser():
    p = argparse.ArgumentParser(prog="bloodless",
                                description="Configure A4Tech Bloody V7/V7M mice.")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("info", help="show model and firmware")
    show = sub.add_parser("show", help="show buttons, DPI levels and backlight")
    show.add_argument("--profile", type=int, default=1, choices=(1, 2, 3))
    button = sub.add_parser("set-button", help="e.g. set-button back key:ctrl+c")
    button.add_argument("name", choices=sorted(config.BUTTONS))
    button.add_argument("action", help="disabled, left, right, middle, back, forward, dpi-up, "
                                       "dpi-down or key:[ctrl+][shift+][alt+][super+]KEY")
    button.add_argument("--profile", type=int, default=1, choices=(1, 2, 3))
    setdpi = sub.add_parser("set-dpi", help="e.g. set-dpi 2 1000")
    setdpi.add_argument("level", type=int)
    setdpi.add_argument("dpi", type=int)
    light = sub.add_parser("backlight", help="show or set backlight level 0-3")
    light.add_argument("level", type=int, nargs="?")
    sub.add_parser("backup", help="save both config blocks to a file")
    restore = sub.add_parser("restore", help="write back a file made by backup")
    restore.add_argument("path")
    return p


def run(args, mouse, out):
    if args.command == "info":
        i = mouse.info()
        print(f"model 0x{i['model']:03x} subtype {i['subtype']} firmware {i['firmware']:02X}",
              file=out)
    elif args.command == "show":
        for name, action in config.get_buttons(mouse.read_buttons(), args.profile).items():
            print(f"{name:8} {actions.describe(action)}", file=out)
        sens = mouse.read_sensitivity()
        selected = config.current_level(mouse, sens)
        for n, value in enumerate(config.get_dpi(sens), start=1):
            marker = " (selected)" if n - 1 == selected else ""
            print(f"dpi {n}    {value}{marker}", file=out)
        print(f"backlight {mouse.get_backlight()}", file=out)
    elif args.command == "set-button":
        action = actions.parse(args.action)
        block = mouse.read_buttons()
        print(f"backup: {config.save_backup(mouse)}", file=out)
        config.set_button(block, args.name, action, args.profile)
        mouse.write_buttons(block)
        print(f"{args.name} = {actions.describe(action)}", file=out)
    elif args.command == "set-dpi":
        sens = mouse.read_sensitivity()
        config.set_dpi(sens, args.level, args.dpi)
        print(f"backup: {config.save_backup(mouse)}", file=out)
        mouse.write_sensitivity(sens)
        print(f"dpi {args.level} = {config.get_dpi(sens)[args.level - 1]}", file=out)
    elif args.command == "backlight":
        if args.level is not None:
            mouse.set_backlight(args.level)
        print(f"backlight {mouse.get_backlight()}", file=out)
    elif args.command == "backup":
        print(config.save_backup(mouse), file=out)
    elif args.command == "restore":
        sens, buttons = config.load_backup(args.path)
        print(f"backup: {config.save_backup(mouse)}", file=out)
        mouse.write_sensitivity(sens)
        mouse.write_buttons(buttons)
        print(f"restored {args.path}", file=out)


def main(argv=None, mouse=None, out=sys.stdout, err=sys.stderr):
    args = build_parser().parse_args(argv)
    try:
        run(args, mouse or config.open_mouse(), out)
    except (DeviceError, BlockError, WriteError, ValueError, OSError) as e:
        print(f"error: {e}", file=err)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())