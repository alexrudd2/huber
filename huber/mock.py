"""Mock interface to a Huber bath."""
from __future__ import annotations

import asyncio
import random
from typing import final

from huber.driver import Bath as realBath
from huber.driver import BathData
from huber.util import STATUS_BITS, hex_to_int, int_to_hex


@final
class Bath(realBath):
    """Mock interface to a Huber bath."""

    server: asyncio.Server  # type: ignore[reportUninitializedInstanceVariable]

    def __init__(self, ip: str, max_timeouts: int =10, comm_timeout: float =0.25) -> None:
        super().__init__(ip, max_timeouts, comm_timeout)

        self.state: BathData = {
            'on': False,                                # Temperature control (+pump) active
            'temperature': {
                'bath': 23.49,                          # Internal (bath) temperature, °C
                'process': 22.71,                       # Process temperature, °C
                'setpoint': 50.0,                       # Temperature setpoint, °C
            },
            'pump': {
                'pressure': random.random() * 320,      # Pump head pressure, mbar
                'speed': int(random.random() * 32000),  # Pump speed, rpm
                'setpoint': 1500,                       # Pump speed setpoint, rpm
            },
            'status': {
                'circulating': random.choice([False, True]),  # True if device is circulating
                'controlling': random.choice([False, True]),  # True if temp control is active
                'error': False,                               # True if an uncleared error exists
                'pumping': random.choice([False, True]),      # True if pump is on
                'warning': False,                             # True if an uncleared warning exists
            },
            'fill': random.random(),                    # Oil level, [0, 1]
            'maintenance': int(random.random() * 365),  # Time until maintenance alarm, days
        }

    async def _connect(self) -> None:
        self.server = await asyncio.start_server(
            self._handle_client, host="127.0.0.1", port=0,  # let OS pick free port
        )
        sock = self.server.sockets[0]
        self.port = sock.getsockname()[:2][1]
        self.ip = "127.0.0.1"

        await super()._connect()

    def close(self) -> None:
        """"Close the TCP connection and tear down the server."""
        super().close()
        if hasattr(self, "server"):
            self.server.close()

    async def _handle_client(  # noqa: C901
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            while not reader.at_eof():
                data = await reader.readline()
                if not data:
                    break
                assert(data[0:2] == b'{M')
                assert(data[-2:] == b'\r\n')
                command = data[2:-2]
                address = int(command[0:2], 16)
                value = command[2:6].decode()
                if value == "****":  # reads
                    match address:
                        case 0x14:  # running status
                            response: bool | int = self.state['on']
                        case 0x01:  # bath temp
                            response = int(self.state['temperature']['bath'] * 100)
                        case 0x00:  # bath temp setpoint
                            response = int(self.state['temperature']['setpoint'] * 100)
                        case 0x03:  # pump pressure
                            response = int(self.state['pump']['pressure'] * 100)
                        case 0x26:  # pump speed
                            response = int(self.state['pump']['speed'])
                        case 0x48:  # pump setpoint
                            response = int(self.state['pump']['setpoint'])
                        case 0x0f:  # fill %
                            response = int(self.state['fill'] * 1000)
                        case 0x5c:  # maintenance days
                            response = int(self.state['maintenance'])
                        case 0x0a:  # status enumeration
                            response = sum(1 << bit for name, bit in STATUS_BITS.items()
                                          if self.state['status'][name])
                        case _:
                            raise NotImplementedError(f"Address {address} is not implemented")
                else:  # writes
                    match address:
                        case 0x14:  # running status
                            self.state['on'] = value == '0001'
                        case 0x00:  # temp setpoint
                            val = hex_to_int(value) / 100.0
                            self.state['temperature']['setpoint'] = val
                        case 0x48:  # pump speed setpoint
                            val = hex_to_int(value)
                            self.state['pump']['setpoint'] = val
                            self.state['pump']['speed'] = val
                        case _:
                            raise NotImplementedError(f"Address {address} is not implemented")
                    response = hex_to_int(value)

                writer.write(('{S' + f"{address:02X}" + int_to_hex(response) + '\r\n').encode())
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
