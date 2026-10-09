"""Atom transport boundary; encoding/framing belongs to the host connection."""
from __future__ import annotations
import copy
from typing import Callable
from ..models import RoboticsError

class AtomDriver:
    source = 'physical'

    def __init__(self, sender: Callable[[dict], None], *, connected: Callable[[], bool] | None = None,
                 priority_sender: Callable[[dict], None] | None = None):
        self.sender = sender
        self.connected = connected or (lambda: True)
        self.priority_sender = priority_sender or sender

    def send(self, payload: dict) -> None:
        if payload.get('op') != 'stop' and not self.connected():
            raise RoboticsError('transport_disconnected')
        sender = self.priority_sender if payload.get('op') == 'stop' else self.sender
        sender(copy.deepcopy(payload))