"""No-hardware emulator using exactly the physical command/result contract."""
from __future__ import annotations
import copy
import secrets
import time
from typing import Callable
from ..models import (Capabilities, CalibrationChannel, GESTURES, RoboticsError,
                      gesture_trajectory, identifier, integer, joint_bounds, number)

class SimDriver:
    source = 'sim'

    def __init__(self, *, clock: Callable[[], float] = time.monotonic, servo_count: int = 2,
                 display: str = 'none', feedback_kind: str = 'measured',
                 controller: str = 'legacy_direct', joint_units: list[str] | None = None):
        self.clock = clock
        self.capabilities = {'device_id': 'sim-robot', 'boot_id': secrets.token_hex(8),
            'controller': controller, 'servo_count': servo_count, 'display': display,
            'feedback_kind': feedback_kind, 'sensors': ['button', 'temperature'],
            'firmware_revision': 'robot-control-1'}
        if controller == 'so101':
            self.capabilities['joint_order'] = [f'joint_{i}' for i in range(servo_count)]
            self.capabilities['units'] = 'mixed' if joint_units and 'percent' in joint_units else 'degrees'
            self.capabilities['joint_units'] = joint_units or ['degrees'] * servo_count
        Capabilities.parse(self.capabilities)
        self.angles = [90.0] * servo_count
        self.armed = False
        self.channels: list[CalibrationChannel] = []
        self.session = ''
        self.seq = 0
        self.lease_until = 0.0
        self.action: dict | None = None
        self.action_count = 0
        self.sent: list[dict] = []
        self.last_status: dict = {}
        self._cache: dict[str, dict] = {}
        self._sink: Callable[[dict], object] = lambda value: None
        self._fault: str | None = None

    def attach(self, sink: Callable[[dict], object]) -> None:
        self._sink = sink

    def inject_fault(self, fault: str | None) -> None:
        if fault not in {None, 'drop', 'error', 'freeze', 'disconnect'}:
            raise RoboticsError('unknown_fault')
        self._fault = fault

    def reboot(self) -> None:
        self.capabilities['boot_id'] = secrets.token_hex(8)
        self.armed = False
        self.channels = []
        self.action = None
        self.session = ''
        self.seq = 0
        self._cache.clear()

    def _status(self, payload: dict, status: str, error: str | None = None) -> None:
        value = {k: payload.get(k) for k in ('op', 'command_id', 'session_id', 'seq')}
        value.update(v=1, status=status, boot_id=self.capabilities['boot_id'],
                     armed=self.armed, commanded_angles=list(self.angles),
                     feedback_kind=self.capabilities['feedback_kind'])
        if self.capabilities['feedback_kind'] == 'measured':
            value['measured_angles'] = list(self.angles)
        if payload.get('op') == 'discover':
            value['capabilities'] = copy.deepcopy(self.capabilities)
        if self.capabilities.get('sdk_calibration_id'):
            value['sdk_calibration_id'] = self.capabilities['sdk_calibration_id']
        if error:
            value['error'] = error
        self.last_status = value
        if isinstance(payload.get('command_id'), str):
            self._cache[payload['command_id']] = copy.deepcopy(value)
            while len(self._cache) > 64:
                self._cache.pop(next(iter(self._cache)))
        if self._fault not in {'drop', 'disconnect'}:
            self._sink(copy.deepcopy(value))

    def send(self, payload: dict) -> None:
        self.sent.append(copy.deepcopy(payload))
        self.sent = self.sent[-256:]
        if self._fault == 'disconnect':
            raise RoboticsError('transport_disconnected')
        try:
            if not isinstance(payload, dict) or payload.get('cmd') != 'ROBOT_CONTROL':
                raise RoboticsError('invalid_command')
            integer(payload.get('v'), 1, 1)
            identifier(payload.get('command_id'))
            identifier(payload.get('session_id'))
            integer(payload.get('seq'), 1, 0xffffffff)
            integer(payload.get('valid_for_ms'), 1, 2000)
            integer(payload.get('lease_ms'), 1, 2000)
            op = payload.get('op')
            # STOP is unconditional and idempotent, including stale session/boot.
            if op == 'stop':
                if payload.get('mode', 'detach') not in {'hold', 'detach'}:
                    raise RoboticsError('invalid_stop_mode')
                self.action = None
                self.armed = False
                self.channels = []
                self.session = ''
                self._cache.clear()
                self._status(payload, 'STOPPED')
                return
            key = payload['command_id']
            if key in self._cache and self.session == payload['session_id'] and payload.get('boot_id') == self.capabilities['boot_id'] and self._cache[key]['session_id'] == payload['session_id']:
                self._sink(copy.deepcopy(self._cache[key]))
                return
            if op == 'discover':
                self.armed = False
                self.action = None
                self.channels = []
                self.session = payload['session_id']
                self.seq = payload['seq']
                self._status(payload, 'DONE')
                return
            if payload.get('boot_id') != self.capabilities['boot_id'] or payload['session_id'] != self.session:
                raise RoboticsError('session_mismatch')
            if payload['seq'] <= self.seq:
                raise RoboticsError('stale_sequence')
            self.seq = payload['seq']
            if self._fault == 'error':
                raise RoboticsError('injected_failure')
            if op == 'calibrate':
                values = payload.get('channels')
                if not isinstance(values, list) or not 1 <= len(values) <= len(self.angles) or self.armed:
                    raise RoboticsError('invalid_calibration')
                caps = Capabilities.parse(self.capabilities)
                self.channels = [CalibrationChannel.parse(c, len(self.angles), bounds=joint_bounds(caps, i)) for i,c in enumerate(values)]
                if [c.servo for c in self.channels] != list(range(len(values))):
                    raise RoboticsError('invalid_joint_order')
                for channel in self.channels:
                    self.angles[channel.servo] = channel.center_angle
                self._status(payload, 'DONE')
            elif op in {'arm', 'heartbeat'}:
                if not self.channels or (op == 'heartbeat' and not self.armed):
                    raise RoboticsError('calibration_required')
                self.armed = True
                self.lease_until = self.clock() + integer(payload.get('lease_ms'), 1, 2000) / 1000
                self._status(payload, 'DONE')
            elif op == 'state':
                self._status(payload, 'DONE')
            elif op in {'move', 'gesture'}:
                if not self.armed or self.clock() >= self.lease_until:
                    raise RoboticsError('device_not_armed')
                if self.action:
                    raise RoboticsError('device_busy')
                duration = integer(payload.get('duration_ms'), 1, 5000) if op == 'move' else 300
                targets = list(self.angles)
                if op == 'move':
                    joints = payload.get('joints')
                    if joints is not None:
                        if self.capabilities['controller'] != 'so101' or not isinstance(joints, list) or len(joints) != len(self.channels):
                            raise RoboticsError('invalid_joint_dimension')
                    else:
                        joints = [{'servo': payload.get('servo'), 'angle': payload.get('angle')}]
                    for item in joints:
                        servo = integer(item.get('servo'), 0, len(self.channels) - 1, 'invalid_servo')
                        targets[servo] = self.channels[servo].validate_move(item.get('angle'), self.angles[servo], duration)
                else:
                    if payload.get('id') not in GESTURES:
                        raise RoboticsError('unknown_gesture')
                    intensity = number(payload.get('intensity'), 0, 1)
                    if 'duration_ms' in payload:
                        raise RoboticsError('unknown_field')
                    segments = gesture_trajectory(payload['id'], intensity, self.channels, self.angles, len(self.angles))
                    first = segments.pop(0)
                    duration = first['duration_ms']
                    targets[first['servo']] = first['angle']
                self.lease_until = self.clock() + integer(payload.get('lease_ms'), 1, 2000) / 1000
                self.action = {'payload': copy.deepcopy(payload), 'start': self.clock(),
                               'duration': duration / 1000, 'from': list(self.angles), 'to': targets,
                               'segments': segments if op == 'gesture' else []}
                self.action_count += 1
                self._status(payload, 'ACK')
                self._status(payload, 'RUNNING')
            else:
                raise RoboticsError('unknown_operation')
        except RoboticsError as error:
            self._status(payload, 'ERROR', error.code)

    def tick(self) -> None:
        if self.armed and self.clock() >= self.lease_until:
            payload = self.action['payload'] if self.action else self.sent[-1]
            self.armed = False
            self.action = None
            self.channels = []
            self.session = ''
            self._status(payload, 'STOPPED', 'lease_expired')
            return
        if not self.action or self._fault == 'freeze':
            return
        while self.action:
            action = self.action
            elapsed = self.clock() - action['start']
            progress = min(1.0, max(0.0, elapsed / action['duration']))
            if elapsed + 1e-9 >= action['duration']: progress = 1.0
            self.angles = [a + (b-a) * progress for a, b in zip(action['from'], action['to'])]
            if progress < 1:
                break
            if action['segments']:
                segment = action['segments'].pop(0)
                action['start'] += action['duration']
                action['duration'] = segment['duration_ms']/1000
                action['from'] = list(self.angles)
                action['to'] = list(self.angles)
                action['to'][segment['servo']] = segment['angle']
            else:
                self.action = None
                self._status(action['payload'], 'DONE')