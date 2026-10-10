import pytest

from bloodless import actions, config
from bloodless.actions import Key, MouseButton, Special
from bloodless.transport import DeviceError, find_devices


def test_get_buttons(mouse):
    buttons = config.get_buttons(mouse.read_buttons())
    assert list(buttons) == ["back", "forward", "top1", "topn", "top3"]
    assert buttons["back"] == MouseButton(0x08)
    assert buttons["forward"] == MouseButton(0x10)
    assert buttons["top1"] == Special(0x27)


def test_set_button(mouse):
    block = mouse.read_buttons()
    config.set_button(block, "back", Key(0x06, 0x01))
    assert config.get_buttons(block)["back"] == Key(0x06, 0x01)


def test_set_button_rejects_left_click_and_unknown_names(mouse):
    block = mouse.read_buttons()
    for name in ("left", "nope"):
        with pytest.raises(ValueError):
            config.set_button(block, name, actions.Disabled())


def test_dpi(mouse):
    sens = mouse.read_sensitivity()
    assert config.get_dpi(sens) == [800, 1000, 1200, 1600, 3200]
    config.set_dpi(sens, 4, 2100)
    assert config.get_dpi(sens) == [800, 1000, 1200, 2100, 3200]


@pytest.mark.parametrize("level, value", [(0, 800), (6, 800), (1, 850), (1, 5000)])
def test_dpi_rejects_bad_input(mouse, level, value):
    with pytest.raises(ValueError):
        config.set_dpi(mouse.read_sensitivity(), level, value)


def test_check_supported():
    config.check_supported({"model": 0x010, "subtype": 1, "firmware": 0xF3})
    with pytest.raises(DeviceError):
        config.check_supported({"model": 0x218, "subtype": 0, "firmware": 0x10})


def test_save_backup(mouse, tmp_path):
    path = config.save_backup(mouse, tmp_path)
    lines = path.read_text().splitlines()
    assert lines[0].startswith("1a00: a4a4 ffff 0dc6 2d13")
    assert lines[1].startswith("1b00: a4a4 ffff ff0c 5902")
    assert len(lines[1].split()) == 1 + 640


def test_backup_dir_honours_xdg_state_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert config.backup_dir() == tmp_path / "bloodless" / "backups"


def test_find_devices_picks_only_vendor_interface_of_a4tech(tmp_path):
    def node(name, uevent):
        (tmp_path / name / "device").mkdir(parents=True)
        (tmp_path / name / "device" / "uevent").write_text(uevent)

    node("hidraw3", "HID_ID=0003:000009DA:00001B3B\nHID_PHYS=usb-0000:03:00.0-4/input0\n")
    node("hidraw5", "HID_ID=0003:000009DA:00001B3B\nHID_PHYS=usb-0000:03:00.0-4/input2\n")
    node("hidraw6", "HID_ID=0003:0000045E:000007A5\nHID_PHYS=usb-0000:03:00.0-5/input2\n")
    (tmp_path / "hidraw7").mkdir()
    assert find_devices(str(tmp_path)) == ["/dev/hidraw5"]


def test_open_mouse_without_device(monkeypatch):
    monkeypatch.setattr(config, "find_devices", lambda: [])
    with pytest.raises(DeviceError, match="no Bloody mouse found"):
        config.open_mouse()


def test_backups_made_in_the_same_second_do_not_overwrite_each_other(mouse, tmp_path):
    paths = {config.save_backup(mouse, tmp_path) for _ in range(3)}
    assert len(paths) == 3
    assert all(path.exists() for path in paths)


def test_load_backup_round_trip(mouse, tmp_path):
    sens, buttons = config.load_backup(config.save_backup(mouse, tmp_path))
    assert sens.to_words() == mouse.read_sensitivity().to_words()
    assert buttons.to_words() == mouse.read_buttons().to_words()