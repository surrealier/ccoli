"""Policy action validation. Scripted skills are not learned VLA policies."""
from __future__ import annotations
from typing import Any, Protocol
from .models import RoboticsError, identifier, integer, number

class Policy(Protocol):
    def plan(self, instruction: str, observation: dict, robot_state: dict) -> dict: ...

def validate_policy_plan(plan: Any, robot_state: dict) -> list[dict]:
    caps = robot_state.get('capabilities') or {}
    if caps.get('controller') != 'so101' or caps.get('feedback_kind') != 'measured':
        raise RoboticsError('required_capability_missing')
    if not isinstance(plan, dict) or plan.get('units') != caps.get('units', 'degrees'):
        raise RoboticsError('policy_units_mismatch')
    if caps.get('units') == 'mixed' and plan.get('joint_units') != caps.get('joint_units'):
        raise RoboticsError('policy_joint_units_mismatch')
    if robot_state.get('source') == 'physical' and (not robot_state.get('sdk_calibration_id') or plan.get('sdk_calibration_id') != robot_state['sdk_calibration_id']):
        raise RoboticsError('policy_sdk_calibration_mismatch')
    if plan.get('joint_order') != caps.get('joint_order') or not plan.get('revision'):
        raise RoboticsError('policy_revision_or_joint_order_mismatch')
    revision = plan['revision']
    if not isinstance(revision, str) or not 1 <= len(revision) <= 160:
        raise RoboticsError('policy_revision_invalid')
    actions = plan.get('actions')
    if not isinstance(actions, list) or not 1 <= len(actions) <= 16:
        raise RoboticsError('policy_action_limit')
    channels = robot_state.get('calibration', [])
    previous = list(robot_state.get('measured_angles') or [])
    count = caps.get('servo_count')
    if len(previous) != count or len(channels) != count:
        raise RoboticsError('measurement_required')
    validated = []
    for action in actions:
        if not isinstance(action, dict) or set(action) != {'joints', 'duration_ms'}:
            raise RoboticsError('policy_action_schema')
        duration = integer(action['duration_ms'], 1, 5000)
        joints = action['joints']
        if not isinstance(joints, list) or len(joints) != count:
            raise RoboticsError('invalid_joint_dimension')
        targets = []
        for index, item in enumerate(joints):
            if not isinstance(item, dict) or set(item) != {'servo', 'angle'}:
                raise RoboticsError('policy_action_schema')
            if integer(item['servo'], 0, count-1) != index:
                raise RoboticsError('invalid_joint_order')
            channel = channels[index]
            target = number(item['angle'], channel['min_angle'], channel['max_angle'])
            if abs(target-previous[index]) / (duration/1000) > channel['max_speed_dps'] + 1e-9:
                raise RoboticsError('speed_limit')
            targets.append(target)
        previous = targets
        validated.append({'op': 'move_joints', 'joints': [{'servo': i, 'angle': a} for i,a in enumerate(targets)],
                          'duration_ms': duration})
    return validated