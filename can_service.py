import can
from can import Listener
import threading
import logging
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass

from can_types import CANMessageType, DecodedMessage

logger = logging.getLogger(__name__)

PGN_DM1 = 0xFECA
PGN_DM2 = 0xFECB
PGN_DM3 = 0xFECD
PGN_DM4 = 0xFECE

CAN_ID_DM1 = 0x18FECA00
CAN_ID_DM2 = 0x18FECB00
CAN_ID_DM3 = 0x18FECD00


@dataclass
class MessageCache:
    last_data: Optional[bytes] = None
    last_decoded: Optional[Dict[str, Any]] = None


class CANService:
    def __init__(self):
        self.bus: Optional[can.interface.Bus] = None
        self.notifier: Optional[can.Notifier] = None
        self.listener: Optional[_CANListener] = None
        self.is_listening = False
        self._lock = threading.Lock()

        self._dbcan_decoder = None
        self._dbc_message_ids: Dict[int, Any] = {}

        self._message_cache: Dict[int, MessageCache] = {}
        self._on_message_callback: Optional[Callable[[DecodedMessage], None]] = None
        self._on_status_callback: Optional[Callable[[str], None]] = None

    def set_message_callback(self, callback: Callable[[DecodedMessage], None]):
        self._on_message_callback = callback

    def set_status_callback(self, callback: Callable[[str], None]):
        self._on_status_callback = callback

    def _log(self, message: str):
        logger.info(message)
        if self._on_status_callback:
            self._on_status_callback(message)

    def load_dbc(self, dbc_path: str) -> bool:
        try:
            import cantools

            self._dbcan_decoder = cantools.db.load_file(dbc_path)
            self._dbc_message_ids = {
                msg.frame_id: msg for msg in self._dbcan_decoder.messages
            }

            message_names = [
                f"{msg.name} ({msg.frame_id:X})" for msg in self._dbcan_decoder.messages
            ]
            self._log(f"Loaded DBC: {dbc_path} with {len(message_names)} messages")
            for name in message_names:
                self._log(f"  - {name}")

            return True
        except ImportError:
            self._log("Error: cantools not installed. Run: pip install cantools")
            return False
        except Exception as e:
            self._log(f"Error loading DBC: {e}")
            return False

    def connect(self, channel: int, baudrate: int = 250000) -> bool:
        try:
            self.bus = can.interface.Bus(
                bustype="ixxat", channel=channel, bitrate=baudrate
            )
            self._log(f"Connected to IXXAT channel {channel} at {baudrate} baud")
            return True
        except Exception as e:
            self._log(f"Connection error: {e}")
            return False

    def disconnect(self):
        if self.is_listening:
            self.stop_listening()

        if self.bus:
            self.bus.shutdown()
            self.bus = None
            self._log("Disconnected from CAN")

    def is_connected(self) -> bool:
        return self.bus is not None

    def start_listening(self, filter_dm1: bool = True):
        if self.bus is None:
            return

        with self._lock:
            self._message_cache.clear()

            self.listener = _CANListener(
                dbc_decoder=self._dbcan_decoder,
                dbc_message_ids=self._dbc_message_ids,
                filter_dm1=filter_dm1,
                on_message=self._handle_message,
            )

            self.notifier = can.Notifier(self.bus, [self.listener])
            self.listener.start()
            self.is_listening = True
            self._log("Started listening to CAN traffic")

    def stop_listening(self):
        with self._lock:
            if self.listener:
                self.listener.stop()
            if self.notifier:
                self.notifier.stop()
            self.is_listening = False
            self._log("Stopped listening to CAN traffic")

    def _handle_message(
        self, msg: can.Message, decoded_fields: Dict[str, Any], dbc_name: Optional[str]
    ):
        can_id = msg.arbitration_id

        cache = self._message_cache.get(can_id)

        is_update = True
        if cache is None:
            cache = MessageCache()
            self._message_cache[can_id] = cache
        else:
            if cache.last_data == msg.data:
                is_update = False

        if is_update or True:
            cache.last_data = bytes(msg.data)
            cache.last_decoded = decoded_fields.copy() if decoded_fields else {}

            decoded_msg = DecodedMessage(
                timestamp=msg.timestamp,
                can_id=can_id,
                message_type=CANMessageType.J1939
                if msg.is_extended_id
                else CANMessageType.STANDARD,
                raw_data=bytes(msg.data),
                decoded_fields=decoded_fields or {},
                dbc_name=dbc_name,
                is_update=is_update,
            )

            if self._on_message_callback:
                self._on_message_callback(decoded_msg)

    def send_j1939_request(self, pgn: int, dest: int = 0xFF) -> bool:
        if self.bus is None:
            return False

        request_data = [
            pgn & 0xFF,
            (pgn >> 8) & 0xFF,
            (pgn >> 16) & 0xFF,
            0xFF,
            0xFF,
            0xFF,
            0xFF,
            0xFF,
        ]

        arb_id = (7 << 26) | (0xEA << 8) | (dest << 8) | 0xFF

        msg = can.Message(arbitration_id=arb_id, data=request_data, is_extended_id=True)

        try:
            self.bus.send(msg)
            self._log(f"Sent PGN {pgn:06X} request to destination {dest:02X}")
            return True
        except Exception as e:
            self._log(f"Send error: {e}")
            return False

    def send_j1939_command(self, pgn: int, data: list, dest: int) -> bool:
        if self.bus is None:
            return False

        data = list(data)
        while len(data) < 8:
            data.append(0xFF)

        arb_id = (7 << 26) | (pgn << 8) | dest

        msg = can.Message(arbitration_id=arb_id, data=data[:8], is_extended_id=True)

        try:
            self.bus.send(msg)
            self._log(f"Sent PGN {pgn:06X} command to ECU {dest:02X}")
            return True
        except Exception as e:
            self._log(f"Send error: {e}")
            return False

    def clear_dm1(self, dest: int) -> bool:
        self._message_cache.clear()
        return self.send_j1939_command(PGN_DM2, [0x01], dest)

    def request_dm1(self, dest: int) -> bool:
        return self.send_j1939_request(PGN_DM1, dest)

    def clear_all_dm(self, dest: int) -> bool:
        self._message_cache.clear()
        return self.send_j1939_command(PGN_DM3, [0x01], dest)

    def send_raw_message(self, can_id: int, data: list, extended: bool = False) -> bool:
        if self.bus is None:
            return False

        msg = can.Message(arbitration_id=can_id, data=data[:8], is_extended_id=extended)

        try:
            self.bus.send(msg)
            return True
        except Exception as e:
            self._log(f"Send error: {e}")
            return False


class _CANListener(Listener):
    def __init__(
        self,
        dbc_decoder,
        dbc_message_ids: Dict[int, Any],
        filter_dm1: bool,
        on_message: Callable,
    ):
        self.dbc_decoder = dbc_decoder
        self.dbc_message_ids = dbc_message_ids
        self.filter_dm1 = filter_dm1
        self.on_message = on_message
        self.running = False
        self.lock = threading.Lock()

    def on_message_received(self, msg: can.Message):
        if not self.running:
            return

        if msg.is_extended_id:
            pgn = (msg.arbitration_id >> 8) & 0x3FFFF
            if self.filter_dm1 and pgn == PGN_DM1:
                return

        decoded_fields = None
        dbc_name = None

        if self.dbc_decoder:
            dbc_msg = self.dbc_message_ids.get(msg.arbitration_id)
            if dbc_msg:
                try:
                    decoded = self.dbc_msg.decode(msg.data)
                    decoded_fields = dict(decoded)
                    dbc_name = dbc_msg.name
                except Exception as e:
                    logger.debug(f"DBC decode error for {msg.arbitration_id:X}: {e}")

        self.on_message(msg, decoded_fields, dbc_name)

    def start(self):
        with self.lock:
            self.running = True

    def stop(self):
        with self.lock:
            self.running = False
