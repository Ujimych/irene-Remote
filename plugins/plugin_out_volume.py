import threading
import uuid
from typing import Callable, Optional, Any

from irene.plugin_loader.abc import PluginManager
from irene.brain.abc import OutputChannel
from irene_plugin_web_face.abc import Connection, ProtocolHandler
from irene_plugin_web_face.protocol_irene_remote import (
    PROTOCOL_OUT_VOLUME,
    MT_OUT_VOLUME_COMMAND,
    MT_OUT_VOLUME_RESULT,
)

name = 'plugin_out_volume'
version = '0.3.0'

class VolumeCommandResult:
    __slots__ = ('success', 'volume', 'muted')

    def __init__(self, success: bool, volume: Optional[int] = None, muted: Optional[bool] = None):
        self.success = success
        self.volume = volume
        self.muted = muted

class VolumeOutputChannel(OutputChannel):
    __slots__ = ('_protocol',)

    def __init__(self, protocol): self._protocol = protocol
    def volume_up(self) -> VolumeCommandResult: return self._protocol.volume_up()
    def volume_down(self) -> VolumeCommandResult: return self._protocol.volume_down()
    def volume_min(self) -> VolumeCommandResult: return self._protocol.volume_min()
    def volume_middle(self) -> VolumeCommandResult: return self._protocol.volume_middle()
    def volume_max(self) -> VolumeCommandResult: return self._protocol.volume_max()
    def set_volume(self, volume: int) -> VolumeCommandResult: return self._protocol.set_volume(volume)
    def get_volume(self) -> VolumeCommandResult: return self._protocol.get_volume()
    def mute(self) -> VolumeCommandResult: return self._protocol.mute()
    def unmute(self) -> VolumeCommandResult: return self._protocol.unmute()

class _VolumeProtocolHandler(ProtocolHandler):
    __slots__ = (
        '_connection',
        '_lock',
        '_pending',
        '_output_channel',
    )

    proto_name = PROTOCOL_OUT_VOLUME

    def __init__(self, connection: Connection):
        self._connection = connection
        self._lock = threading.Lock()
        self._pending: dict[str, tuple[threading.Event, dict[str, Any]]] = {}

        self._connection.register_message_type(MT_OUT_VOLUME_RESULT, self._handle_result)
        self._output_channel = VolumeOutputChannel(self)
        self._connection.register_output(self._output_channel)

    def start(self):
        pass

    def terminate(self):
        with self._lock:
            pending = list(self._pending.values())
            self._pending.clear()

        for event, result in pending:
            result['value'] = VolumeCommandResult(False)
            event.set()

    def _handle_result(self, payload: dict):
        command_id = payload.get('commandId')
        if not command_id: return

        with self._lock: pending = self._pending.get(command_id)
        if pending is None: return

        event, result = pending
        result['value'] = VolumeCommandResult(
            success=bool(payload.get('success', False)),
            volume=payload.get('volume'),
            muted=payload.get('muted'),
        )
        event.set()

    def _send_command(self, command: str, value: Optional[int] = None, timeout: float = 3.0) -> VolumeCommandResult:
        command_id = str(uuid.uuid4())
        event = threading.Event()
        result: dict[str, Any] = {}

        with self._lock:
            self._pending[command_id] = (event, result)

        payload = {'commandId': command_id, 'command': command}
        if value is not None: payload['value'] = value

        try:
            self._connection.send_message(MT_OUT_VOLUME_COMMAND, payload)
            if not event.wait(timeout): return VolumeCommandResult(False)
            return result.get('value', VolumeCommandResult(False))
        finally:
            with self._lock: self._pending.pop(command_id, None)

    def volume_up(self) -> VolumeCommandResult: return self._send_command('up')
    def volume_down(self) -> VolumeCommandResult: return self._send_command('down')
    def volume_min(self) -> VolumeCommandResult: return self._send_command('min')
    def volume_middle(self) -> VolumeCommandResult: return self._send_command('middle')
    def volume_max(self) -> VolumeCommandResult: return self._send_command('max')
    def set_volume(self, volume: int) -> VolumeCommandResult: return self._send_command('set', int(volume))
    def get_volume(self) -> VolumeCommandResult: return self._send_command('get')
    def mute(self) -> VolumeCommandResult: return self._send_command('mute')
    def unmute(self) -> VolumeCommandResult: return self._send_command('unmute')


def init_client_protocol(nxt: Callable, prev: Optional[ProtocolHandler], proto_name: str, connection: Connection, pm: PluginManager, *args, **kwargs):
    print(f"VOLUME DEBUG: init_client_protocol called, proto_name={proto_name!r}, prev={prev!r}", flush=True)
    if proto_name == PROTOCOL_OUT_VOLUME: prev = prev or _VolumeProtocolHandler(connection)
    return nxt(prev, proto_name, connection, pm, *args, **kwargs)
