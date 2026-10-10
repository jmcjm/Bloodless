import pytest

from bloodless import dpi


@pytest.mark.parametrize("value, raw", [(800, (0x0B, 2)), (1000, (0x0E, 2)), (1200, (0x0C, 3)),
                                        (1600, (0x0D, 4)), (2100, (0x0E, 5)), (3200, (0x10, 7))])
def test_values_observed_from_vendor_app(value, raw):
    assert dpi.dpi_to_raw(value) == raw
    assert dpi.raw_to_dpi(*raw) == value


@pytest.mark.parametrize("raw, value", [((0x0C, 1), 600), ((0x0A, 1), 500), ((0x10, 5), 2400)])
def test_formula_for_pairs_found_in_old_configs(raw, value):
    assert dpi.raw_to_dpi(*raw) == value
    assert dpi.dpi_to_raw(value) == raw


@pytest.mark.parametrize("value", range(100, 3300, 100))
def test_every_selectable_value_encodes_within_range(value):
    a, r = dpi.dpi_to_raw(value)
    assert 1 <= a <= 16 and 1 <= r <= 7
    assert abs(dpi.raw_to_dpi(a, r) - value) <= 100


@pytest.mark.parametrize("value", range(100, 1700, 100))
def test_values_up_to_1600_are_exact(value):
    assert dpi.raw_to_dpi(*dpi.dpi_to_raw(value)) == value


@pytest.mark.parametrize("value", [0, 50, 150, 3300, -100, 100000])
def test_invalid_dpi_is_rejected(value):
    with pytest.raises(ValueError):
        dpi.dpi_to_raw(value)