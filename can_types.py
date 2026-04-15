from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from enum import Enum


class CANMessageType(Enum):
    J1939 = "j1939"
    STANDARD = "standard"


@dataclass
class DecodedMessage:
    timestamp: float
    can_id: int
    message_type: CANMessageType
    raw_data: bytes
    decoded_fields: Dict[str, Any] = field(default_factory=dict)
    dbc_name: Optional[str] = None
    is_update: bool = True
