"""Small state machine. A transport acceptance is never physical task success."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import secrets
import threading
import time
from typing import Any, Callable, Protocol

from .models import (Capabilities, CalibrationChannel, GESTURES, MAX_FRAME_BYTES,
                     RoboticsError, calibration_id, gesture_trajectory, identifier, integer, joint_bounds, number)
from .profiles import validate_profile

class Transport(Protocol):
    def send(self, payload: dict[str, Any]) -> None: ...

class RobotController:
    def __init__(self, transport: Transport, *, clock: Callable[[], float] = time.monotonic,
                 calibration_path: str | Path | None = None, observation_store: Any = None):
        self.transport = transport
        self.clock = clock
        self.calibration_path = Path(calibration_path) if calibration_path else None
        self.observations = observation_store
        self._lock = threading.RLock()
        self._dispatch_lock = threading.Lock()
        self._profile_generation = 0
        self._session = secrets.token_hex(12)
        self._seq = 0
        self._state = 'disconnected'
        self._caps: Capabilities | None = None
        self._profile_id: str | None = None
        self._profile: dict | None = None
        self._channels: list[CalibrationChannel] = []
        self._calibrated = False
        self._armed = False
        self._pending: dict[str, dict] = {}
        self._recent: dict[str, dict] = {}
        self._active: str | None = None
        self._angles: list[float] = []
        self._measured: list[float] | None = None
        self._last_result: dict | None = None
        self._last_error: str | None = None
        self._lease_until = 0.0
        self._last_feedback = 0.0
        self._sdk_calibration_id: str | None = None
        self._latencies: list[float] = []
        self._stop_latencies: list[float] = []
        self._feedback_times: list[float] = []
        self._timeouts = 0
        self._stop_count = 0
        self._required_stop: str | None = None

    @property
    def source(self) -> str:
        return str(getattr(self.transport, 'source', 'physical'))

    def _invalidate(self, reason: str, state: str) -> None:
        self._armed = False
        self._calibrated = False
        self._channels = []
        self._pending.clear()
        self._recent.clear()
        self._active = None
        self._lease_until = 0
        self._last_error = reason
        self._state = state

    def _require_ready(self) -> None:
        if not self._caps:
            raise RoboticsError('device_not_discovered')
        if not self._profile or not self._profile['servo_count']:
            raise RoboticsError('motion_profile_required')

    def discover(self) -> dict:
        with self._lock:
            self._invalidate('rediscovery', 'disconnected')
            self._session = secrets.token_hex(12)
            self._seq = 0
            self._caps = None
            self._sdk_calibration_id = None
            self._profile = None
            self._profile_id = None
            self._profile_generation += 1
            self._angles = []
            self._measured = None
        return self._command('discover')

    def configure(self, profile_id: str) -> dict:
        with self._lock:
            if not self._caps:
                raise RoboticsError('device_not_discovered')
            if self._armed or self._active:
                raise RoboticsError('stop_before_configuration')
            if any(p['op'] in {'discover', 'calibrate', 'arm'} or p['action'] for p in self._pending.values()):
                raise RoboticsError('device_busy')
            profile = validate_profile(profile_id, self._caps)
            self._profile_generation += 1
            self._profile_id = profile_id
            self._profile = profile
            self._channels = []
            self._calibrated = False
            self._state = 'configured'
            return self.snapshot()

    def calibrate(self, channels: list[dict]) -> dict:
        with self._lock:
            self._require_ready()
            if self._armed or self._active:
                raise RoboticsError('stop_before_calibration')
            count = self._profile['servo_count']
            if not isinstance(channels, list) or len(channels) != count:
                raise RoboticsError('invalid_calibration_count')
            session = self._session
            generation = self._profile_generation
            parsed = [CalibrationChannel.parse(c, count, bounds=joint_bounds(self._caps, i)) for i, c in enumerate(channels)]
            if [c.servo for c in parsed] != list(range(count)):
                raise RoboticsError('invalid_joint_order')
        return self._command('calibrate', {'channels': [c.public() for c in parsed]},
                             extra={'channels': parsed}, expected_session=session, expected_generation=generation)

    def arm(self) -> dict:
        with self._lock:
            self._require_ready()
            if not self._calibrated or self._state not in {'calibrated', 'armed', 'completed'}:
                raise RoboticsError('calibration_required')
            if self._active:
                raise RoboticsError('device_busy')
            if self._caps.controller == 'so101' and self.source == 'physical' and not self._sdk_calibration_id:
                raise RoboticsError('sdk_calibration_required')
            session = self._session
            generation = self._profile_generation
        return self._command('arm', {'lease_ms': 2000}, expected_session=session, expected_generation=generation)

    def _validate_move(self, servo: Any, angle: Any, duration_ms: Any) -> float:
        self._require_ready()
        if not self._calibrated or not self._armed or self.clock() >= self._lease_until:
            raise RoboticsError('device_not_armed')
        if self._active:
            raise RoboticsError('device_busy')
        servo = integer(servo, 0, len(self._channels) - 1, 'invalid_servo')
        if len(self._angles) <= servo:
            raise RoboticsError('position_unknown')
        return self._channels[servo].validate_move(angle, self._angles[servo], duration_ms)

    def move(self, servo: int, angle: float, duration_ms: int = 1000, *, expected_session: str | None = None) -> dict:
        with self._lock:
            if expected_session is not None and expected_session != self._session:
                raise RoboticsError('stale_authorization')
            value = self._validate_move(servo, angle, duration_ms)
            session = self._session
        return self._command('move', {'servo': servo, 'angle': value,
                                      'duration_ms': duration_ms, 'lease_ms': 2000}, action=True, expected_session=session)

    def move_joints(self, joints: list[dict], duration_ms: int = 1000, *, expected_session: str | None = None) -> dict:
        with self._lock:
            if expected_session is not None and expected_session != self._session:
                raise RoboticsError('stale_authorization')
            if not self._caps or self._caps.controller != 'so101':
                raise RoboticsError('vector_action_unsupported')
            if not isinstance(joints, list) or len(joints) != len(self._channels):
                raise RoboticsError('invalid_joint_dimension')
            session = self._session
            validated = []
            for i, item in enumerate(joints):
                if not isinstance(item, dict) or set(item) != {'servo', 'angle'} or item['servo'] != i:
                    raise RoboticsError('invalid_joint_order')
                value = self._validate_move(item['servo'], item['angle'], duration_ms)
                validated.append({'servo': i, 'angle': value})
        return self._command('move', {'joints': validated, 'duration_ms': duration_ms,
                                      'lease_ms': 2000}, action=True, expected_session=session)

    def gesture(self, gesture_id: str, intensity: float = .3, *, expected_session: str | None = None) -> dict:
        with self._lock:
            if expected_session is not None and expected_session != self._session:
                raise RoboticsError('stale_authorization')
            self._require_ready()
            if not self._armed or not self._calibrated or self.clock() >= self._lease_until:
                raise RoboticsError('device_not_armed')
            if self._active:
                raise RoboticsError('device_busy')
            if not isinstance(gesture_id, str) or gesture_id not in GESTURES:
                raise RoboticsError('unknown_gesture')
            if self._caps.controller == 'so101':
                raise RoboticsError('gesture_unsupported')
            value = number(intensity, 0, 1, 'invalid_intensity')
            trajectory = gesture_trajectory(gesture_id, value, self._channels, self._angles, self._caps.servo_count)
            duration_s = sum(step['duration_ms'] for step in trajectory)/1000
            session = self._session
        return self._command('gesture', {'id': gesture_id, 'intensity': value,
                                         'lease_ms': 2000}, action=True, expected_session=session,
                             extra={'duration_s': duration_s})

    def stop(self, mode: str = 'detach') -> dict:
        if mode not in {'detach', 'hold'}:
            raise RoboticsError('invalid_stop_mode')
        # No model or action lock is acquired. Transport supplies priority send.
        with self._lock:
            self._invalidate('stopped', 'stopped')
            self._stop_count += 1
        return self._command('stop', {'mode': mode})

    def heartbeat(self) -> dict | None:
        with self._lock:
            if not self._armed:
                return None
        return self._command('heartbeat', {'lease_ms': 2000})

    def request_state(self) -> dict:
        with self._lock:
            if not self._caps:
                raise RoboticsError('device_not_discovered')
        return self._command('state')

    def _command(self, op: str, args: dict | None = None, *, action: bool = False,
                 extra: dict | None = None, expected_session: str | None = None,
                 expected_generation: int | None = None) -> dict:
        values = dict(action=action, extra=extra, expected_session=expected_session,
                      expected_generation=expected_generation)
        if op == 'stop':
            return self._dispatch_command(op, args, **values)
        with self._dispatch_lock:
            return self._dispatch_command(op, args, **values)

    def _dispatch_command(self, op: str, args: dict | None = None, *, action: bool = False,
                          extra: dict | None = None, expected_session: str | None = None,
                          expected_generation: int | None = None) -> dict:
        with self._lock:
            if expected_generation is not None and expected_generation != self._profile_generation:
                raise RoboticsError('stale_configuration')
            if expected_session is not None and expected_session != self._session:
                raise RoboticsError('stale_authorization')
            if action and (not self._armed or not self._calibrated):
                raise RoboticsError('device_not_armed')
            if action and self._active:
                raise RoboticsError('device_busy')
            if op == 'arm' and not self._calibrated:
                raise RoboticsError('calibration_required')
            if op in {'arm', 'calibrate'} and any(p['op'] in {'arm', 'calibrate'} for p in self._pending.values()):
                raise RoboticsError('device_busy')
            if len(self._pending) >= 32:
                raise RoboticsError('too_many_pending_commands')
            self._seq += 1
            if self._seq > 0xffffffff:
                self._invalidate('sequence_exhausted', 'fault')
                raise RoboticsError('sequence_exhausted')
            command_id = secrets.token_hex(12)
            payload = {'cmd': 'ROBOT_CONTROL', 'v': 1, 'op': op, 'command_id': command_id,
                       'session_id': self._session, 'boot_id': self._caps.boot_id if self._caps else '',
                       'seq': self._seq, 'valid_for_ms': 2000, 'lease_ms': 2000}
            payload.update(args or {})
            raw = json.dumps(payload, allow_nan=False, separators=(',', ':')).encode()
            if len(raw) > MAX_FRAME_BYTES:
                raise RoboticsError('frame_too_large')
            now = self.clock()
            self._pending[command_id] = {'op': op, 'seq': self._seq,
                'started': now, 'deadline': now + (extra or {}).get('duration_s', payload.get('duration_ms', 0) / 1000) + 2,
                'extra': extra or {}, 'action': action, 'acked': False, 'generation': expected_generation}
            self._recent[command_id] = copy.copy(self._pending[command_id])
            while len(self._recent) > 64:
                self._recent.pop(next(iter(self._recent)))
            if action:
                self._active = command_id
                self._state = 'executing'
                self._lease_until = now + 2
            result = {'command_id': command_id, 'session_id': self._session,
                      'status': 'pending', 'physical_success': None, 'source': self.source}
        try:
            self.transport.send(copy.deepcopy(payload))
        except Exception:
            with self._lock:
                self._invalidate('transport_failed', 'fault')
            raise RoboticsError('transport_failed') from None
        return result

    def accept(self, packet: dict) -> bool:
        accepted = self._accept_status(packet)
        with self._lock:
            reason = self._required_stop
            self._required_stop = None
        if reason:
            # Dispatch after releasing the state lock; physical ERROR cannot
            # leave an older motion alive until the next heartbeat timeout.
            try:
                self.stop()
            except RoboticsError:
                pass
            with self._lock:
                self._invalidate(reason, 'fault')
        return accepted

    def _accept_status(self, packet: dict) -> bool:
        if not isinstance(packet, dict):
            return False
        try:
            if integer(packet.get('v'), 1, 1) != 1:
                return False
            command_id = identifier(packet.get('command_id'))
            session = identifier(packet.get('session_id'))
            boot = identifier(packet.get('boot_id'))
            seq = integer(packet.get('seq'), 1, 0xffffffff)
            status = packet.get('status')
            if status not in {'ACK', 'RUNNING', 'DONE', 'ERROR', 'STOPPED'}:
                return False
            if type(packet.get('armed')) is not bool:
                return False
        except RoboticsError:
            return False
        with self._lock:
            pending = self._pending.get(command_id)
            asynchronous_stop = False
            if not pending and status == 'STOPPED' and self._armed:
                pending = self._recent.get(command_id)
                asynchronous_stop = pending is not None
            # Unsolicited watchdog STOPPED is accepted only for the exact active
            # command; arbitrary/stale packets never reset a new session.
            if not pending or session != self._session or seq != pending['seq']:
                return False
            if pending.get('generation') is not None and pending['generation'] != self._profile_generation:
                return False
            if packet.get('op') != pending['op']:
                return False
            if not asynchronous_stop and self.clock() > pending['deadline']:
                return False
            if pending['op'] != 'discover' and self._caps and boot != self._caps.boot_id:
                self._invalidate('boot_changed', 'disconnected')
                return False
            candidate_caps = self._caps
            if pending['op'] == 'discover' and status not in {'ERROR', 'STOPPED'}:
                try:
                    caps = Capabilities.parse(packet.get('capabilities'))
                    if caps.boot_id != boot:
                        return False
                except RoboticsError:
                    return False
                candidate_caps = caps
            candidate_sdk_id = packet.get('sdk_calibration_id')
            if candidate_sdk_id is None and pending['op'] == 'discover':
                candidate_sdk_id = packet.get('capabilities', {}).get('sdk_calibration_id')
            if candidate_sdk_id == '' and candidate_caps and candidate_caps.controller == 'so101':
                candidate_sdk_id = None
            if status in {'ERROR', 'STOPPED'}:
                candidate_sdk_id = None
            try:
                if candidate_sdk_id is not None:
                    calibration_id(candidate_sdk_id)
            except RoboticsError:
                return False
            if self._sdk_calibration_id and candidate_sdk_id and candidate_sdk_id != self._sdk_calibration_id and self._armed:
                self._invalidate('sdk_calibration_changed', 'fault')
                self._required_stop = 'sdk_calibration_changed'
                return False
            if candidate_caps is None:
                if pending['op'] == 'stop' and status in {'STOPPED', 'DONE'} and not packet['armed']:
                    self._stop_latencies.append(self.clock()-pending['started'])
                    self._invalidate('stopped', 'stopped')
                    return True
                if status == 'ERROR':
                    self._invalidate('device_error', 'fault')
                    self._required_stop = 'device_error'
                    return True
                return False
            count = candidate_caps.servo_count
            if status in {'ERROR', 'STOPPED'}:
                # The failure itself is authoritative even when unplugging the
                # device makes an optional telemetry read impossible.
                values = packet.get('commanded_angles')
                try:
                    if isinstance(values, list) and len(values) == count:
                        self._angles = [number(a, *joint_bounds(candidate_caps, i)) for i,a in enumerate(values)]
                except RoboticsError:
                    pass
                if pending['action']:
                    self._latencies.append(self.clock()-pending['started'])
                    self._latencies = self._latencies[-256:]
                    self._last_result = {'command_id': command_id, 'status': status.lower(),
                        'physical_success': None, 'source': self.source, 'at': self.clock()}
                if pending['op'] == 'stop' and status == 'STOPPED':
                    self._stop_latencies.append(self.clock()-pending['started'])
                    self._stop_latencies = self._stop_latencies[-128:]
                reason = packet.get('error', 'device_error' if status == 'ERROR' else 'stopped')
                if not isinstance(reason, str) or not reason.isascii() or len(reason) > 64:
                    reason = 'device_error'
                self._invalidate(reason, 'fault' if status == 'ERROR' else 'stopped')
                if status == 'ERROR':
                    self._required_stop = reason
                return True
            angles = packet.get('commanded_angles', [])
            measured = packet.get('measured_angles')
            try:
                if not isinstance(angles, list) or len(angles) != count:
                    return False
                angles = [number(a, *joint_bounds(candidate_caps, i)) for i, a in enumerate(angles)]
                if candidate_caps.feedback_kind == 'measured' and measured is None and status not in {'ERROR', 'STOPPED'}:
                    return False
                if measured is not None:
                    if candidate_caps.feedback_kind != 'measured' or not isinstance(measured, list) or len(measured) != count:
                        return False
                    measured = [number(a, *joint_bounds(candidate_caps, i)) for i, a in enumerate(measured)]
                if packet.get('feedback_kind') != candidate_caps.feedback_kind:
                    return False
            except RoboticsError:
                return False
            self._caps = candidate_caps
            if candidate_sdk_id is not None:
                self._sdk_calibration_id = candidate_sdk_id
            self._angles = angles
            self._measured = measured
            self._last_feedback = self.clock()
            self._feedback_times.append(self._last_feedback)
            self._feedback_times = self._feedback_times[-128:]
            if pending['op'] == 'stop' and status == 'STOPPED':
                self._stop_latencies.append(self.clock()-pending['started'])
                self._stop_latencies = self._stop_latencies[-128:]
            if pending['action'] and status in {'ACK', 'RUNNING'} and not packet['armed']:
                self._invalidate('device_disarmed', 'stopped')
                return True
            if status == 'ACK':
                pending['acked'] = True
                if pending['op'] == 'discover':
                    self._state = 'discovered'
                return True
            if status == 'RUNNING':
                if pending['action']:
                    self._state = 'executing'
                return True
            self._pending.pop(command_id, None)
            if pending['action']:
                self._active = None
                self._latencies.append(self.clock() - pending['started'])
                self._latencies = self._latencies[-256:]
                self._last_result = {'command_id': command_id, 'status': status.lower(),
                    'physical_success': None, 'source': self.source, 'at': self.clock()}

            op = pending['op']
            if op == 'discover':
                self._state = 'discovered'
            elif op == 'calibrate':
                self._channels = pending['extra']['channels']
                self._calibrated = True
                self._state = 'calibrated'
                self._save_calibration()
            elif op == 'arm':
                if not packet['armed'] or not self._calibrated:
                    self._invalidate('arm_rejected', 'fault')
                    return True
                self._armed = True
                self._lease_until = self.clock() + 2
                self._state = 'armed'
            elif op in {'heartbeat', 'state'}:
                if self._armed and not packet['armed']:
                    self._invalidate('device_disarmed', 'stopped')
                elif op == 'heartbeat' and self._armed:
                    self._lease_until = self.clock() + 2
            elif op == 'stop':
                self._invalidate('stopped', 'stopped')
            elif pending['action']:
                self._armed = packet['armed']
                self._state = 'completed'
            self._last_error = None if self._state not in {'stopped', 'fault'} else self._last_error
            return True

    def _save_calibration(self) -> None:
        if not self.calibration_path:
            return
        value = {'v': 1, 'device_id': self._caps.device_id, 'boot_id': self._caps.boot_id,
                 'firmware_revision': self._caps.firmware_revision, 'profile_id': self._profile_id,
                 'channels': [c.public() for c in self._channels], 'sdk_calibration_id': self._sdk_calibration_id}
        self.calibration_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.calibration_path.with_suffix(self.calibration_path.suffix + '.tmp')
        temporary.write_text(json.dumps(value, allow_nan=False), encoding='utf-8')
        temporary.replace(self.calibration_path)

    def saved_calibration(self) -> dict | None:
        """Validated reapply material, never automatic calibration or arming."""
        if not self.calibration_path or not self.calibration_path.is_file():
            return None
        try:
            if self.calibration_path.stat().st_size > 8192:
                raise RoboticsError('invalid_saved_calibration')
            value = json.loads(self.calibration_path.read_text(encoding='utf-8'))
            required = {'v', 'device_id', 'boot_id', 'firmware_revision', 'profile_id', 'channels'}
            if not isinstance(value, dict) or not required <= set(value) or set(value)-required-{'sdk_calibration_id'}:
                raise RoboticsError('invalid_saved_calibration')
            integer(value['v'], 1, 1)
            for key in ('device_id', 'boot_id', 'firmware_revision', 'profile_id'):
                identifier(value[key])
            if not self._caps or not self._profile or value['device_id'] != self._caps.device_id or value['firmware_revision'] != self._caps.firmware_revision or value['profile_id'] != self._profile_id:
                raise RoboticsError('calibration_binding_mismatch')
            channels = value['channels']
            count = self._profile['servo_count']
            if not isinstance(channels, list) or len(channels) != count:
                raise RoboticsError('invalid_saved_calibration')
            parsed = [CalibrationChannel.parse(c, count, bounds=joint_bounds(self._caps, i)) for i,c in enumerate(channels)]
            if [c.servo for c in parsed] != list(range(count)):
                raise RoboticsError('invalid_joint_order')
            saved_sdk = value.get('sdk_calibration_id')
            if saved_sdk is not None:
                calibration_id(saved_sdk)
                if self._sdk_calibration_id and saved_sdk != self._sdk_calibration_id:
                    raise RoboticsError('calibration_binding_mismatch')
            value['boot_matches'] = value['boot_id'] == self._caps.boot_id
            value['requires_reapply'] = True
            return value
        except RoboticsError:
            raise
        except (OSError, ValueError, TypeError, AttributeError):
            raise RoboticsError('invalid_saved_calibration') from None
    def disconnected(self) -> None:
        with self._lock:
            self._invalidate('disconnected', 'disconnected')
            self._caps = None
            self._sdk_calibration_id = None
            self._measured = None

    def poll(self) -> None:
        with self._lock:
            expired = [p for p in self._pending.values() if self.clock() > p['deadline']]
            lease_expired = self._armed and self.clock() >= self._lease_until
            if not expired and not lease_expired:
                return
            active = self._active
            self._timeouts += len(expired)
            self._last_result = {'command_id': active, 'status': 'timeout',
                                 'physical_success': None, 'source': self.source, 'at': self.clock()}
        try:
            self.stop()
        except RoboticsError:
            pass
        with self._lock:
            self._invalidate('command_timeout' if expired else 'lease_expired', 'fault')

    def snapshot(self) -> dict:
        with self._lock:
            samples = sorted(self._latencies)
            stop_samples = sorted(self._stop_latencies)
            stop_quantile = lambda q: stop_samples[min(len(stop_samples)-1, max(0, math.ceil(len(stop_samples)*q)-1))] if stop_samples else None
            feedback_hz = (len(self._feedback_times)-1)/(self._feedback_times[-1]-self._feedback_times[0]) if len(self._feedback_times)>1 and self._feedback_times[-1]>self._feedback_times[0] else None
            quantile = lambda q: samples[min(len(samples)-1, max(0, math.ceil(len(samples)*q)-1))] if samples else None
            return {'state': self._state, 'source': self.source, 'profile_id': self._profile_id,
                'session_id': self._session, 'profile_generation': self._profile_generation,
                'capabilities': self._caps.public() if self._caps else None,
                'sdk_calibration_id': self._sdk_calibration_id,
                'calibrated': self._calibrated, 'armed': self._armed,
                'commanded_angles': list(self._angles),
                'measured_angles': copy.deepcopy(self._measured),
                'feedback_kind': self._caps.feedback_kind if self._caps else None,
                'feedback_age_s': self.clock() - self._last_feedback if self._last_feedback else None,
                'calibration': [c.public() for c in self._channels],
                'active_command_id': self._active, 'last_result': copy.deepcopy(self._last_result),
                'last_error': self._last_error, 'pending_count': len(self._pending),
                'metrics': {'action_samples': len(samples), 'action_p50_s': quantile(.5),
                            'action_p95_s': quantile(.95), 'timeouts': self._timeouts,
                            'stops': self._stop_count, 'stop_latency_p50_s': stop_quantile(.5),
                            'stop_latency_p95_s': stop_quantile(.95), 'feedback_hz': feedback_hz}}