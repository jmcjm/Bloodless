import pytest

from bloodless.blocks import BlockError, ButtonBlock, SensitivityBlock, checksum
from conftest import load

BUTTON_FIXTURES = ["buttons_f5_default", "buttons_f5_forward_a", "buttons_f5_forward_a_back_b",
                   "buttons_f5_forward_a_back_b_one_c", "buttons_f3_mouse2", "buttons_ef_original"]
SENS_FIXTURES = ["sens_f5_800_1000_1200_1600_3200", "sens_f5_800_1000_1200_2100_3200",
                 "sens_f3_mouse2", "sens_ef_original"]


@pytest.mark.parametrize("name", BUTTON_FIXTURES + SENS_FIXTURES)
def test_checksum_matches_real_blocks(name):
    words = load(name)
    assert checksum(words) == (words[2], words[3])


@pytest.mark.parametrize("name", BUTTON_FIXTURES)
def test_button_block_round_trips(name):
    assert ButtonBlock(load(name)).to_words() == load(name)


@pytest.mark.parametrize("name", SENS_FIXTURES)
def test_sensitivity_block_round_trips(name):
    assert SensitivityBlock(load(name)).to_words() == load(name)


def test_button_block_ignores_stale_words_after_its_end():
    words = load("buttons_f5_default")
    assert ButtonBlock(words + [0xFFFF] * 100).to_words() == words


def test_slots_of_default_block():
    block = ButtonBlock(load("buttons_f5_default"))
    assert block.get_slot(1, 0) == (0x2501, 0x2401)
    assert block.get_slot(1, 3) == (0x2508, 0x2408)
    assert block.get_slot(1, 4) == (0x2510, 0x2410)
    assert block.get_slot(1, 8) == (0x2627, 0x262E)


def test_set_slot_reproduces_vendor_app_write():
    block = ButtonBlock(load("buttons_f5_forward_a"))
    block.set_slot(1, 3, 0x2105, 0x2005)
    assert block.to_words() == load("buttons_f5_forward_a_back_b")


def test_profiles_have_separate_tables_when_block_has_them():
    block = ButtonBlock(load("buttons_ef_original"))
    assert block.get_slot(1, 3) == (0xC010, 0xC013)
    assert block.get_slot(2, 3) == (0xC016, 0xC019)
    assert block.get_slot(3, 3) == (0x2508, 0x2408)


def test_read_sequence():
    block = ButtonBlock(load("buttons_f3_mouse2"))
    assert block.read_sequence(0x10) == [0x2301, 0x2106]
    assert block.read_sequence(0x13) == [0x2006, 0x2201]


def test_read_sequence_rejects_offset_outside_sequence_area():
    block = ButtonBlock(load("buttons_f5_default"))
    with pytest.raises(BlockError):
        block.read_sequence(0x60)


def test_add_sequence_reuses_existing_one():
    block = ButtonBlock(load("buttons_f3_mouse2"))
    before = block.to_words()
    assert block.add_sequence([0x2301, 0x2106]) == 0x10
    assert block.to_words() == before


def test_add_sequence_inserts_and_shifts_every_pointer():
    old = ButtonBlock(load("buttons_f5_default"))
    block = ButtonBlock(load("buttons_f5_default"))
    offset = block.add_sequence([0x2301, 0x2106])
    assert offset == 0x3C
    assert block.read_sequence(offset) == [0x2301, 0x2106]
    w, o = block.words, old.words
    for header in (7, 8, 9, 10, 11, 13):
        assert w[header] == o[header] + 3
    for header in (7, 8, 9):
        assert w[w[header]:w[header] + 3] == [x + 3 for x in o[o[header]:o[header] + 3]]
    assert w[w[13]:w[13] + 10:2] == [x + 3 for x in o[o[13]:o[13] + 10:2]]
    # Everything that is not a pointer moved by three words, unchanged.
    assert all(block.get_slot(1, s) == old.get_slot(1, s) for s in range(24))
    assert old.read_sequence(0x10) == block.read_sequence(0x10)
    # The result is still a valid block.
    ButtonBlock(block.to_words())


def test_add_sequence_refuses_when_block_is_full():
    block = ButtonBlock(load("buttons_ef_original"))
    with pytest.raises(BlockError):
        for usage in range(4, 60):
            block.add_sequence([0x2301, 0x2100 | usage])
    assert len(block.to_words()) <= ButtonBlock.MAX_WORDS
    ButtonBlock(block.to_words())


@pytest.mark.parametrize("damage", [
    lambda w: w.__setitem__(40, w[40] ^ 1),           # flipped bit -> checksum
    lambda w: w.__delitem__(slice(8, None)),          # truncated
    lambda w: w.__setitem__(slice(0, None), [0xFFFF] * len(w)),  # erased flash
    lambda w: w.__setitem__(slice(0, None), [0] * len(w)),       # zeros
])
def test_damaged_button_block_is_rejected(damage):
    words = load("buttons_f5_default")
    damage(words)
    with pytest.raises(BlockError):
        ButtonBlock(words)


def test_button_block_with_valid_checksum_but_wrong_layout_is_rejected():
    words = load("sens_ef_original")
    with pytest.raises(BlockError):
        ButtonBlock(words)


def test_sensitivity_levels():
    block = SensitivityBlock(load("sens_f5_800_1000_1200_1600_3200"))
    assert block.count == 5
    assert block.selected == 0
    assert block.rate == 2
    assert [block.get_level(i) for i in range(5)] == [(0x0B, 2), (0x0E, 2), (0x0C, 3), (0x0D, 4),
                                                      (0x10, 7)]


def test_set_level_reproduces_vendor_app_write():
    block = SensitivityBlock(load("sens_f5_800_1000_1200_1600_3200"))
    block.set_level(3, 0x0E, 5)
    assert block.to_words() == load("sens_f5_800_1000_1200_2100_3200")


def test_level_index_out_of_range():
    block = SensitivityBlock(load("sens_ef_original"))
    with pytest.raises(ValueError):
        block.set_level(5, 0x10, 7)
    with pytest.raises(ValueError):
        block.get_level(-1)


def test_damaged_sensitivity_block_is_rejected():
    words = load("sens_ef_original")
    words[10] ^= 1
    with pytest.raises(BlockError):
        SensitivityBlock(words)