"""Companion uses the same Atom wire contract; capabilities confirm the bridge."""
from .atom import AtomDriver

class CompanionDriver(AtomDriver):
    expected_controller = 'companion_uart'