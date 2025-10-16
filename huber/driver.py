"""Python driver for Huber recirculating baths, using asynchronous TCP.

Distributed under the GNU General Public License v2
"""
from __future__ import annotations

import asyncio
import logging
from typing import ClassVar, Literal, NotRequired, TypedDict, overload

from huber import util

logger = logging.getLogger('huber')

class ReaderWriter(TypedDict):  # noqa: D101
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter

class BathData(TypedDict):
    """Internal data structure of bath."""

    on: bool
    temperature: dict[str, float]
    pump: dict[str, float]
    status: dict[str, bool]
    fill: float
    maintenance: float
    warning: NotRequired[dict]
    error: NotRequired[dict]

class Bath:
    """Python driver for Huber recirculating baths."""

    port = 8101
    defaults: ClassVar[list[str]] = [
        'on',
        'temperature.bath',
        'temperature.setpoint',
        'pump.pressure',
        'pump.speed',
        'pump.setpoint',
        'fill',
        'maintenance',
        'status',
    ]
    connection: ReaderWriter

    def __init__(self, ip, max_timeouts: int =10, comm_timeout: float =0.25) -> None:
        """Initialize the connection with the bath's IP address."""
        self.ip = ip
        self.open = False
        self.reconnecting = False
        self.timeouts = 0
        self.max_timeouts = max_timeouts
        self.comm_timeout = comm_timeout
        self.lock = asyncio.Lock()

    async def __aenter__(self) -> Bath:
        """Provide async entrance to context manager.

        Contrasting synchronous access, this will connect on initialization.
        """
        await self._connect()
        return self

    def __exit__(self, *args) -> None:
        """Provide exit to context manager."""
        self.close()

    async def __aexit__(self, *args) -> None:
        """Provide async exit to context manager."""
        self.close()

    async def get(self) -> BathData:
        """Get a pre-selected list of fields.

        Note that this is slow, as it chains multiple requests to construct
        a response. Look into the other `get` methods for single fields.
        """
        output: BathData = {}  # type: ignore[typeddict-item]
        for default in self.defaults:
            util.set_nested(output, default, await self._get(default))  # type: ignore[call-overload]
        if output.get('status'):
            if output['status']['warning']:
                output['warning'] = await self._get('warning')  # type: ignore[typeddict-item]
            if output['status']['error']:
                output['error'] = await self._get('error')  # type: ignore[typeddict-item]
        return output

    async def start(self) -> None:
        """Start the controller and pump."""
        return await self._set('on', True)

    async def stop(self) -> None:
        """Stop the controller and pump."""
        return await self._set('on', False)

    async def toggle(self, on) -> None:
        """Start or stop the controller and pump."""
        return await self._set('on', on)

    async def get_setpoint(self) -> float:
        """Get the temperature setpoint of the bath, in C."""
        return await self._get('temperature.setpoint')

    async def set_setpoint(self, value: float) -> None:
        """Set the temperature setpoint of the bath, in C."""
        return await self._set('temperature.setpoint', value)

    async def get_bath_temperature(self) -> float:
        """Get the internal temperature of the bath, in C."""
        return await self._get('temperature.bath')

    async def get_process_temperature(self) -> float:
        """Get the (optionally installed) process temperature, in C."""
        return await self._get('temperature.process')

    async def get_pump_pressure(self) -> float:
        """Get the bath pump outlet pressure, in mbar."""
        return await self._get('pump.pressure')

    async def get_pump_speed(self) -> float:
        """Get the bath pump speed, in RPM."""
        return await self._get('pump.speed')

    async def get_error(self) -> dict | None:
        """Get the most recent error, as a dictionary."""
        return await self._get('error')

    async def get_warning(self) -> dict | None:
        """Get the most recent warning, as a dictionary."""
        return await self._get('warning')

    async def clear_error(self) -> None:
        """Clear the most recent error."""
        await self._set('error', 1)

    async def clear_warning(self) -> None:
        """Clear the most recent warning."""
        await self._set('warning', 1)

    async def set_pump_speed(self, value: float) -> None:
        """Set the bath pump speed, in RPM."""
        return await self._set('pump.setpoint', value)

    async def get_fill_level(self) -> float:
        """Get the thermostat fluid fill level, in [0, 1]."""
        return await self._get('fill')

    async def get_next_maintenance(self) -> float:
        """Get the number of days until next maintenance alarm."""
        return await self._get('maintenance')

    async def get_status(self) -> dict:
        """Get bath status indicators. Useful for triggering alerts."""
        return await self._get('status')

    def close(self) -> None:
        """Close the TCP connection."""
        if self.open:
            self.connection['writer'].close()
        self.open = False

    async def _connect(self) -> None:
        """Asynchronously open a TCP connection with the server."""
        self.open = False
        reader, writer = await asyncio.open_connection(self.ip, self.port)
        self.connection = {'reader': reader, 'writer': writer}
        self.open = True

    @overload
    async def _get(self, key: Literal['status']) -> dict: ...
    @overload
    async def _get(self, key: Literal['error']
                            | Literal['warning']) -> dict | None: ...
    @overload
    async def _get(self, key: Literal['maintenance']
                            | Literal['fill']
                            | Literal['pump.speed']
                            | Literal['pump.pressure']
                            | Literal['temperature.setpoint']
                            | Literal['temperature.process']
                            | Literal['temperature.bath']) -> float: ...
    async def _get(self, key):
        """Get a property as specified by the corresponding key."""
        settings = util.get_field(key)
        response = await self._write_and_read(settings['address'])
        value = util.parse(response, settings)
        if ('range' in settings and value is not None and not
                settings['range'][0] <= value <= settings['range'][1]):
            raise ValueError(f'Value {value} outside allowed range.')
        return value

    async def _set(self, key: str, value) -> None:
        """Set property as specified by key."""
        settings = util.get_field(key)
        if 'writable' not in settings or not settings['writable']:
            raise ValueError(f'Can not write to {key}.')
        if ('range' in settings and not
                settings['range'][0] <= value <= settings['range'][1]):
            raise ValueError(f'Value {value} outside allowed range.')
        encoded = int(100 * value if settings['format'] == 'f' else value)
        response = await self._write_and_read(settings['address'], encoded)
        new = util.parse(response, settings)
        if new is None:
            raise OSError(f'Could not set {key}. (No response)')
        if settings['format'] != 'b' and abs(new - value) > .1:
            raise OSError(f'Could not set {key}. (Received response, but did not change)')

    async def _write_and_read(self, address, value=None) -> int | None:
        """Write a command and reads a response from the bath.

        As these baths are commonly moved around, this has been expanded to
        handle recovering from disconnects.  A lock is used to queue multiple requests.
        """
        async with self.lock:  # lock releases on CancelledError
            value = '****' if value is None else util.int_to_hex(value)
            command = f'{{M{address:02X}{value}\r\n'
            await self._handle_connection()
            response = await self._handle_communication(command)

        if (response is None or len(response) != 8
           or response[:4] != f'{{S{address:02X}'):
            return None
        return util.hex_to_int(response[4:])

    async def _handle_connection(self) -> None:
        """Automatically maintain TCP connection."""
        try:
            if not self.open:
                await asyncio.wait_for(self._connect(), timeout=self.comm_timeout)
            self.reconnecting = False
        except (asyncio.TimeoutError, OSError):
            if not self.reconnecting:
                logger.error(f'Connecting to {self.ip} timed out.')
            self.reconnecting = True

    async def _handle_communication(self, command):
        """Manage communication, including timeouts and logging."""
        try:
            self.connection['writer'].write(command.encode())
            future = self.connection['reader'].readuntil(b'\r\n')
            line = await asyncio.wait_for(future, timeout=self.comm_timeout)
            result = line.decode().strip()
            self.timeouts = 0
        except (asyncio.TimeoutError, TypeError, OSError):
            self.timeouts += 1
            if self.timeouts == self.max_timeouts:
                logger.error(f'Reading from {self.ip} timed out '
                             f'{self.timeouts} times.')
            return None
        return result
