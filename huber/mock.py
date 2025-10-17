"""Mock interface to a Huber bath."""
from __future__ import annotations

import asyncio
import random

from huber.driver import Bath as realBath
from huber.driver import BathData


class Bath(realBath):
    """Mock interface to a Huber bath."""

    def __init__(self, *args, **kwargs) -> None:
        """Init fixed variables."""
        self.temp_setpoint: float = 50
        self.pump_setpoint: float = 500
        self.on = False

    async def _connect(self) -> None:
        """Mock creating the TCP connection."""
        self.open = True

    def close(self) -> None:
        """Mock closing the TCP connection."""
        self.open = False

    async def get(self) -> BathData:
        """Return data structure randomly populated."""
        await asyncio.sleep(random.random() * 0.25)
        mock_bath_data: BathData = {
            'on': self.on,  # Temperature control (+pump) active
            'temperature': {
                'bath': 23.49,                  # Internal (bath) temperature, °C
                'process': 22.71,               # Process temperature, °C
                'setpoint': self.temp_setpoint, # Temperature setpoint, °C
            },
            'pump': {
                'pressure': random.random() * 1000,    # Pump head pressure, mbar
                'speed': random.random() * 1000,       # Pump speed, rpm
                'setpoint': self.pump_setpoint,        # Pump speed setpoint, rpm
            },
            'status': {
                'circulating': random.choice([False, True]),  # True if device is circulating
                'controlling': random.choice([False, True]),  # True if temp control is active
                'error': False,                               # True if an uncleared error exists
                'pumping': random.choice([False, True]),      # True if pump is on
                'warning': False,                             # True if an uncleared warning exists
            },
            'fill': random.random(),               # Oil level, [0, 1]
            'maintenance': random.random() * 365,  # Time until maintenance alarm, days
        }
        return mock_bath_data

    async def start(self) -> None:
        """Start the controller and pump."""
        await asyncio.sleep(random.random())
        self.on = True

    async def stop(self) -> None:
        """Stop the controller and pump."""
        await asyncio.sleep(random.random() * 0.25)
        self.on = False

    async def get_setpoint(self) -> float:
        """Return setpoint."""
        return (await self.get())['temperature']['setpoint']

    async def set_setpoint(self, value: float) -> None:
        """Set the temperature setpoint of the bath, in C."""
        await asyncio.sleep(random.random() * 0.25)
        self.temp_setpoint = value

    async def get_bath_temperature(self) -> float:
        """Get the internal temperature of the bath, in C."""
        return (await self.get())['temperature']['bath']

    async def get_process_temperature(self) -> float:
        """Get the (optionally installed) process temperature, in C."""
        return (await self.get())['temperature']['process']

    async def get_pump_pressure(self) -> float:
        """Get the bath pump outlet pressure, in mbar."""
        return (await self.get())['pump']['pressure']

    async def get_pump_speed(self) -> float:
        """Get the bath pump speed, in RPM."""
        return (await self.get())['pump']['speed']

    async def set_pump_speed(self, value: float) -> None:
        """Set the bath pump speed, in RPM."""
        await asyncio.sleep(random.random() * 0.25)
        self.pump_setpoint = value

    async def get_fill_level(self) -> float:
        """Get the thermostat fluid fill level, in [0, 1]."""
        return (await self.get())['fill']

    async def get_next_maintenance(self) -> float:
        """Get the number of days until next maintenance alarm."""
        return (await self.get())['maintenance']

    async def get_status(self) -> dict[str, bool]:
        """Get bath status indicators. Useful for triggering alerts."""
        return (await self.get())['status']

    async def get_error(self) -> dict | None:
        """Get the most recent error, as a dictionary."""
        return (await self.get()).get('error')

    async def get_warning(self) -> dict | None:
        """Get the most recent warning, as a dictionary."""
        return (await self.get()).get('warning')
