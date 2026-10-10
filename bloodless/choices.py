"""Mapping between button actions and the rows of the GUI drop-down."""
from . import actions

# (label, action text understood by actions.parse); "key" needs the text field.
PRESETS = [
    ("Disabled", "disabled"),
    ("Left click", "left"),
    ("Right click", "right"),
    ("Middle click", "middle"),
    ("Back", "back"),
    ("Forward", "forward"),
    ("DPI up", "dpi-up"),
    ("DPI down", "dpi-down"),
    ("Key combination", "key"),
    ("Custom (keep as is)", "custom"),
]
KEY_INDEX = 8
CUSTOM_INDEX = 9


def choice_for(action):
    """(index into PRESETS, text for the key field) describing action."""
    text = actions.describe(action)
    if text.startswith("key:"):
        return KEY_INDEX, text[4:]
    for index, (_label, name) in enumerate(PRESETS):
        if name == text:
            return index, ""
    return CUSTOM_INDEX, ""


def action_for(index, key_text, original):
    """Action for the selected row; original is what the mouse currently has."""
    if index == CUSTOM_INDEX:
        return original
    if index == KEY_INDEX:
        return actions.parse("key:" + key_text)
    return actions.parse(PRESETS[index][1])