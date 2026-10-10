import pytest

from bloodless import choices
from bloodless.actions import Disabled, Key, MouseButton, Raw, Special


@pytest.mark.parametrize("action, index, text", [
    (Disabled(), 0, ""), (MouseButton(0x08), 4, ""), (MouseButton(0x10), 5, ""),
    (Special(0x27), 6, ""), (Special(0x25), 7, ""),
    (Key(0x06, 0x01), choices.KEY_INDEX, "ctrl+c"), (Key(0x04), choices.KEY_INDEX, "a"),
    (Raw(0x262A, 0x262E), choices.CUSTOM_INDEX, ""),
])
def test_choice_for(action, index, text):
    assert choices.choice_for(action) == (index, text)


@pytest.mark.parametrize("action", [Disabled(), MouseButton(0x01), MouseButton(0x10),
                                    Special(0x27), Key(0x06, 0x01), Raw(0xC01C, 0x262E)])
def test_round_trip(action):
    index, text = choices.choice_for(action)
    assert choices.action_for(index, text, action) == action


def test_custom_keeps_the_original_action():
    original = Raw(0xC01C, 0x262E)
    assert choices.action_for(choices.CUSTOM_INDEX, "ignored", original) is original


def test_bad_key_text_raises_value_error():
    with pytest.raises(ValueError):
        choices.action_for(choices.KEY_INDEX, "ctrl+", Disabled())