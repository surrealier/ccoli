"""Observe/plan/validate/execute/evaluate with bounded, explicit recovery."""
from __future__ import annotations
import copy
import secrets
import threading
import time
from typing import Any, Callable
from .models import Capabilities, CalibrationChannel, RoboticsError, identifier, integer, joint_bounds, number
from .policies import validate_policy_plan
from .safety import require_authorized

SKILLS = frozenset({'button_press', 'camera_scan', 'notification', 'sensor_actuation', 'object_tidy'})
TERMINAL = frozenset({'idle', 'succeeded', 'failed', 'stopped'})

class TaskRunner:
    def __init__(self, controller, observations, *, clock: Callable[[], float] = time.monotonic,
                 policy=None, recorder=None):
        self.controller = controller
        self.observations = observations
        self.clock = clock
        self.policy = policy
        self.recorder = recorder
        self._lock = threading.RLock()
        self._task: dict = {'status': 'idle'}
        self._steps: list[dict] = []
        self._index = 0
        self._command_id: str | None = None
        self._task_session: str | None = None
        self._baseline = 0
        self._completed_at = 0.0
        self._observation_deadline = 0.0
        self._start_time = 0.0
        self._physical_evidence = False
        self._cancel_requested = False
        self._stats = {'tasks': 0, 'succeeded': 0, 'failed': 0, 'interventions': 0, 'physical_successes': 0}

    def start(self, skill: str, params: dict, *, authorized: bool = False) -> dict:
        require_authorized(authorized)
        with self._lock:
            if skill not in SKILLS or not isinstance(params, dict):
                raise RoboticsError('unknown_skill')
            if self._task['status'] not in TERMINAL:
                raise RoboticsError('task_busy')
            state = self.controller.snapshot()
            if not state['armed'] or not state['calibrated']:
                raise RoboticsError('device_not_armed')
            self._cancel_requested = False
            steps = self._plan(skill, params, state)
            if self._cancel_requested:
                raise RoboticsError('human_stop')
            latest = self.controller.snapshot()
            if latest['session_id'] != state['session_id'] or latest['profile_generation'] != state['profile_generation']:
                raise RoboticsError('stale_authorization')
            if latest['commanded_angles'] != state['commanded_angles']:
                raise RoboticsError('observation_changed_during_planning')
            self._task_session = state['session_id']
            self._validate_steps(steps, state)
            self._stats['tasks'] += 1
            self._steps = steps
            self._index = 0
            self._command_id = None
            self._start_time = self.clock()
            self._physical_evidence = False
            self._task = {'task_id': secrets.token_hex(12), 'skill': skill, 'status': 'planned',
                'phase': 'validate', 'step': 0, 'step_count': len(steps), 'reason_code': None,
                'physical_success': None, 'source': state['source'], 'recovery_attempts': 0,
                'history': ['observe', 'plan', 'validate'], 'started_at': self.clock(),
                'verification': {'frames_captured': 0, 'mechanical_verified_frames': 0, 'mechanical_motion_verified': None} if skill == 'camera_scan' else {}}
            if self.recorder and self.recorder.enabled:
                self.recorder.start(skill, {'source': state['source'],
                    'capabilities': state['capabilities'], 'calibration': state['calibration']})
                self._record('observation', {'robot_state': state, 'observations': self.observations.snapshot(include_frames=True)})
            self._execute()
            return self.snapshot()

    def _observation(self, kind: str, source: str) -> dict:
        identifier(source)
        observation = self.observations.get(kind, source, require_measured=self.controller.source == 'physical')
        if self.controller.source == 'physical' and not observation.get('driver_id'):
            raise RoboticsError('trusted_measurement_required')
        if observation['provenance'] not in {'measured', 'simulated'}:
            raise RoboticsError('measurement_required')
        return observation

    def _sensor(self, source: str) -> dict:
        return self._observation('sensor', source)

    def _plan(self, skill: str, params: dict, state: dict) -> list[dict]:
        if skill == 'notification':
            if set(params) - {'intensity'}:
                raise RoboticsError('invalid_skill_parameters')
            return [{'op': 'gesture', 'id': 'notification_nod',
                     'intensity': number(params.get('intensity', .3), 0, 1), 'expect': {'kind': 'scheduler'}}]
        if skill == 'button_press':
            allowed = {'servo', 'press_angle', 'release_angle', 'sensor_id', 'duration_ms'}
            if set(params) != allowed:
                raise RoboticsError('invalid_skill_parameters')
            sensor = self._sensor(params['sensor_id'])
            if type(sensor['data'].get('pressed')) is not bool or sensor['data']['pressed']:
                raise RoboticsError('button_initial_state_required')
            servo = integer(params['servo'], 0, len(state['calibration'])-1)
            duration = integer(params['duration_ms'], 1, 5000)
            return [{'op': 'move', 'servo': servo, 'angle': params['press_angle'], 'duration_ms': duration,
                     'expect': {'kind': 'sensor', 'source_id': params['sensor_id'], 'field': 'pressed', 'equals': True}},
                    {'op': 'move', 'servo': servo, 'angle': params['release_angle'], 'duration_ms': duration,
                     'expect': {'kind': 'sensor', 'source_id': params['sensor_id'], 'field': 'pressed', 'equals': False}}]
        if skill == 'camera_scan':
            if set(params) != {'servo', 'angles', 'camera_id', 'duration_ms'}:
                raise RoboticsError('invalid_skill_parameters')
            identifier(params['camera_id'])
            if not isinstance(params['angles'], list) or not 1 <= len(params['angles']) <= 8:
                raise RoboticsError('scan_step_limit')
            return [{'op': 'move', 'servo': params['servo'], 'angle': angle,
                     'duration_ms': params['duration_ms'],
                     'expect': {'kind': 'rgb', 'source_id': params['camera_id']}}
                    for angle in params['angles']]
        if skill == 'sensor_actuation':
            allowed = {'sensor_id', 'field', 'above', 'servo', 'angle', 'duration_ms'}
            if set(params) != allowed:
                raise RoboticsError('invalid_skill_parameters')
            identifier(params['field'])
            sensor = self._sensor(params['sensor_id'])
            threshold = number(params['above'], -1e6, 1e6)
            current = number(sensor['data'].get(params['field']), -1e6, 1e6)
            if current <= threshold:
                raise RoboticsError('sensor_condition_not_met')
            return [{'op': 'move', 'servo': params['servo'], 'angle': params['angle'],
                     'duration_ms': params['duration_ms'], 'expect': {'kind': 'joint'},
                     'condition': {'source_id': params['sensor_id'], 'field': params['field'], 'above': threshold}}]
        if skill == 'object_tidy':
            if set(params) - {'object_id', 'destination', 'objects_id', 'camera_id'} or not {'object_id', 'destination'} <= set(params):
                raise RoboticsError('invalid_skill_parameters')
            caps = state['capabilities']
            if caps['controller'] != 'so101' or caps['feedback_kind'] != 'measured':
                raise RoboticsError('required_capability_missing')
            if not self.policy:
                raise RoboticsError('policy_not_ready')
            object_id = identifier(params['object_id'])
            destination = identifier(params['destination'])
            source_id = identifier(params.get('objects_id', 'workspace'))
            objects = self._observation('objects', source_id)
            item = next((o for o in objects['data']['objects'] if o['id'] == object_id), None)
            if not item or item['confidence'] < .8 or item['location'] == destination:
                raise RoboticsError('object_initial_state_required')
            rgb = self._observation('rgb', params.get('camera_id', 'desk'))
            joint = self._observation('joint', caps['device_id'])
            if joint.get('calibration') != {'firmware_revision': caps['firmware_revision'],
                    'joint_order': caps['joint_order'], 'profile_id': state['profile_id']}:
                raise RoboticsError('calibration_snapshot_mismatch')
            plan = self.policy.plan(f'Move {object_id} to {destination}',
                                    {'rgb': rgb, 'joint': joint, 'objects': objects}, state)
            actions = validate_policy_plan(plan, state)
            for step in actions:
                step['expect'] = {'kind': 'joint'}
            actions[-1]['expect'] = {'kind': 'objects', 'source_id': source_id,
                                     'object_id': object_id, 'destination': destination}
            return actions
        raise RoboticsError('unknown_skill')

    def _validate_steps(self, steps: list[dict], state: dict) -> None:
        previous = list(state['commanded_angles'])
        caps = Capabilities.parse(state['capabilities'])
        channels = [CalibrationChannel.parse(c, len(state['calibration']), bounds=joint_bounds(caps, i)) for i,c in enumerate(state['calibration'])]
        for step in steps:
            if step['op'] == 'move':
                servo = integer(step['servo'], 0, len(channels)-1)
                target = channels[servo].validate_move(step['angle'], previous[servo], step['duration_ms'])
                step['angle'] = target
                previous[servo] = target
            elif step['op'] == 'move_joints':
                for item in step['joints']:
                    index = item['servo']
                    previous[index] = channels[index].validate_move(item['angle'], previous[index], step['duration_ms'])
            elif step['op'] == 'gesture':
                # MCU schedules bounded gestures against the same channel ranges.
                number(step['intensity'], 0, 1)
            else:
                raise RoboticsError('invalid_skill_action')

    def _record(self, kind: str, data: dict) -> None:
        if self.recorder and self.recorder.enabled:
            self.recorder.record(kind, data, timestamp=self.clock())

    def _execute(self) -> None:
        if self._index >= len(self._steps):
            self._finish('succeeded')
            return
        step = self._steps[self._index]
        self._baseline = 0
        expect = step['expect']
        if expect['kind'] in {'sensor', 'rgb', 'objects'}:
            try:
                self._baseline = self.observations.get(expect['kind'], expect['source_id'])['sequence']
            except RoboticsError as error:
                if error.code not in {'observation_missing', 'observation_stale'}:
                    raise
        condition = step.get('condition')
        if condition:
            sensor = self._sensor(condition['source_id'])
            if number(sensor['data'].get(condition['field']), -1e6, 1e6) <= condition['above']:
                self._fail('sensor_condition_not_met')
                return
        self._task['status'] = 'executing'
        self._task['phase'] = 'execute'
        self._task['step'] = self._index
        self._task['history'].append('execute')
        if step['op'] == 'move':
            result = self.controller.move(step['servo'], step['angle'], step['duration_ms'], expected_session=self._task_session)
        elif step['op'] == 'move_joints':
            result = self.controller.move_joints(step['joints'], step['duration_ms'], expected_session=self._task_session)
        else:
            result = self.controller.gesture(step['id'], step['intensity'], expected_session=self._task_session)
        self._command_id = result['command_id']
        recorded = {k: v for k,v in step.items() if k not in {'expect', 'condition'}}
        recorded['command_id'] = result['command_id']
        recorded['source'] = result['source']
        self._record('action', recorded)

    def tick(self) -> dict:
        with self._lock:
            if self._task['status'] in TERMINAL:
                return self.snapshot()
            self.controller.poll()
            state = self.controller.snapshot()
            if state['state'] in {'fault', 'disconnected', 'stopped'}:
                self._fail(state.get('last_error') or 'device_unavailable')
                return self.snapshot()
            if self._task['status'] == 'recovering':
                result = state.get('last_result')
                if result and result['command_id'] == self._command_id and result['status'] == 'done':
                    self._fail('postcondition_not_verified')
                elif self.clock() > self._observation_deadline:
                    self._fail('recovery_timeout')
                return self.snapshot()
            if self.clock() - self._start_time > 60:
                self._fail('task_deadline')
                return self.snapshot()
            if self._task['status'] == 'executing':
                result = state.get('last_result')
                if not result or result['command_id'] != self._command_id:
                    return self.snapshot()
                if result['status'] != 'done':
                    self._fail('action_failed')
                    return self.snapshot()
                self._record('observation', {'robot_state': state, 'observations': self.observations.snapshot(include_frames=True)})
                self._completed_at = result['at']
                self._observation_deadline = self.clock() + 1
                self._task['status'] = 'waiting_observation'
                self._task['phase'] = 'observe'
                self._task['history'].append('observe')
            try:
                verified = self._evaluate(self._steps[self._index], state)
            except RoboticsError as error:
                if error.code not in {'observation_missing', 'observation_stale', 'measurement_required'}:
                    self._fail(error.code)
                    return self.snapshot()
                verified = False
            if verified:
                self._task['history'].append('evaluate')
                self._index += 1
                try:
                    self._execute()
                except RoboticsError as error:
                    self._fail(error.code)
            elif self.clock() > self._observation_deadline:
                self._recover()
            return self.snapshot()

    def _evaluate(self, step: dict, state: dict) -> bool:
        expect = step['expect']
        kind = expect['kind']
        if kind == 'scheduler':
            return True
        if kind == 'joint':
            if state['measured_angles'] is None or state['feedback_age_s'] > 2:
                return False
            targets = step.get('joints', [{'servo': step.get('servo'), 'angle': step.get('angle')}])
            good = all(abs(state['measured_angles'][item['servo']]-item['angle']) <= 3 for item in targets)
            if good:
                self._physical_evidence = state['source'] == 'physical'
            return good
        observation = self._observation(kind, expect['source_id'])
        if observation['sequence'] <= self._baseline or observation['captured_at'] < self._completed_at:
            return False
        data = observation['data']
        if kind == 'sensor':
            good = type(data.get(expect['field'])) is bool and data[expect['field']] is expect['equals']
        elif kind == 'objects':
            good = any(item['id'] == expect['object_id'] and item['location'] == expect['destination']
                       and item['confidence'] >= .8 for item in data['objects'])
        else:
            good = kind == 'rgb'
        if good:
            if kind == 'rgb':
                self._task['verification']['frames_captured'] += 1
                mount = observation.get('calibration') or {}
                mechanical = (state['measured_angles'] is not None and state['feedback_age_s'] <= 2 and
                    abs(state['measured_angles'][step['servo']]-step['angle']) <= 3 and
                    mount.get('camera_mount_servo') == step['servo'] and
                    mount.get('device_id') == state['capabilities']['device_id'] and
                    mount.get('boot_id') == state['capabilities']['boot_id'])
                if mechanical:
                    self._task['verification']['mechanical_verified_frames'] += 1
                complete_measurement = self._task['verification']['mechanical_verified_frames'] == self._task['verification']['frames_captured']
                self._task['verification']['mechanical_motion_verified'] = True if complete_measurement else None
                self._physical_evidence = state['source'] == 'physical' and complete_measurement
            else:
                self._physical_evidence = state['source'] == 'physical'
            self._record('observation', observation)
        return good

    def _recover(self) -> None:
        self._task['history'].append('recover')
        # One bounded button retraction is safe; repeat presses and autonomous
        # rearming are prohibited. Every retry requires a fresh explicit task.
        if self._task['skill'] == 'button_press' and self._index == 0 and not self._task['recovery_attempts']:
            self._task['recovery_attempts'] = 1
            release = self._steps[1]
            try:
                result = self.controller.move(release['servo'], release['angle'], release['duration_ms'], expected_session=self._task_session)
                self._command_id = result['command_id']
                self._task['status'] = 'recovering'
                self._task['phase'] = 'recover'
                self._observation_deadline = self.clock() + release['duration_ms']/1000 + 1
                self._record('action', {'op': 'move', 'servo': release['servo'], 'angle': release['angle'],
                                        'duration_ms': release['duration_ms'], 'recovery': True})
                return
            except RoboticsError:
                pass
        self._fail('postcondition_not_verified')

    def _finish(self, status: str, reason: str | None = None) -> None:
        self._stats[{'succeeded': 'succeeded', 'failed': 'failed', 'stopped': 'interventions'}[status]] += 1
        self._task['status'] = status
        self._task['phase'] = 'evaluate' if status == 'succeeded' else 'recover'
        self._task['reason_code'] = reason
        self._task['duration_s'] = self.clock() - self._start_time
        self._task['physical_success'] = ((True if self._physical_evidence else None) if self._task['source'] == 'physical' else False) if status == 'succeeded' else False
        if self._task['physical_success'] is True:
            self._stats['physical_successes'] += 1
        if self.recorder and self.recorder.enabled:
            self.recorder.finish({'status': status, 'physical_success': self._task['physical_success'],
                                  'reason_code': reason}, timestamp=self.clock())

    def _fail(self, reason: str) -> None:
        try:
            self.controller.stop()
        except RoboticsError:
            pass
        self._record('failure', {'reason_code': reason})
        self._finish('failed', reason)

    def stop(self) -> dict:
        self._cancel_requested = True
        self.controller.stop()
        if not self._lock.acquire(blocking=False):
            return {'status': 'stopped', 'reason_code': 'human_stop', 'physical_success': False}
        try:
            if self._task['status'] not in TERMINAL:
                self._record('intervention', {'op': 'stop'})
                self._finish('stopped', 'human_stop')
            return self.snapshot()
        finally:
            self._lock.release()

    def snapshot(self) -> dict:
        with self._lock:
            result = copy.deepcopy(self._task)
            result['metrics'] = dict(self._stats)
            return result