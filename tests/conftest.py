from pathlib import Path

import pytest

from bloodless.fake import FakeTransport
from bloodless.protocol import Mouse

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    """Words of tests/fixtures/<name>.hex."""
    return [int(word, 16) for word in (FIXTURES / f"{name}.hex").read_text().split()]


@pytest.fixture
def transport():
    return FakeTransport(load("buttons_f5_default"), load("sens_f5_800_1000_1200_1600_3200"))


@pytest.fixture
def mouse(transport):
    return Mouse(transport, sleep=lambda seconds: None)