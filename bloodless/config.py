"""What the user can change, expressed on top of the block models."""
import os
import time
from pathlib import Path

from . import actions, dpi
from .blocks import ButtonBlock, SensitivityBlock
from .protocol import Mouse
from .transport import DeviceError, HidrawTransport, find_devices

SUPPORTED_MODELS = {0x010}
# Button name -> slot in the button table. Left/right/middle are deliberately not editable.
BUTTONS = {"back": 3, "forward": 4, "top1": 8, "topn": 9, "top3": 10}


def open_mouse():
    devices = find_devices()
    if not devices:
        raise DeviceError("no Bloody mouse found (is it plugged in?)")
    first_error = None
    for path in devices:
        transport = None
        try:
            transport = HidrawTransport(path)
            mouse = Mouse(transport)
            check_supported(mouse.info())
        except OSError as e:
            if transport is not None:
                transport.close()
            if first_error is None:
                first_error = e
            continue
        return mouse
    raise first_error


def check_supported(info):
    if info["model"] not in SUPPORTED_MODELS:
        raise DeviceError(f"unsupported mouse model 0x{info['model']:03x}")


def get_buttons(block, profile=1):
    return {name: actions.decode(block, *block.get_slot(profile, slot))
            for name, slot in BUTTONS.items()}


def set_button(block, name, action, profile=1):
    if name not in BUTTONS:
        raise ValueError(f"unknown button {name!r}, expected one of {', '.join(BUTTONS)}")
    if profile != 1 and block.shares_table(profile):
        raise ValueError(f"profile {profile} shares its button table with another profile "
                         "(the vendor app splits the tables after its first remap); "
                         "edit profile 1 instead")
    block.set_slot(profile, BUTTONS[name], *actions.encode(block, action))


def get_dpi(sens):
    return [dpi.raw_to_dpi(*sens.get_level(i)) for i in range(sens.count)]


def set_dpi(sens, level, value):
    """level is 1-based, as shown to the user."""
    sens.set_level(level - 1, *dpi.dpi_to_raw(value))


def backup_dir():
    state = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return Path(state) / "bloodless" / "backups"


def save_backup(mouse, directory=None):
    """Dump both config blocks as stored in the mouse; returns the file written."""
    directory = Path(directory) if directory else backup_dir()
    directory.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = directory / f"{stamp}.txt"
    n = 1
    while path.exists():  # several backups within one second must not overwrite each other
        n += 1
        path = directory / f"{stamp}-{n}.txt"
    lines = []
    for base, count in ((SensitivityBlock.BASE, SensitivityBlock.WORDS),
                        (ButtonBlock.BASE, ButtonBlock.MAX_WORDS)):
        words = mouse.read_words(base, count)
        lines.append(f"{base:04x}: " + " ".join(f"{w:04x}" for w in words))
    path.write_text("\n".join(lines) + "\n")
    return path


def load_backup(path):
    """(SensitivityBlock, ButtonBlock) from a file written by save_backup."""
    blocks = {}
    for line in Path(path).read_text().splitlines():
        base, _, words = line.partition(":")
        try:
            blocks[int(base, 16)] = [int(word, 16) for word in words.split()]
        except ValueError:
            raise ValueError(f"{path} is not a bloodless backup file") from None
    if set(blocks) != {SensitivityBlock.BASE, ButtonBlock.BASE}:
        raise ValueError(f"{path} is not a bloodless backup file")
    for words in blocks.values():
        words[:2] = [0xFFFF, 0xFFFF]
    return SensitivityBlock(blocks[SensitivityBlock.BASE]), ButtonBlock(blocks[ButtonBlock.BASE])