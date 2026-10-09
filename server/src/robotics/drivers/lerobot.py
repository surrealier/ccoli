"""Actual LeRobot 0.6.1 SO-101 driver; SDK imports are opt-in and lazy."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
import copy
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
from typing import Callable

from ..models import Capabilities, CalibrationChannel, RoboticsError, identifier, integer, joint_bounds, number
from ..vla_adapter import SO101_JOINTS, SO101_UNITS


def sdk_worker_launch(python_executable: str,script_path: str,*,port: str,robot_id: str,
                      work_dir: str,platform: str | None=None) -> list[str]:
    """Build native isolated-SDK argv. Windows COM is not a Docker Linux device."""
    import re
    platform=platform or sys.platform
    if not isinstance(port,str) or not (
            re.fullmatch(r'COM[1-9][0-9]{0,3}',port,re.I) if platform=='win32'
            else platform=='linux' and re.fullmatch(r'/dev/(?:tty(?:USB|ACM)[0-9]+|serial/by-id/[A-Za-z0-9_.:-]+)',port)):
        raise RoboticsError('unsupported_sdk_port')
    interpreter=Path(python_executable).resolve(); script=Path(script_path).resolve()
    if not interpreter.is_file() or not script.is_file():
        raise RoboticsError('sdk_environment_unavailable')
    return [str(interpreter),'-u',str(script),'serve-sdk','--port',port,'--robot-id',identifier(robot_id),
            '--work-root',str(Path(work_dir).resolve())]


class SubprocessRobotTransport:
    """Voice-runtime transport to opt-in SDK process; import never requires Torch."""
    source='physical'

    def __init__(self,command: list[str],*,startup_timeout_s: float=30,observation_store=None):
        if (not isinstance(command,list) or not command or
                any(not isinstance(value,str) or not value or '\x00' in value for value in command)):
            raise RoboticsError('sdk_worker_command_invalid')
        self._sink=lambda value:None
        self._ready=threading.Event(); self._closed=threading.Event()
        self._writer_lock=threading.Lock()
        self._startup_ok=False
        self.observation_store=observation_store
        self._device_id=None; self._joint_sequence=0
        self.process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL,shell=False)
        self._reader=threading.Thread(target=self._read,daemon=True,name='so101-stdio')
        self._reader.start()
        if not self._ready.wait(number(startup_timeout_s,.01,120)) or not self._startup_ok:
            self.close()
            raise RoboticsError('sdk_worker_unavailable')

    def bind(self,sink: Callable[[dict],None]) -> None:
        self._sink=sink

    def _read(self) -> None:
        try:
            while not self._closed.is_set():
                line=self.process.stdout.readline(65537)
                if not line or len(line)>65536 or not line.endswith(b'\n'):
                    raise ValueError('sdk worker disconnected')
                value=json.loads(line)
                if not isinstance(value,dict):
                    raise ValueError('invalid SDK protocol')
                if not self._ready.is_set():
                    self._startup_ok=value.get('ready') is True and value.get('sdk')=='lerobot-0.6.1'
                    self._ready.set()
                    if not self._startup_ok:
                        return
                else:
                    caps=value.get('capabilities')
                    if isinstance(caps,dict) and caps.get('controller')=='so101':
                        self._device_id=identifier(caps.get('device_id'))
                    angles=value.get('measured_angles')
                    if self.observation_store is not None and self._device_id and isinstance(angles,list):
                        if len(angles)!=6:
                            raise RoboticsError('invalid_joint_dimension')
                        angles=[number(angle,*((-180,180) if index<5 else (0,100))) for index,angle in enumerate(angles)]
                        if value.get('feedback_kind')!='measured':
                            raise RoboticsError('measurement_required')
                        self.observation_store.register_source('joint',self._device_id,
                            driver_id='so101-sdk-'+hashlib.sha256(self._device_id.encode()).hexdigest()[:16],
                            provenance='measured')
                        self._joint_sequence+=1
                        self.observation_store.update('joint',self._device_id,{'angles':angles},
                            sequence=self._joint_sequence,provenance='measured',
                            calibration={'firmware_revision':'lerobot-0.6.1','joint_order':list(SO101_JOINTS),'profile_id':'so101'})
                    self._sink(value)
        except Exception:
            self._ready.set()
            self._sink({'v':1,'status':'ERROR','error':'sdk_transport_disconnected','armed':False})

    def send(self,payload: dict) -> None:
        wire=(json.dumps(payload,allow_nan=False,separators=(',',':'))+'\n').encode()
        if len(wire)>65536:
            raise RoboticsError('sdk_command_too_large')
        with self._writer_lock:
            if self._closed.is_set() or self.process.poll() is not None:
                raise RoboticsError('transport_disconnected')
            complete=threading.Event(); failed=[]
            def write():
                try:
                    self.process.stdin.write(wire); self.process.stdin.flush()
                except Exception:
                    failed.append(True)
                finally:
                    complete.set()
            thread=threading.Thread(target=write,daemon=True,name='so101-stdio-write'); thread.start()
            if not complete.wait(2) or failed:
                self.close()
                raise RoboticsError('sdk_transport_write_failed')

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        # EOF lets serve-sdk run its torque-off finalizer before escalating process shutdown.
        if self.process.stdin:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill(); self.process.wait(timeout=2)
        if self.process.stdout:
            self.process.stdout.close()
        if self.observation_store is not None and self._device_id:
            self.observation_store.unregister_source('joint',self._device_id)


def discover_ports() -> list[dict]:
    """Enumerate candidates only; finding a USB port does not prove an arm exists."""
    from serial.tools import list_ports
    return [{'port': item.device, 'description': item.description, 'vid': item.vid, 'pid': item.pid,
             'verified': False} for item in list_ports.comports()]


def _sdk_robot(*, port: str, robot_id: str, calibration_dir: Path):
    from importlib.metadata import version
    if version('lerobot') != '0.6.1':
        raise RoboticsError('sdk_version_mismatch')
    from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig
    config = SO101FollowerConfig(port=port, id=robot_id, calibration_dir=calibration_dir,
                                cameras={}, use_degrees=True, max_relative_target=3.0,
                                disable_torque_on_disconnect=True)
    return SO101Follower(config)


def read_teleoperator_target(leader) -> list[dict]:
    """Read human leader input; callers use the same calibrated controller move path."""
    if not leader.is_connected or not leader.is_calibrated:
        raise RoboticsError('teleoperator_calibration_required')
    action=leader.get_action()
    if not isinstance(action,dict) or set(action)!={f'{name}.pos' for name in SO101_JOINTS}:
        raise RoboticsError('teleoperator_joint_order_mismatch')
    return [{'servo':index,'angle':number(action[f'{name}.pos'],*((-180,180) if index<5 else (0,100)))}
            for index,name in enumerate(SO101_JOINTS)]


class SO101Teleoperator:
    """Actual SDK leader lifecycle; reading targets never sends follower motion."""
    def __init__(self, port: str, robot_id: str, *, calibration_dir: str | Path):
        from importlib.metadata import version
        if version('lerobot')!='0.6.1':
            raise RoboticsError('sdk_version_mismatch')
        from lerobot.teleoperators.so_leader import SO101Leader,SO101LeaderConfig
        self.leader=SO101Leader(SO101LeaderConfig(port=port,id=identifier(robot_id),
                                                calibration_dir=Path(calibration_dir),use_degrees=True))

    def connect(self) -> None:
        self.leader.connect(calibrate=False)
        self.leader.disable_torque()

    def calibrate(self) -> None:
        self.leader.calibrate()
        self.leader.disable_torque()

    def read_target(self) -> list[dict]:
        return read_teleoperator_target(self.leader)

    def close(self) -> None:
        if self.leader.is_connected:
            self.leader.disconnect()


class SO101Driver:
    source = 'physical'

    def __init__(self, port: str, robot_id: str, *, calibration_dir: str | Path,
                 robot_factory: Callable = _sdk_robot, clock: Callable[[], float] = time.monotonic,
                 sink: Callable[[dict], None] | None = None, observation_store=None):
        if not isinstance(port, str) or not port or len(port) > 256:
            raise RoboticsError('invalid_serial_port')
        self.port, self.robot_id = port, identifier(robot_id)
        self.calibration_dir = Path(calibration_dir)
        self.robot_factory, self.clock = robot_factory, clock
        self._sink = sink or (lambda value: None)
        self.robot = None
        self.boot_id = secrets.token_hex(12)
        self.armed = False
        self.channels: list[CalibrationChannel] = []
        self.sdk_calibration_id = ''
        self._io_lock = threading.RLock()
        self._state_lock = threading.RLock()
        self._halt = threading.Event()
        self._closed = threading.Event()
        self._watchdog_thread = None
        self._motion = None
        self._lease_until = 0.0
        self._session = ''
        self._seq = 0
        self._results: dict[str, dict] = {}
        self.observation_store=observation_store
        self._joint_sequence=0
        self._stop_epoch=0
        self._active_command: dict | None=None

    def bind(self, sink: Callable[[dict], None]) -> None:
        self._sink = sink

    def _calibration_hash(self) -> str:
        calibration = getattr(self.robot, 'calibration', {})
        if not calibration:
            return ''
        values = {key: asdict(item) if is_dataclass(item) else item for key,item in calibration.items()}
        return hashlib.sha256(json.dumps(values, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    def capabilities(self) -> dict:
        return {'device_id': self.robot_id, 'boot_id': self.boot_id, 'controller': 'so101',
                'servo_count': 6, 'display': 'none', 'feedback_kind': 'measured', 'sensors': [],
                'firmware_revision': 'lerobot-0.6.1', 'joint_order': list(SO101_JOINTS),
                'units': 'mixed', 'joint_units': list(SO101_UNITS)}

    def connect(self) -> dict:
        with self._io_lock:
            if self.robot is not None and self.robot.is_connected:
                return self.capabilities()
            self.robot = self.robot_factory(port=self.port, robot_id=self.robot_id,
                                            calibration_dir=self.calibration_dir)
            # SOFollower.connect() calls configure(), whose torque context re-enables motors.
            # Use its official bus lifecycle without configure; discovery never enables torque.
            self.robot.bus.connect()
            self.robot.bus.disable_torque()
            self.sdk_calibration_id = self._calibration_hash() if self.robot.is_calibrated else ''
            self.boot_id = secrets.token_hex(12)
        self._closed.clear()
        self._watchdog_thread = threading.Thread(target=self._watchdog, daemon=True, name='so101-deadman')
        self._watchdog_thread.start()
        return self.capabilities()

    def calibrate_sdk(self) -> dict:
        """Explicit interactive SDK calibration; the human manually moves the disabled arm."""
        self.stop()
        with self._io_lock:
            if self.robot is None or not self.robot.is_connected:
                raise RoboticsError('transport_disconnected')
            self.robot.calibrate()
            self.robot.bus.disable_torque()
            if not self.robot.is_calibrated:
                raise RoboticsError('sdk_calibration_required')
            self.sdk_calibration_id = self._calibration_hash()
        return {'sdk_calibration_id': self.sdk_calibration_id, 'armed': False}

    def set_limits(self, channels: list[dict]) -> None:
        with self._state_lock:
            if self.armed or (self._motion is not None and self._motion.is_alive()):
                raise RoboticsError('stop_before_calibration')
            if self.robot is None or not self.robot.is_calibrated or not self.sdk_calibration_id:
                raise RoboticsError('sdk_calibration_required')
            epoch=self._stop_epoch
        if not isinstance(channels, list) or len(channels) != 6:
            raise RoboticsError('invalid_calibration_count')
        caps = Capabilities.parse(self.capabilities())
        parsed = [CalibrationChannel.parse(value,6,bounds=joint_bounds(caps,index)) for index,value in enumerate(channels)]
        if [channel.servo for channel in parsed] != list(range(6)):
            raise RoboticsError('invalid_joint_order')
        with self._state_lock:
            if epoch!=self._stop_epoch:
                raise RoboticsError('calibration_cancelled')
            self.channels = parsed

    def read_state(self) -> dict:
        with self._io_lock:
            if self.robot is None or not self.robot.is_connected:
                raise RoboticsError('transport_disconnected')
            observation = self.robot.get_observation()
        angles = [observation[f'{name}.pos'] for name in SO101_JOINTS]
        caps = Capabilities.parse(self.capabilities())
        angles = [number(angle,*joint_bounds(caps,index),'measurement_out_of_range') for index,angle in enumerate(angles)]
        if self.observation_store is not None:
            with self._state_lock:
                self.observation_store.register_source('joint',self.robot_id,
                    driver_id='so101-sdk-'+hashlib.sha256(self.robot_id.encode()).hexdigest()[:16],provenance='measured')
                self._joint_sequence+=1
                self.observation_store.update('joint',self.robot_id,{'angles':angles},sequence=self._joint_sequence,
                    provenance='measured',calibration={'firmware_revision':'lerobot-0.6.1',
                    'joint_order':list(SO101_JOINTS),'profile_id':'so101'})
        return {'armed': self.armed, 'measured_angles': angles, 'commanded_angles': list(angles),
                'sdk_calibration_id': self.sdk_calibration_id, 'feedback_kind': 'measured'}

    def arm(self, lease_ms: int = 2000) -> None:
        lease=integer(lease_ms,1,2000)/1000
        with self._state_lock:
            if (len(self.channels)!=6 or not self.sdk_calibration_id or self.robot is None
                    or not self.robot.is_calibrated or self._closed.is_set()):
                raise RoboticsError('calibration_required')
            epoch=self._stop_epoch
        def check_cancelled() -> None:
            if epoch!=self._stop_epoch or len(self.channels)!=6 or self._closed.is_set():
                raise RoboticsError('arm_cancelled')
        with self._io_lock:
            with self._state_lock:
                check_cancelled()
            angles=self.read_state()['measured_angles']
            for channel,angle in zip(self.channels,angles):
                number(angle,channel.min_angle,channel.max_angle,'measurement_outside_calibration')
            current={f'{name}.pos':angle for name,angle in zip(SO101_JOINTS,angles)}
            # Write current measured goals with torque disabled before enabling position control.
            self.robot.send_action({f'{name}.pos': current[f'{name}.pos'] for name in SO101_JOINTS})
            with self._state_lock:
                check_cancelled()
            self.robot.configure()
            # STOP publishes cancellation before waiting for IO. Final enable/commit is atomic
            # with that publication, so a late arm can never erase a completed STOP.
            with self._state_lock:
                check_cancelled()
                self.robot.bus.enable_torque()
                self._halt.clear()
                self.armed = True
                self._lease_until = self.clock()+lease

    def stop(self, mode: str = 'detach') -> None:
        if mode not in {'detach','hold'}:
            raise RoboticsError('invalid_stop_mode')
        with self._state_lock:
            self._stop_epoch+=1
            self._halt.set()
            self.armed = False
            self._lease_until = 0
            self.channels = []
            self._session=''
            self._seq=0
            self._results.clear()
            self._active_command=None
        if self.robot is not None and self.robot.is_connected:
            with self._io_lock:
                if mode == 'hold' and self.sdk_calibration_id:
                    angles=self.read_state()['measured_angles']
                    current={f'{name}.pos':angle for name,angle in zip(SO101_JOINTS,angles)}
                    self.robot.send_action({f'{name}.pos': current[f'{name}.pos'] for name in SO101_JOINTS})
                else:
                    self.robot.bus.disable_torque()

    def human_takeover(self) -> dict:
        self.stop('detach')
        return self.read_state()

    def close(self) -> None:
        self._closed.set()
        try:
            self.stop()
        finally:
            try:
                with self._io_lock:
                    if self.robot is not None and self.robot.is_connected:
                        self.robot.disconnect()
            finally:
                if self.observation_store is not None:
                    self.observation_store.unregister_source('joint',self.robot_id)
                if self._watchdog_thread:
                    self._watchdog_thread.join(timeout=.3)

    def _watchdog(self) -> None:
        while not self._closed.wait(.025):
            if self.armed and self.clock() >= self._lease_until:
                self._expire_lease()

    def _expire_lease(self) -> None:
        with self._state_lock:
            if not self.armed or self.clock()<self._lease_until:
                return
            packet=copy.deepcopy(self._active_command)
        status,error='STOPPED','lease_expired'
        try:
            self.stop('detach')
        except Exception:
            # Cancellation is latched but torque IO is unverified: do not report success.
            status,error='ERROR','sdk_watchdog_io_failure'
        if packet is not None:
            self._status(packet,status,error)

    def _status(self, payload: dict, status: str, error: str | None = None) -> None:
        packet = {key:payload.get(key) for key in ('op','command_id','session_id','seq')}
        packet.update(v=1,status=status,boot_id=self.boot_id,armed=self.armed,feedback_kind='measured',
                      sdk_calibration_id=self.sdk_calibration_id)
        try:
            packet.update(self.read_state())
        except Exception:
            if status not in {'ERROR','STOPPED'}:
                status = packet['status'] = 'ERROR'
                error = 'measurement_unavailable'
        if payload.get('op')=='discover':
            packet['capabilities']=self.capabilities()
        if error:
            packet['error']=error
        command_id=payload.get('command_id')
        if isinstance(command_id,str):
            self._results[command_id]=copy.deepcopy(packet)
            while len(self._results)>64:
                self._results.pop(next(iter(self._results)))
        self._sink(packet)

    def send(self, payload: dict) -> None:
        """The same framed controller contract as Atom/companion, with native SDK IO."""
        try:
            if not isinstance(payload,dict) or payload.get('cmd')!='ROBOT_CONTROL':
                raise RoboticsError('invalid_command')
            integer(payload.get('v'),1,1)
            for field in ('command_id','session_id'):
                identifier(payload.get(field))
            integer(payload.get('seq'),1,0xffffffff)
            integer(payload.get('valid_for_ms'),1,2000)
            op=payload.get('op')
            if op=='stop':
                self.stop(payload.get('mode','detach'))
                self._session=''; self._results.clear()
                self._status(payload,'STOPPED'); return
            if op=='discover':
                self.connect(); self.stop()
                self._session=payload['session_id']; self._seq=payload['seq']
                self._results.clear(); self._status(payload,'DONE'); return
            if payload.get('boot_id')!=self.boot_id or payload['session_id']!=self._session:
                raise RoboticsError('session_mismatch')
            cached=self._results.get(payload['command_id'])
            if cached:
                self._sink(copy.deepcopy(cached)); return
            if payload['seq']<=self._seq:
                raise RoboticsError('stale_sequence')
            self._seq=payload['seq']
            if op=='calibrate':
                self.set_limits(payload.get('channels')); self._status(payload,'DONE')
            elif op=='arm':
                self.arm(payload.get('lease_ms'))
                self._active_command=copy.deepcopy(payload)
                self._status(payload,'DONE')
            elif op=='heartbeat':
                with self._state_lock:
                    if not self.armed:
                        raise RoboticsError('device_not_armed')
                    self._lease_until=self.clock()+integer(payload.get('lease_ms'),1,2000)/1000
                    self._active_command=copy.deepcopy(payload)
                self._status(payload,'DONE')
            elif op=='state':
                self._status(payload,'DONE')
            elif op=='move':
                self._start_move(payload)
            else:
                raise RoboticsError('unsupported_sdk_action')
        except RoboticsError as exc:
            self._status(payload if isinstance(payload,dict) else {},'ERROR',exc.code)
        except Exception:
            try:
                self.stop()
            except Exception:
                pass  # State was already disarmed; report the original unavailable transport.
            self._status(payload if isinstance(payload,dict) else {},'ERROR','sdk_io_failure')

    def _start_move(self, payload: dict) -> None:
        with self._state_lock:
            if not self.armed or self.clock()>=self._lease_until:
                raise RoboticsError('device_not_armed')
            if self._motion is not None and self._motion.is_alive():
                raise RoboticsError('device_busy')
            epoch=self._stop_epoch
            channels=list(self.channels)
        duration=integer(payload.get('duration_ms'),1,5000)
        measured=self.read_state()['measured_angles']
        joints=payload.get('joints')
        if joints is None:
            joints=[{'servo':payload.get('servo'),'angle':payload.get('angle')}]
        if not isinstance(joints,list) or not 1<=len(joints)<=6:
            raise RoboticsError('invalid_joint_dimension')
        targets=list(measured); seen=set()
        for joint in joints:
            if not isinstance(joint,dict) or set(joint)!={'servo','angle'}:
                raise RoboticsError('invalid_joint_schema')
            servo=integer(joint['servo'],0,5)
            if servo in seen:
                raise RoboticsError('invalid_joint_order')
            seen.add(servo)
            targets[servo]=channels[servo].validate_move(joint['angle'],measured[servo],duration)
        with self._state_lock:
            if epoch!=self._stop_epoch or not self.armed:
                raise RoboticsError('motion_cancelled')
            self._lease_until=self.clock()+integer(payload.get('lease_ms'),1,2000)/1000
            self._active_command=copy.deepcopy(payload)
            self._motion=threading.Thread(target=self._execute_move,args=(copy.deepcopy(payload),measured,targets,duration,epoch),daemon=True,name='so101-move')
        self._status(payload,'RUNNING')
        self._motion.start()

    def _execute_move(self, payload: dict, start: list, targets: list, duration_ms: int, epoch: int) -> None:
        try:
            started=self.clock()
            while not self._halt.is_set() and self.armed:
                if self.clock()>=self._lease_until:
                    self._expire_lease()
                    return
                progress=min(1.0,(self.clock()-started)/(duration_ms/1000))
                desired={f'{name}.pos':old+(target-old)*progress for name,old,target in zip(SO101_JOINTS,start,targets)}
                with self._io_lock:
                    with self._state_lock:
                        if (self._halt.is_set() or not self.armed or epoch!=self._stop_epoch
                                or self.clock()>=self._lease_until):
                            return
                        actual=self.robot.send_action(desired)
                if progress>=1:
                    if any(abs(float(actual[key])-desired[key])>.01 for key in desired):
                        raise RoboticsError('sdk_target_clipped')
                    self._status(payload,'DONE'); return
                self._halt.wait(.05)
        except Exception:
            try:
                self.stop()
            except Exception:
                pass
            self._status(payload,'ERROR','sdk_motion_failed')
