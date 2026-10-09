"""Strict, dependency-free contracts for bounded robot control."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import re
from typing import Any

PROTOCOL_VERSION = 1
MAX_FRAME_BYTES = 2048
MAX_LEASE_MS = 2000
MAX_DURATION_MS = 5000
GESTURES = frozenset({'farewell_wave', 'goodnight_settle', 'curious_tilt',
                      'happy_bounce', 'hurt_turnaway', 'idle_stretch',
                      'notification_nod', 'camera_scan'})

class RoboticsError(ValueError):
    """A stable reason code, suitable for localization without internal details."""
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)

def number(value: Any, low: float, high: float, code: str = 'invalid_number') -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RoboticsError(code)
    if not math.isfinite(value) or not low <= value <= high:
        raise RoboticsError(code)
    return float(value)

def integer(value: Any, low: int, high: int, code: str = 'invalid_integer') -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise RoboticsError(code)
    return value

def identifier(value: Any, code: str = 'invalid_identifier', *, empty: bool = False) -> str:
    if empty and value == '':
        return value
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,48}', value):
        raise RoboticsError(code)
    return value

@dataclass(frozen=True)
class Capabilities:
    device_id: str
    boot_id: str
    controller: str
    servo_count: int
    display: str
    feedback_kind: str
    sensors: tuple[str, ...]
    firmware_revision: str
    joint_order: tuple[str, ...] = ()
    units: str = 'degrees'
    joint_units: tuple[str, ...] = ()

    @classmethod
    def parse(cls, data: Any) -> 'Capabilities':
        if not isinstance(data, dict):
            raise RoboticsError('invalid_capabilities')
        controller = data.get('controller')
        if controller not in {'legacy_direct', 'companion_uart', 'so101'}:
            raise RoboticsError('unsupported_controller')
        count = integer(data.get('servo_count'), 0, 8, 'invalid_servo_count')
        if controller == 'legacy_direct' and count > 2:
            raise RoboticsError('invalid_servo_count')
        if controller == 'companion_uart' and count > 4:
            raise RoboticsError('invalid_servo_count')
        display = data.get('display')
        if display not in {'none', 'ssd1306', 'st7789v2_240x280'}:
            raise RoboticsError('unsupported_display')
        if controller == 'legacy_direct' and display == 'st7789v2_240x280' and count:
            raise RoboticsError('pin_conflict')
        feedback = data.get('feedback_kind')
        if feedback not in {'commanded', 'measured'}:
            raise RoboticsError('invalid_feedback_kind')
        sensors = data.get('sensors', [])
        if not isinstance(sensors, list) or len(sensors) > 16:
            raise RoboticsError('invalid_sensors')
        sensors = tuple(identifier(s) for s in sensors)
        if len(set(sensors)) != len(sensors):
            raise RoboticsError('invalid_sensors')
        joints = data.get('joint_order', [])
        if not isinstance(joints, list) or (joints and len(joints) != count):
            raise RoboticsError('invalid_joint_order')
        joints = tuple(identifier(j) for j in joints)
        if len(set(joints)) != len(joints):
            raise RoboticsError('invalid_joint_order')
        units = data.get('units', 'degrees')
        if units not in {'degrees', 'mixed'} or (controller != 'so101' and units != 'degrees'):
            raise RoboticsError('unsupported_units')
        joint_units = data.get('joint_units', ['degrees'] * count)
        if not isinstance(joint_units, list) or len(joint_units) != count or any(u not in {'degrees', 'percent'} for u in joint_units):
            raise RoboticsError('invalid_joint_units')
        if units == 'degrees' and any(u != 'degrees' for u in joint_units):
            raise RoboticsError('invalid_joint_units')
        if units == 'mixed' and (controller != 'so101' or joint_units != ['degrees'] * 5 + ['percent']):
            raise RoboticsError('invalid_joint_units')
        return cls(identifier(data.get('device_id')), identifier(data.get('boot_id')),
                   controller, count, display, feedback, sensors,
                   identifier(data.get('firmware_revision')), joints, units, tuple(joint_units))

    def public(self) -> dict[str, Any]:
        value = asdict(self)
        value['sensors'] = list(self.sensors)
        value['joint_order'] = list(self.joint_order)
        value['joint_units'] = list(self.joint_units)
        return value

@dataclass(frozen=True)
class CalibrationChannel:
    servo: int
    min_angle: float
    max_angle: float
    center_angle: float
    max_speed_dps: float
    inverted: bool = False

    @classmethod
    def parse(cls, data: Any, count: int, *, bounds: tuple[float, float] = (0, 180)) -> 'CalibrationChannel':
        keys = {'servo', 'min_angle', 'max_angle', 'center_angle', 'max_speed_dps', 'inverted'}
        if not isinstance(data, dict) or set(data) != keys:
            raise RoboticsError('invalid_calibration')
        servo = integer(data['servo'], 0, count - 1, 'invalid_servo')
        low = number(data['min_angle'], *bounds)
        high = number(data['max_angle'], *bounds)
        center = number(data['center_angle'], *bounds)
        speed = number(data['max_speed_dps'], 1, 90)
        if not low < center < high or type(data['inverted']) is not bool:
            raise RoboticsError('invalid_calibration')
        return cls(servo, low, high, center, speed, data['inverted'])

    def public(self) -> dict[str, Any]:
        return asdict(self)

    def validate_move(self, angle: Any, previous: float, duration_ms: Any) -> float:
        angle = number(angle, self.min_angle, self.max_angle, 'angle_out_of_range')
        duration = integer(duration_ms, 1, MAX_DURATION_MS, 'invalid_duration')
        if abs(angle - previous) / (duration / 1000) > self.max_speed_dps + 1e-9:
            raise RoboticsError('speed_limit')
        return angle
def joint_bounds(capabilities: Capabilities, index: int) -> tuple[float, float]:
    if capabilities.controller == 'so101':
        return (0, 100) if capabilities.joint_units[index] == 'percent' else (-180, 180)
    return (0, 180)
def gesture_trajectory(gesture_id: str, intensity: float, channels: list[CalibrationChannel],
                       current: list[float], servo_count: int) -> list[dict]:
    """Same calibrated 4/5-stage trajectory as CcoliRobotControl.h."""
    if not isinstance(gesture_id, str) or gesture_id not in GESTURES or not channels:
        raise RoboticsError('unknown_gesture')
    intensity = number(intensity, 0, 1)
    channel = 0
    if gesture_id == 'farewell_wave': channel = 3 if servo_count >= 4 else 0
    elif gesture_id in {'curious_tilt', 'hurt_turnaway', 'camera_scan'}: channel = 1 if servo_count >= 2 else 0
    elif gesture_id == 'idle_stretch': channel = 2 if servo_count >= 3 else 0
    if channel >= len(channels): channel = 0
    calibration = channels[channel]
    room = min(calibration.center_angle-calibration.min_angle,
               calibration.max_angle-calibration.center_angle)
    extent = min(room * .3, 18) * intensity
    offsets = [-1, 0, 1, 0, 0] if gesture_id == 'camera_scan' else [-1, 1, -1, 0]
    previous = current[channel]
    result = []
    for offset in offsets:
        target = calibration.center_angle + offset * extent
        duration = max(300, math.ceil(abs(target-previous)*1000/calibration.max_speed_dps))
        result.append({'servo': channel, 'angle': target, 'duration_ms': duration})
        previous = target
    if sum(step['duration_ms'] for step in result) > 5000:
        raise RoboticsError('gesture_duration_limit')
    return result
def calibration_id(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{64}', value):
        raise RoboticsError('invalid_sdk_calibration_id')
    return value