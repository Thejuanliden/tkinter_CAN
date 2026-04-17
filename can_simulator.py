import threading
import time
import random
import logging
from typing import Dict, Optional, Callable, Any, List
from dataclasses import dataclass

from can_types import CANMessageType, DecodedMessage

logger = logging.getLogger(__name__)


@dataclass
class MessageCache:
    last_data: Optional[bytes] = None
    last_decoded: Optional[Dict[str, Any]] = None


@dataclass
class SimulatedMessage:
    can_id: int
    data_generator: Callable[[], List[int]]
    period: float = 1.0
    is_extended: bool = True
    name: str = ""
    next_time: float = 0.0


def _engine_data_gen():
    return [0x10, random.randint(0, 255), random.randint(0, 100), 0, 0, 0, 0, 0]


def _aftertreatment1_gen():
    return [
        random.randint(0, 255),
        random.randint(0, 255),
        random.randint(0, 255),
        random.randint(0, 255),
        random.randint(0, 255),
        random.randint(0, 255),
        0,
        0,
    ]


def _aftertreatment_dosing_gen():
    return [0xFF, 0xFE, random.randint(0, 255), 0, 0, 0, 0, 0]


def _dm1_gen():
    return [0x01, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]


def _transport_gen():
    return [
        random.randint(0, 255),
        random.randint(0, 255),
        random.randint(0, 255),
        random.randint(0, 255),
        random.randint(0, 255),
        random.randint(0, 255),
        random.randint(0, 255),
        random.randint(0, 255),
    ]


def _intake_gas_gen():
    return [
        random.randint(20, 80),
        0,
        random.randint(100, 300) & 0xFF,
        (random.randint(100, 300) >> 8) & 0xFF,
        0,
        0,
        0,
        0,
    ]


J1939_SIMULATED_MESSAGES = [
    SimulatedMessage(
        can_id=0x7E4,
        data_generator=_engine_data_gen,
        period=0.1,
        is_extended=False,
    ),
    SimulatedMessage(
        can_id=0x600,
        data_generator=_aftertreatment1_gen,
        period=0.5,
        is_extended=False,
    ),
    SimulatedMessage(
        can_id=0x7E5,
        data_generator=_aftertreatment_dosing_gen,
        period=1.0,
        is_extended=False,
    ),
    SimulatedMessage(
        can_id=0x708,
        data_generator=_dm1_gen,
        period=5.0,
        is_extended=False,
    ),
    SimulatedMessage(
        can_id=0x100,
        data_generator=_transport_gen,
        period=0.05,
        is_extended=False,
    ),
    SimulatedMessage(
        can_id=0x700,
        data_generator=_intake_gas_gen,
        period=0.25,
        is_extended=False,
    ),
]


class CANSimulator:
    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._on_message_callback: Optional[Callable[[DecodedMessage], None]] = None
        self._on_status_callback: Optional[Callable[[str], None]] = None
        self._message_cache: Dict[int, MessageCache] = {}
        self._messages: List[SimulatedMessage] = []
        self._start_time = 0.0
        self._dbc_decoder = None
        self._dbc_message_ids: Dict[int, Any] = {}

        for msg in J1939_SIMULATED_MESSAGES:
            self._messages.append(msg)

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

            self._dbc_decoder = cantools.db.load_file(dbc_path)
            self._dbc_message_ids = {
                msg.frame_id: msg for msg in self._dbc_decoder.messages
            }
            self._log(f"Loaded DBC: {dbc_path}")
            return True
        except Exception as e:
            self._log(f"DBC load error: {e}")
            return False

    def set_dbc_data(self, decoder, message_ids: Dict[int, Any]):
        self._dbc_decoder = decoder
        self._dbc_message_ids = message_ids

    def get_messages(self) -> List[SimulatedMessage]:
        return self._messages.copy()

    def add_message(
        self,
        can_id: int,
        data: List[int],
        period: float = 1.0,
        extended: bool = True,
        name: str = "",
    ):
        def static_gen():
            return data

        self._messages.append(
            SimulatedMessage(can_id, static_gen, period, extended, name)
        )

    def remove_message(self, can_id: int):
        self._messages = [m for m in self._messages if m.can_id != can_id]

    def update_message(self, can_id: int, **kwargs):
        for msg in self._messages:
            if msg.can_id == can_id:
                if "period" in kwargs:
                    msg.period = kwargs["period"]
                if "name" in kwargs:
                    msg.name = kwargs["name"]
                break

    def start(self, filter_dm1: bool = True):
        if self._running:
            return
        self._running = True
        self._start_time = time.time()
        self._filter_dm1 = filter_dm1
        self._message_cache.clear()
        for msg in self._messages:
            msg.next_time = 0.0
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._log("Simulator started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        self._log("Simulator stopped")

    def is_running(self) -> bool:
        return self._running

    def _run_loop(self):
        while self._running:
            current_time = time.time() - self._start_time

            for msg in self._messages:
                if current_time >= msg.next_time:
                    data = msg.data_generator()

                    if self._filter_dm1 and msg.can_id == 0x708:
                        msg.next_time = current_time + msg.period
                        continue

                    self._emit_message(
                        msg.can_id, data, msg.is_extended, current_time, ""
                    )
                    msg.next_time = current_time + msg.period

            time.sleep(0.01)

    def _emit_message(
        self,
        can_id: int,
        data: List[int],
        is_extended: bool,
        timestamp: float,
        default_name: str = "",
    ):
        raw_data = bytes(data[:8])

        cache = self._message_cache.get(can_id)
        is_update = True
        if cache is None:
            cache = MessageCache()
            self._message_cache[can_id] = cache
        else:
            if cache.last_data == raw_data:
                is_update = False

        cache.last_data = raw_data

        decoded_fields = {}
        dbc_name = None

        if self._dbc_decoder and can_id in self._dbc_message_ids:
            try:
                dbc_msg = self._dbc_message_ids[can_id]
                decoded_fields = dict(dbc_msg.decode(raw_data))
                dbc_name = dbc_msg.name
            except Exception as e:
                logger.debug(f"DBC decode error for {can_id:X}: {e}")

        if not dbc_name and default_name:
            dbc_name = default_name

        decoded_msg = DecodedMessage(
            timestamp=timestamp,
            can_id=can_id,
            message_type=CANMessageType.J1939
            if is_extended
            else CANMessageType.STANDARD,
            raw_data=raw_data,
            decoded_fields=decoded_fields,
            dbc_name=dbc_name,
            is_update=is_update,
        )

        if self._on_message_callback:
            self._on_message_callback(decoded_msg)

    def send_j1939_request(self, pgn: int, dest: int = 0xFF) -> bool:
        self._log(f"Sim: PGN {pgn:06X} request to {dest:02X}")
        if pgn == 0xFECA:
            self._emit_message(
                0x708,
                [0x01, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
                False,
                time.time() - self._start_time,
                "",
            )
        return True

    def send_j1939_command(self, pgn: int, data: List[int], dest: int) -> bool:
        self._log(f"Sim: PGN {pgn:06X} command to {dest:02X}")
        if pgn == 0xFECB:
            self._message_cache.clear()
            self._log("Sim: DM1 cleared")
        return True

    def clear_dm1(self, dest: int) -> bool:
        self._message_cache.clear()
        return self.send_j1939_command(0xFECB, [0x01], dest)

    def request_dm1(self, dest: int) -> bool:
        return self.send_j1939_request(0xFECA, dest)

    def clear_all_dm(self, dest: int) -> bool:
        self._message_cache.clear()
        return self.send_j1939_command(0xFECD, [0x01], dest)
