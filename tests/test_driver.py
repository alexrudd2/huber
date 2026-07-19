"""Test the driver correctly initializes and returns mocked data."""
import random
from json import loads
from unittest import mock

import pytest

from huber import command_line
from huber.mock import Bath

fixed_random = random.random()
fixed_choice = random.choice([False, True])


@pytest.fixture(autouse=True)
def mocked_random():
    """Patch random to have deterministic answers for the fixture and mock."""
    with (
        mock.patch('huber.mock.random.random', return_value=fixed_random),
        mock.patch('huber.mock.random.choice', return_value=fixed_choice),
    ):
        yield

@pytest.fixture(autouse=True)
def mock_bath(monkeypatch):
    """Mock the bath."""
    monkeypatch.setattr('huber.Bath', Bath)


@pytest.fixture
def expected_data():
    """Return the mocked data."""
    return {
        'on': False,  # Temperature control (+pump) active
        'temperature': {
            'bath': 23.49,                # Internal (bath) temperature, °C
            'setpoint': 50.0,             # Temperature setpoint, °C
        },
        'pump': {
            'pressure': int(fixed_random * 320 * 100) / 100.0,  # Pump head pressure, mbar
            'speed': int(fixed_random * 32000),                 # Pump speed, rpm
            'setpoint': 1500,                                   # Pump speed setpoint, rpm
        },
        'status': {
            'circulating': fixed_choice,  # True if device is circulating
            'controlling': fixed_choice,  # True if temp control is active
            'error': False,               # True if an uncleared error exists
            'pumping': fixed_choice,      # True if pump is on
            'warning': False,             # True if an uncleared warning exists
        },
        'fill': int(fixed_random * 1000) / 1000.0,  # Oil level, [0, 1]
        'maintenance': int(fixed_random * 365),     # Time until maintenance alarm, days
    }


@pytest.mark.asyncio
async def test_get_data(expected_data):
    """Confirm that the driver returns correct values on get() calls."""
    bath = Bath('fake ip')
    assert expected_data == await bath.get()

@pytest.mark.asyncio
async def test_start_stop():
    """Confirm that the driver correctly starts and stops the bath."""
    bath = Bath('fake ip')
    assert (await bath.get())['on'] == False  # noqa: E712
    await bath.start()
    assert (await bath.get())['on'] == True  # noqa: E712
    await bath.stop()
    assert (await bath.get())['on'] == False  # noqa: E712

    await bath.toggle(False)
    assert (await bath.get())['on'] == False  # noqa: E712
    await bath.toggle(True)
    assert (await bath.get())['on'] == True  # noqa: E712
    await bath.toggle(True)
    assert (await bath.get())['on'] == True  # noqa: E712
    await bath.toggle(False)
    assert (await bath.get())['on'] == False  # noqa: E712

@pytest.mark.asyncio
async def test_setpoint_roundtrip():
    """Confirm that the driver correctly changes setpoints."""
    bath = Bath('fake ip')
    sp = 2222
    await bath.set_pump_speed(sp)
    assert (await bath.get())['pump']['setpoint'] == sp


def test_driver_cli(capsys, expected_data):
    """Confirm the commandline interface works."""
    command_line(['fakeip'])
    captured = loads(capsys.readouterr().out)
    assert expected_data == captured

def test_driver_cli_setpoint(capsys, expected_data):
    """Confirm setting a setpoint via the commandline interface works."""
    command_line(['fakeip', '--set-setpoint', '1.23'])
    captured = loads(capsys.readouterr().out)
    expected_data['temperature']['setpoint'] = 1.23  # type: ignore[index, assignment]
    assert expected_data == captured
