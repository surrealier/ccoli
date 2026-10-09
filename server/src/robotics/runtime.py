"""Live transport, independent heartbeat and button-driven robotics orchestration."""
from __future__ import annotations

import copy
import json
import hashlib
import logging
from pathlib import Path
import secrets
import threading
import time
from typing import Callable

from .controller import RobotController
from .drivers.atom import AtomDriver
from .drivers.sim import SimDriver
from .episodes import EpisodeRecorder
from .models import MAX_FRAME_BYTES, RoboticsError
from .observations import ObservationStore
from .safety import parse_robot_intent, require_authorized
from .task_runner import TaskRunner


def _status_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate field')
        result[key] = value
    return result


class RobotRuntime:
    def __init__(self, *, clock: Callable[[], float] = time.monotonic,
                 data_directory: str | Path | None = None):
        self.clock = clock
        self._lock = threading.RLock()
        self._generation: str | None = None
        self._physical_connected = False
        self._source = 'atom'
        self._data_directory = Path(data_directory) if data_directory else None
        self.recorder = EpisodeRecorder((self._data_directory or Path('data/robotics'))/'episodes')
        self._physical = self._make_pair(AtomDriver(self._unconnected, connected=lambda:False))
        self.sim_driver = SimDriver(clock=clock)
        self._sim = self._make_pair(self.sim_driver)
        self.sim_driver.attach(self._sim[0].accept)
        self._task_cache = {'status':'idle','physical_success':None}
        self._planning = threading.Event()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_heartbeat = 0.0

    @staticmethod
    def _unconnected(_packet: dict) -> None:
        raise RoboticsError('transport_disconnected')

    def _make_pair(self, driver) -> tuple[RobotController, TaskRunner, ObservationStore]:
        observations = ObservationStore(clock=self.clock)
        path = None  # Assigned after a capability-bound profile selection.
        controller = RobotController(driver, clock=self.clock, calibration_path=path,
                                     observation_store=observations)
        runner = TaskRunner(controller, observations, clock=self.clock, recorder=self.recorder)
        return controller, runner, observations

    def _pair(self):
        with self._lock:
            return self._sim if self._source == 'sim' else self._physical

    @property
    def controller(self) -> RobotController:
        return self._pair()[0]

    @property
    def observations(self) -> ObservationStore:
        return self._pair()[2]

    def bind_atom(self, sender: Callable[[dict], None]) -> str:
        generation = secrets.token_hex(12)
        driver = AtomDriver(sender, connected=lambda:self._generation == generation and self._physical_connected)
        with self._lock:
            self._physical[0].disconnected()
            self._generation = generation
            self._physical_connected = True
            self._physical = self._make_pair(driver)
            if self._source == 'atom':
                self._task_cache = {'status':'idle','physical_success':None}
        return generation

    def unbind_atom(self, generation: str) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._generation = None
            self._physical_connected = False
            self._physical[0].disconnected()
            self._physical[2].clear()
            if self._source == 'atom':
                self._task_cache = {'status':'stopped','reason_code':'disconnected','physical_success':False}

    def accept_atom(self, generation: str, payload: bytes | dict) -> bool:
        with self._lock:
            if generation != self._generation or not self._physical_connected:
                return False
            core = self._physical[0]
        try:
            if isinstance(payload, bytes):
                if not 1 <= len(payload) <= MAX_FRAME_BYTES:
                    return False
                payload = json.loads(payload.decode('utf-8'), object_pairs_hook=_status_object,
                                     parse_constant=lambda _value: (_ for _ in ()).throw(ValueError('invalid number')))
            return core.accept(payload)
        except (UnicodeError, ValueError, TypeError, RoboticsError):
            return False

    def select_source(self, source: str) -> dict:
        if source not in {'atom','sim'}:
            raise RoboticsError('unsupported_source')
        if self._planning.is_set():
            raise RoboticsError('stop_before_configuration')
        self.stop()
        with self._lock:
            self._source = source
            self._task_cache = {'status':'idle','physical_success':None}
            self._last_heartbeat = 0.0
            self.observations.clear()
        return self.snapshot()

    def discover(self) -> dict:
        return self.controller.discover()

    def configure(self, profile_id: str) -> dict:
        with self._lock:
            core = self.controller
            result = core.configure(profile_id)
            if self._data_directory is not None:
                caps = result['capabilities']
                binding = hashlib.sha256((caps['device_id']+'\0'+caps['firmware_revision']).encode()).hexdigest()[:24]
                core.calibration_path = self._data_directory/self._source/binding/(profile_id+'.json')
            return result

    def calibrate(self, channels: list[dict], *, wiring_confirmed: bool = False) -> dict:
        require_authorized(wiring_confirmed)
        return self.controller.calibrate(channels)

    def arm(self, *, confirmed: bool = False) -> dict:
        require_authorized(confirmed)
        return self.controller.arm()

    def move(self, servo: int, angle: float, duration_ms: int = 1000) -> dict:
        return self.controller.move(servo, angle, duration_ms)

    def gesture(self, gesture_id: str, intensity: float = .3) -> dict:
        return self.controller.gesture(gesture_id, intensity)

    def stop(self) -> dict:
        # Do not call runner.snapshot here: a slow policy may own its lock.
        controller, runner, _observations = self._pair()
        try:
            task = runner.stop()
        except RoboticsError:
            task = {'status':'stopped','reason_code':'transport_unavailable','physical_success':False}
        with self._lock:
            self._task_cache = copy.deepcopy(task)
        return {'ok':True,'controller':controller.snapshot(),'task':task}

    def handle_text(self, text: str) -> dict | None:
        intent = parse_robot_intent(text)
        if intent is None:
            return None
        if intent['op'] == 'stop':
            return self.stop()
        return self.gesture(intent['id'], intent['intensity'])

    def start_task(self, skill: str, params: dict, *, confirmed: bool = False) -> dict:
        require_authorized(confirmed)
        with self._lock:
            if self._planning.is_set():
                raise RoboticsError('task_busy')
            pair = self._pair()
            self._planning.set()
            self._task_cache = {'status':'planning','skill':skill,'physical_success':None}
        try:
            result = pair[1].start(skill, params, authorized=True)
            with self._lock:
                if pair is self._pair():
                    self._task_cache = copy.deepcopy(result)
            return result
        except RoboticsError as error:
            with self._lock:
                if pair is self._pair():
                    self._task_cache = {'status':'failed','skill':skill,'reason_code':error.code,'physical_success':False}
            raise
        finally:
            self._planning.clear()

    def simulated_observation(self, kind: str, source_id: str, data: dict, sequence: int) -> dict:
        if self._source != 'sim':
            raise RoboticsError('simulator_required')
        return self.observations.update(kind, source_id, data, sequence=sequence, provenance='simulated')

    def inject_fault(self, fault: str | None) -> None:
        if self._source != 'sim':
            raise RoboticsError('simulator_required')
        self.sim_driver.inject_fault(fault)

    def set_recording(self, enabled: bool) -> dict:
        if type(enabled) is not bool:
            raise RoboticsError('invalid_recording_setting')
        self.recorder.set_enabled(enabled)
        return {'enabled':self.recorder.enabled,'local_only':True}

    def tick(self) -> None:
        pair = self._pair()
        controller, runner, _observations = pair
        if self._source == 'sim':
            self.sim_driver.tick()
        controller.poll()
        now = self.clock()
        if now - self._last_heartbeat >= .4:
            controller.heartbeat()
            self._last_heartbeat = now
        if not self._planning.is_set():
            result = runner.tick()
            with self._lock:
                if pair is self._pair():
                    self._task_cache = copy.deepcopy(result)

    def snapshot(self) -> dict:
        with self._lock:
            pair = self._pair()
            result = {'selected_source':self._source,'physical_connected':self._physical_connected,
                      'controller':pair[0].snapshot(),'task':copy.deepcopy(self._task_cache),
                      'observations':pair[2].snapshot(),'recording_enabled':self.recorder.enabled}
        return result

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        def run():
            while not self._stop_event.wait(.1):
                try:
                    self.tick()
                except Exception as error:
                    # A recorder/storage fault must never kill the safety loop.
                    try:
                        self.controller.stop()
                    except RoboticsError:
                        pass
                    self.recorder.abort('runtime_failed')
                    with self._lock:
                        self._task_cache = {'status':'failed','reason_code':'runtime_failed','physical_success':False}
                    logging.getLogger(__name__).error("Robot runtime failed (%s)", type(error).__name__)
        self._thread = threading.Thread(target=run, name='robot-heartbeat', daemon=True)
        self._thread.start()

    def close(self) -> None:
        self.stop()
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1)
