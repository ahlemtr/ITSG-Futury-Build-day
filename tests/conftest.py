from pathlib import Path

import pytest

from tests.fakes.fake_kb import FakeKB

ROOT = Path(__file__).resolve().parents[1]
ITSG_FILE = ROOT / "fixtures/itsg/TEEL0-Test1-DBVO"


@pytest.fixture
def kb():
    return FakeKB()


@pytest.fixture
def itsg_bytes():
    return ITSG_FILE.read_bytes()
