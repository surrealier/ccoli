"""Dependency-free boundary to the isolated learned LeRobot policy worker."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import copy
import json
import math
import re
import queue
import subprocess
import threading
import time
from typing import Any, Callable

from .models import RoboticsError, identifier, integer, number

SO101_JOINTS = ('shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex', 'wrist_roll', 'gripper')
SO101_UNITS = ('degrees',) * 5 + ('percent',)
BASE_CHECKPOINT = 'lerobot/smolvla_base'
BASE_REVISION = '5e8d12a6e2975b0e5e5fce7c8caf47c371d257b6'
BACKBONE = 'HuggingFaceTB/SmolVLM2-500M-Video-Instruct'
BACKBONE_REVISION = '7b375e1b73b11138ff12fe22c8f2822d8fe03467'


class SubprocessPolicyWorker:
    """Persistent local stdio worker, with bounded responses and no private payload logs."""
    def __init__(self, command: list[str], *, revision: str, startup_timeout_s: float=120,
                 request_timeout_s: float=15, max_message_bytes: int=12_000_000):
        if (not isinstance(command,list) or not command or
                any(not isinstance(item,str) or not item or '\x00' in item for item in command)):
            raise RoboticsError('policy_worker_command_invalid')
        if not re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}',revision):
            raise RoboticsError('policy_revision_invalid')
        self.revision=revision
        self.timeout=number(request_timeout_s,.01,120)
        self.max_bytes=integer(max_message_bytes,1024,12_000_000)
        self.closed=False
        self._lock=threading.Lock()
        self._messages=queue.Queue(maxsize=2)
        self.process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL,shell=False)
        self._reader=threading.Thread(target=self._read,daemon=True,name='vla-stdio-reader')
        self._reader.start()
        try:
            ready=self._receive(number(startup_timeout_s,.01,600))
            if ready.get('ready') is not True or ready.get('revision')!=revision:
                raise RoboticsError('policy_worker_revision_mismatch')
        except Exception:
            self.close()
            raise

    def _read(self) -> None:
        try:
            while not self.closed:
                line=self.process.stdout.readline(self.max_bytes+1)
                if not line or len(line)>self.max_bytes or not line.endswith(b'\n'):
                    raise ValueError('invalid worker response')
                value=json.loads(line)
                if not isinstance(value,dict):
                    raise ValueError('invalid worker response')
                self._messages.put(value,timeout=1)
        except Exception:
            try:
                self._messages.put({'error':'worker_disconnected'},timeout=.1)
            except queue.Full:
                pass

    def _receive(self, timeout: float) -> dict:
        try:
            value=self._messages.get(timeout=timeout)
        except queue.Empty:
            raise RoboticsError('policy_worker_timeout') from None
        if value.get('error'):
            raise RoboticsError('policy_worker_failed')
        return value

    def __call__(self, request: dict) -> dict:
        payload=(json.dumps(request,allow_nan=False,separators=(',',':'))+'\n').encode()
        if len(payload)>self.max_bytes:
            raise RoboticsError('policy_worker_request_too_large')
        with self._lock:
            if self.closed or self.process.poll() is not None:
                raise RoboticsError('policy_worker_closed')
            try:
                # The reader is continuously draining stdout. Input write is bounded by the
                # same process deadline; terminate a stuck reader rather than retain frames.
                sent=threading.Event()
                failed=[]
                def write() -> None:
                    try:
                        self.process.stdin.write(payload)
                        self.process.stdin.flush()
                    except Exception:
                        failed.append(True)
                    finally:
                        sent.set()
                writer=threading.Thread(target=write,daemon=True,name='vla-stdio-writer')
                started=time.monotonic(); writer.start()
                if not sent.wait(self.timeout):
                    raise RoboticsError('policy_worker_timeout')
                if failed:
                    raise RoboticsError('policy_worker_failed')
                result=self._receive(max(.001,self.timeout-(time.monotonic()-started)))
                if result.get('revision')!=self.revision:
                    raise RoboticsError('policy_worker_revision_mismatch')
                return result
            except Exception:
                self.close()
                raise

    def close(self) -> None:
        if self.closed:
            return
        self.closed=True
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill(); self.process.wait(timeout=2)
        for stream in (self.process.stdin,self.process.stdout):
            if stream:
                stream.close()

    def __enter__(self):
        return self

    def __exit__(self,*args) -> None:
        self.close()


@dataclass(frozen=True)
class PolicyManifest:
    schema_version: int
    checkpoint: str
    revision: str
    joint_order: tuple[str, ...]
    joint_units: tuple[str, ...]
    units: str
    profile_id: str
    firmware_revision: str
    calibration_id: str
    camera_features: dict[str, str]
    action_feature_names: tuple[str, ...]
    state_feature_names: tuple[str, ...]
    hardware_validated: bool

    @classmethod
    def parse(cls, value: Any) -> 'PolicyManifest':
        fields = set(cls.__dataclass_fields__)
        if not isinstance(value, dict) or set(value) != fields or type(value.get('schema_version')) is not int or value['schema_version'] != 1:
            raise RoboticsError('policy_manifest_schema')
        checkpoint = value['checkpoint']
        if not isinstance(checkpoint, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+|local:[A-Za-z0-9_./-]+', checkpoint):
            raise RoboticsError('policy_checkpoint_invalid')
        if '..' in checkpoint or not re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}', str(value['revision'])):
            raise RoboticsError('policy_revision_invalid')
        order = value['joint_order']
        units = value['joint_units']
        if order != list(SO101_JOINTS) or units != list(SO101_UNITS) or value['units'] != 'mixed':
            raise RoboticsError('policy_joint_contract_mismatch')
        feature_names = [f'{name}.pos' for name in SO101_JOINTS]
        if value['action_feature_names'] != feature_names or value['state_feature_names'] != feature_names:
            raise RoboticsError('policy_feature_names_mismatch')
        if value['profile_id'] != 'so101' or type(value['hardware_validated']) is not bool:
            raise RoboticsError('policy_deployment_invalid')
        identifier(value['firmware_revision'])
        calibration_id = value['calibration_id']
        if not isinstance(calibration_id, str) or not re.fullmatch(r'[a-f0-9]{64}', calibration_id):
            raise RoboticsError('policy_calibration_invalid')
        cameras = value['camera_features']
        if not isinstance(cameras, dict) or not 1 <= len(cameras) <= 4 or len(set(cameras.values())) != len(cameras):
            raise RoboticsError('policy_camera_features_invalid')
        for feature, source in cameras.items():
            if not isinstance(feature, str) or not re.fullmatch(r'observation\.images\.[A-Za-z0-9_]{1,48}', feature):
                raise RoboticsError('policy_camera_features_invalid')
            identifier(source)
        return cls(1, checkpoint, value['revision'], tuple(order), tuple(units), 'mixed',
                   'so101', value['firmware_revision'], calibration_id, dict(cameras),
                   tuple(feature_names), tuple(feature_names), value['hardware_validated'])

    def public(self) -> dict:
        data = asdict(self)
        for key in ('joint_order', 'joint_units', 'state_feature_names', 'action_feature_names'):
            data[key] = list(data[key])
        return data


def named_action_plan(action: Any, manifest: PolicyManifest, *, duration_ms: int) -> dict:
    """Only named, SDK-postprocessed six-joint actions can reach robot planning."""
    if not isinstance(action, dict) or set(action) != set(manifest.action_feature_names):
        raise RoboticsError('policy_action_feature_mismatch')
    joints = []
    for index, name in enumerate(manifest.action_feature_names):
        low, high = (-180, 180) if index < 5 else (0, 100)
        joints.append({'servo': index, 'angle': number(action[name], low, high, 'policy_action_out_of_range')})
    return {'actions': [{'joints': joints, 'duration_ms': integer(duration_ms, 1, 5000)}],
            'revision': manifest.revision, 'joint_order': list(manifest.joint_order),
            'units': manifest.units, 'joint_units': list(manifest.joint_units),
            'sdk_calibration_id': manifest.calibration_id}


class SmolVLAAdapter:
    """Use only a hardware-validated checkpoint bound to the current measured arm."""
    def __init__(self, manifest: dict, worker: Callable[[dict], dict], *,
                 observation_provider: Callable[[str], dict] | None = None,
                 clock: Callable[[], float] = time.monotonic, max_observation_age_s: float = 2):
        self.manifest = PolicyManifest.parse(manifest)
        self.worker, self.observation_provider, self.clock = worker, observation_provider, clock
        self.max_observation_age_s = number(max_observation_age_s, .01, 30)

    def plan(self, instruction: str, observation: dict, robot_state: dict) -> dict:
        if not isinstance(instruction, str) or not instruction.strip() or len(instruction) > 2000:
            raise RoboticsError('policy_instruction_invalid')
        if not self.manifest.hardware_validated:
            raise RoboticsError('policy_hardware_validation_required')
        caps = robot_state.get('capabilities') or {}
        if not robot_state.get('armed') or not robot_state.get('calibrated'):
            raise RoboticsError('device_not_armed')
        expected = self.manifest
        if (caps.get('controller') != 'so101' or caps.get('feedback_kind') != 'measured'
                or caps.get('joint_order') != list(expected.joint_order)
                or caps.get('joint_units') != list(expected.joint_units) or caps.get('units') != 'mixed'
                or caps.get('firmware_revision') != expected.firmware_revision
                or robot_state.get('profile_id') != expected.profile_id
                or robot_state.get('sdk_calibration_id') != expected.calibration_id):
            raise RoboticsError('policy_calibration_or_capability_mismatch')
        joint = observation.get('joint', {})
        binding = {'firmware_revision': expected.firmware_revision,
                   'joint_order': list(expected.joint_order), 'profile_id': expected.profile_id}
        if (joint.get('provenance')!='measured' or not joint.get('driver_id')
                or joint.get('calibration')!=binding):
            raise RoboticsError('policy_measured_state_required')
        identifier(joint['driver_id'])
        state = joint.get('data', {}).get('angles')
        if not isinstance(state, list) or len(state) != 6:
            raise RoboticsError('invalid_joint_dimension')
        for index, angle in enumerate(state):
            number(angle, *((-180,180) if index < 5 else (0,100)))
        frames = {}
        ages = [number(joint.get('age_s'), 0, self.max_observation_age_s, 'observation_stale')]
        primary = observation.get('rgb', {})
        for feature, source in expected.camera_features.items():
            frame = primary if primary.get('source_id') == source else (
                self.observation_provider(source) if self.observation_provider else None)
            if not isinstance(frame, dict) or frame.get('provenance') != 'measured' or not frame.get('driver_id'):
                raise RoboticsError('policy_camera_missing')
            identifier(frame['driver_id'])
            if frame.get('source_id')!=source:
                raise RoboticsError('policy_camera_source_mismatch')
            ages.append(number(frame.get('age_s'), 0, self.max_observation_age_s, 'observation_stale'))
            frames[feature] = copy.deepcopy(frame['data'])
        started = self.clock()
        result = self.worker({'op': 'infer', 'manifest': expected.public(), 'instruction': instruction,
                              'state': state, 'frames': frames})
        if max(ages) + self.clock() - started > self.max_observation_age_s:
            raise RoboticsError('observation_stale')
        if not isinstance(result, dict) or result.get('revision') != expected.revision:
            raise RoboticsError('policy_worker_revision_mismatch')
        duration = 1000
        action = result.get('action')
        plan = named_action_plan(action, expected, duration_ms=duration)
        # Select a duration that preserves every calibrated speed limit; reject instead of clipping.
        channels = robot_state.get('calibration', [])
        if len(channels) != 6:
            raise RoboticsError('calibration_required')
        for index, item in enumerate(plan['actions'][0]['joints']):
            channel = channels[index]
            number(item['angle'], channel['min_angle'], channel['max_angle'], 'angle_out_of_range')
            speed = number(channel['max_speed_dps'], 1, 90)
            duration = max(duration, math.ceil(abs(item['angle']-state[index])/speed*1000))
        plan['actions'][0]['duration_ms'] = integer(duration, 1, 5000, 'policy_motion_too_far')
        return plan
