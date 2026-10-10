import pytest

from bloodless import actions, dpi
from bloodless.blocks import ButtonBlock
from bloodless.protocol import WriteError
from conftest import load


def opcodes(transport):
    return [frame[1] for frame in transport.sent]


def test_info(mouse):
    assert mouse.info() == {"model": 0x010, "subtype": 0, "firmware": 0xF5}


def test_read_blocks(mouse):
    assert mouse.read_buttons().to_words() == load("buttons_f5_default")
    assert mouse.read_sensitivity().to_words() == load("sens_f5_800_1000_1200_1600_3200")


def test_reading_unlocks_once(mouse, transport):
    mouse.read_sensitivity()
    mouse.read_sensitivity()
    assert opcodes(transport).count(0x25) == 1


def test_write_buttons_frames(mouse, transport):
    block = mouse.read_buttons()
    transport.sent.clear()
    mouse.write_buttons(block)
    words = block.to_words()
    frames = transport.sent
    assert frames[0][:4] == bytes([0x07, 0x2F, 0x00, 0x1B])
    assert frames[1][:8] == bytes([0x07, 0x20, 0, 0, 0, 0, 0, 0x01])
    packets = [f for f in frames if f[1] == 0x2F and f[2] == 0x79]
    assert len(packets) == len(words) // 16
    assert packets[0][:8] == bytes([0x07, 0x2F, 0x79, 0x1B, 0x00, 0x80, 0, 0])
    assert packets[0][8:12] == b"\xff\xff\xff\xff"
    assert packets[1][3:5] == bytes([0x1B, 0x10])
    assert packets[16][3:5] == bytes([0x1C, 0x00])
    after_packets = frames[frames.index(packets[-1]) + 1:]
    assert after_packets[0][:10] == bytes([0x07, 0x2F, 0x01, 0x1B, 0x00, 0, 0, 0, 0xA4, 0xA4])
    assert after_packets[1][:8] == bytes([0x07, 0x20, 0, 0, 0, 0, 0, 0])
    assert [f[1] for f in frames[-3:]] == [0x0E, 0x0F, 0x0C]


def test_write_buttons_changes_what_is_read_back(mouse):
    block = mouse.read_buttons()
    block.set_slot(1, 4, *actions.encode(block, actions.Key(0x19, 0x01)))
    mouse.write_buttons(block)
    reread = mouse.read_buttons()
    assert actions.decode(reread, *reread.get_slot(1, 4)) == actions.Key(0x19, 0x01)


def test_writing_a_shorter_block_over_a_longer_one(mouse, transport):
    transport.load(0x1B00, load("buttons_ef_original"))
    mouse.write_buttons(ButtonBlock(load("buttons_f5_default")))
    assert mouse.read_buttons().to_words() == load("buttons_f5_default")


def test_write_sensitivity_sends_live_dpi_frame(mouse, transport):
    sens = mouse.read_sensitivity()
    sens.set_level(0, *dpi.dpi_to_raw(400))
    mouse.write_sensitivity(sens)
    assert mouse.read_sensitivity().get_level(0) == dpi.dpi_to_raw(400)
    live = [f for f in transport.sent if f[1] == 0x0D][-1]
    a, r = dpi.dpi_to_raw(400)
    assert live[8:14] == bytes([4, 0, a, a, 0x80 | r, 2])


def test_readback_mismatch_raises(mouse, transport):
    block = mouse.read_buttons()
    transport.corrupt_writes = True
    with pytest.raises(WriteError):
        mouse.write_buttons(block)


def test_backlight(mouse, transport):
    assert mouse.get_backlight() == 3
    mouse.set_backlight(1)
    assert mouse.get_backlight() == 1
    assert bytes([0x07, 0x11, 0, 0, 0x80, 0, 0, 0, 1]) in [f[:9] for f in transport.sent]


@pytest.mark.parametrize("level", [-1, 4, 255])
def test_backlight_out_of_range(mouse, level):
    with pytest.raises(ValueError):
        mouse.set_backlight(level)

def test_current_level_follows_the_mouse(mouse, transport):
    assert mouse.current_level() == 0
    transport.level = 3  # what a press of the DPI button does
    assert mouse.current_level() == 3


def test_current_level_ignores_reports_queued_earlier(mouse, transport):
    transport.inputs.append(bytes([7, 1, 1, 0, 0, 0, 7, 0, 0, 0, 0, 2, 4, 1, 0, 0]))
    assert mouse.current_level() == 0


def test_current_level_skips_reports_of_another_kind(mouse, transport):
    original = transport.send

    def send(payload):
        if bytes(payload)[1] == 0x0C and not transport.inputs:
            transport.inputs.append(bytes([7, 1, 0xF1, 0, 0, 0, 7, 0, 0, 0, 0, 2, 8, 1, 0, 0]))
            transport.sent.append(bytes(payload))
            transport.send = original
            return
        original(payload)

    transport.send = send
    transport.level = 2
    assert mouse.current_level() == 2


def test_current_level_is_none_when_the_mouse_stays_silent(mouse, transport):
    transport.silent = True
    assert mouse.current_level() is None


def test_writing_sensitivity_keeps_the_selected_level_in_use(mouse, transport):
    transport.level = 4
    mouse.write_sensitivity(mouse.read_sensitivity())
    assert mouse.current_level() == 0
