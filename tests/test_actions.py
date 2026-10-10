import pytest

from bloodless import actions
from bloodless.actions import Disabled, Key, MouseButton, Raw, Special
from bloodless.blocks import ButtonBlock
from conftest import load


def decoded(fixture, slot, profile=1):
    block = ButtonBlock(load(fixture))
    return actions.decode(block, *block.get_slot(profile, slot))


def test_decode_default_block():
    assert decoded("buttons_f5_default", 0) == MouseButton(0x01)
    assert decoded("buttons_f5_default", 3) == MouseButton(0x08)
    assert decoded("buttons_f5_default", 4) == MouseButton(0x10)
    assert decoded("buttons_f5_default", 5) == Disabled()
    assert decoded("buttons_f5_default", 8) == Special(0x27)
    assert decoded("buttons_f5_default", 9) == Special(0x25)
    assert decoded("buttons_f5_default", 10) == Raw(0x262A, 0x262E)


def test_decode_plain_keys_written_by_vendor_app():
    assert decoded("buttons_f5_forward_a_back_b_one_c", 4) == Key(0x04)
    assert decoded("buttons_f5_forward_a_back_b_one_c", 3) == Key(0x05)
    assert decoded("buttons_f5_forward_a_back_b_one_c", 8) == Key(0x06)


def test_decode_key_combinations_from_a_real_mouse():
    assert decoded("buttons_f3_mouse2", 3) == Key(0x06, 0x01)   # Ctrl+C
    assert decoded("buttons_f3_mouse2", 4) == Key(0x19, 0x01)   # Ctrl+V
    assert decoded("buttons_f3_mouse2", 8) == Key(0x16, 0x01)   # Ctrl+S


def test_decode_unknown_sequence_stays_raw():
    assert decoded("buttons_ef_original", 6) == Raw(0xC01C, 0x262E)


def test_encode_simple_actions_do_not_touch_the_block():
    block = ButtonBlock(load("buttons_f5_default"))
    before = block.to_words()
    assert actions.encode(block, Disabled()) == (0x262E, 0x262E)
    assert actions.encode(block, MouseButton(0x08)) == (0x2508, 0x2408)
    assert actions.encode(block, Special(0x27)) == (0x2627, 0x262E)
    assert actions.encode(block, Key(0x04)) == (0x2104, 0x2004)
    assert actions.encode(block, Raw(0xC01C, 0x262E)) == (0xC01C, 0x262E)
    assert block.to_words() == before


def test_encode_key_reproduces_vendor_app_write():
    block = ButtonBlock(load("buttons_f5_forward_a"))
    block.set_slot(1, 3, *actions.encode(block, actions.parse("key:b")))
    block.set_slot(1, 8, *actions.encode(block, actions.parse("key:c")))
    assert block.to_words() == load("buttons_f5_forward_a_back_b_one_c")


def test_encode_combination_adds_sequences_and_decodes_back():
    block = ButtonBlock(load("buttons_f5_default"))
    press, release = actions.encode(block, Key(0x06, 0x01))
    assert (press, release) == (0xC03C, 0xC03F)
    block.set_slot(1, 3, press, release)
    reread = ButtonBlock(block.to_words())
    assert actions.decode(reread, *reread.get_slot(1, 3)) == Key(0x06, 0x01)


def test_encode_combination_reuses_sequences_already_in_the_block():
    block = ButtonBlock(load("buttons_f3_mouse2"))
    before = block.to_words()
    assert actions.encode(block, Key(0x06, 0x01)) == (0xC010, 0xC013)
    assert block.to_words() == before


def test_changing_one_button_leaves_all_other_slots_and_profiles_alone():
    block = ButtonBlock(load("buttons_ef_original"))
    before = {(p, s): actions.decode(block, *block.get_slot(p, s))
              for p in (1, 2, 3) for s in range(24)}
    block.set_slot(1, 4, *actions.encode(block, Key(0x1D, 0x03)))   # Ctrl+Shift+Z
    reread = ButtonBlock(block.to_words())
    after = {(p, s): actions.decode(reread, *reread.get_slot(p, s))
             for p in (1, 2, 3) for s in range(24)}
    assert after.pop((1, 4)) == Key(0x1D, 0x03)
    before.pop((1, 4))
    # Raw c0xx references keep their numeric value because new sequences go after old ones.
    assert after == before


@pytest.mark.parametrize("text", ["disabled", "left", "right", "middle", "back", "forward",
                                  "dpi-up", "dpi-down", "key:a", "key:f5", "key:ctrl+c",
                                  "key:ctrl+shift+a", "key:alt+tab", "key:super+1",
                                  "key:ctrl", "key:super", "key:-", "key:."])
def test_parse_and_describe_round_trip(text):
    assert actions.describe(actions.parse(text)) == text


def test_modifier_alone_is_a_key():
    assert actions.parse("key:ctrl") == Key(0xE0)
    assert actions.parse("key:shift") == Key(0xE1)
    assert actions.parse("key:alt") == Key(0xE2)
    assert actions.parse("key:super") == Key(0xE3)
    block = ButtonBlock(load("buttons_f5_default"))
    assert actions.encode(block, Key(0xE0)) == (0x21E0, 0x20E0)


def test_parse_is_case_and_space_insensitive():
    assert actions.parse("  Key:Ctrl+C ") == Key(0x06, 0x01)


@pytest.mark.parametrize("text", ["", "key:", "key:ctrl+", "key:ctrl+ctrl+c", "key:hyper+c",
                                  "key:notakey", "click", "key:c+ctrl"])
def test_parse_rejects_garbage(text):
    with pytest.raises(ValueError):
        actions.parse(text)


def test_describe_unmodelled_actions():
    assert actions.describe(Raw(0x262A, 0x262E)) == "custom (0x262a 0x262e)"
    assert actions.describe(Key(0xE8)).startswith("custom")