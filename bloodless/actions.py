"""Button actions: decode slot words into objects, encode objects back, parse user text."""
from dataclasses import dataclass

from .blocks import BlockError

MOD_BITS = {"ctrl": 0x01, "shift": 0x02, "alt": 0x04, "super": 0x08}
MOUSE_BUTTONS = {"left": 0x01, "right": 0x02, "middle": 0x04, "back": 0x08, "forward": 0x10}
SPECIALS = {"dpi-up": 0x27, "dpi-down": 0x25}
NONE = 0x262E

KEYS = {chr(ord("a") + i): 0x04 + i for i in range(26)}
KEYS.update({str(d): 0x1E + (d - 1) % 10 for d in range(10)})
KEYS.update({f"f{n}": 0x39 + n for n in range(1, 13)})
KEYS.update({"enter": 0x28, "esc": 0x29, "backspace": 0x2A, "tab": 0x2B, "space": 0x2C,
             "insert": 0x49, "home": 0x4A, "pageup": 0x4B, "delete": 0x4C, "end": 0x4D,
             "pagedown": 0x4E, "right": 0x4F, "left": 0x50, "down": 0x51, "up": 0x52})
# Modifiers double as standalone keys (HID E0-E3), so a button can send Ctrl alone.
KEYS.update({"ctrl": 0xE0, "shift": 0xE1, "alt": 0xE2, "super": 0xE3})
KEYS.update({"`": 0x35, "-": 0x2D, "=": 0x2E, "[": 0x2F, "]": 0x30, "\\": 0x31,
             ";": 0x33, "'": 0x34, ",": 0x36, ".": 0x37, "/": 0x38})
_KEY_NAMES = {code: name for name, code in KEYS.items()}
_BUTTON_NAMES = {mask: name for name, mask in MOUSE_BUTTONS.items()}
_SPECIAL_NAMES = {code: name for name, code in SPECIALS.items()}


@dataclass(frozen=True)
class Disabled:
    pass


@dataclass(frozen=True)
class MouseButton:
    mask: int


@dataclass(frozen=True)
class Key:
    usage: int
    modifiers: int = 0


@dataclass(frozen=True)
class Special:
    code: int


@dataclass(frozen=True)
class Raw:
    """Anything this program does not model; kept verbatim."""
    press: int
    release: int


def decode(block, press, release):
    op, arg = press >> 8, press & 0xFF
    if (press, release) == (NONE, NONE):
        return Disabled()
    if op == 0x25 and release == 0x2400 | arg and arg in _BUTTON_NAMES:
        return MouseButton(arg)
    if op == 0x21 and release == 0x2000 | arg:
        return Key(arg)
    if op == 0x26 and release == NONE and arg in _SPECIAL_NAMES:
        return Special(arg)
    if op == 0xC0 and release >> 8 == 0xC0:
        try:
            down, up = block.read_sequence(arg), block.read_sequence(release & 0xFF)
        except BlockError:
            return Raw(press, release)
        if len(down) == 2 and down[0] >> 8 == 0x23 and down[1] >> 8 == 0x21:
            mods, usage = down[0] & 0xFF, down[1] & 0xFF
            if up == [0x2000 | usage, 0x2200 | mods]:
                return Key(usage, mods)
    return Raw(press, release)


def encode(block, action):
    """Return (press, release) words for action; may add sequences to block."""
    if isinstance(action, Disabled):
        return NONE, NONE
    if isinstance(action, MouseButton):
        return 0x2500 | action.mask, 0x2400 | action.mask
    if isinstance(action, Special):
        return 0x2600 | action.code, NONE
    if isinstance(action, Raw):
        return action.press, action.release
    if isinstance(action, Key):
        if not action.modifiers:
            return 0x2100 | action.usage, 0x2000 | action.usage
        down = block.add_sequence([0x2300 | action.modifiers, 0x2100 | action.usage])
        up = block.add_sequence([0x2000 | action.usage, 0x2200 | action.modifiers])
        return 0xC000 | down, 0xC000 | up
    raise TypeError(f"not an action: {action!r}")


def parse(text):
    """'disabled', 'back', 'dpi-up', 'key:ctrl+c', 'key:f5' -> action object."""
    text = text.strip().lower()
    if text == "disabled":
        return Disabled()
    if text in MOUSE_BUTTONS:
        return MouseButton(MOUSE_BUTTONS[text])
    if text in SPECIALS:
        return Special(SPECIALS[text])
    if text.startswith("key:"):
        *mods, key = text[4:].split("+")
        if key in KEYS and all(m in MOD_BITS for m in mods) and len(set(mods)) == len(mods):
            return Key(KEYS[key], sum(MOD_BITS[m] for m in mods))
    raise ValueError(f"unknown action: {text!r}")


def describe(action):
    """Inverse of parse for modelled actions; a readable label for the rest."""
    if isinstance(action, Disabled):
        return "disabled"
    if isinstance(action, MouseButton):
        return _BUTTON_NAMES[action.mask]
    if isinstance(action, Special):
        return _SPECIAL_NAMES[action.code]
    if isinstance(action, Key):
        mods = [name for name, bit in MOD_BITS.items() if action.modifiers & bit]
        if action.usage in _KEY_NAMES and not action.modifiers & ~0x0F:
            return "key:" + "+".join(mods + [_KEY_NAMES[action.usage]])
        return f"custom (key 0x{action.usage:02x}, modifiers 0x{action.modifiers:02x})"
    return f"custom (0x{action.press:04x} 0x{action.release:04x})"