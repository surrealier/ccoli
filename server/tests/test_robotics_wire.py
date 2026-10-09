"""Real Python state machine against the compiled MCU controller, no motors."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import subprocess
import threading
import time
import pytest
from src.robotics.controller import RobotController
from src.robotics.models import RoboticsError

ROOT = Path(__file__).resolve().parents[2]

@pytest.fixture(scope='module')
def native_binary(tmp_path_factory):
    target = tmp_path_factory.mktemp('native-robot')/'companion_simulator'
    source = ROOT/'docker'/'firmware-controller-smoke.cpp'
    include = ROOT/'arduino'/'libraries'/'CcoliRobotControl'/'src'
    subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-pedantic',
                    '-I', str(include), str(source), '-o', str(target)],
                   check=True, capture_output=True, text=True, timeout=60)
    # Includes the enabled-output assertions, inversion, duplicate and malformed
    # corpus from the exact production C++ controller header.
    result = subprocess.run([str(target)], check=True, capture_output=True, text=True, timeout=10)
    assert result.stdout.strip() == 'firmware controller native smoke passed'
    return target

class NativeWire:
    source = 'sim'
    def __init__(self, binary):
        self.process = subprocess.Popen([str(binary), '--wire'], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True, bufsize=1)
        self.sent = []
        self.received = []
        self.errors = []
        self._sink = lambda _: None
        self._write_lock = threading.Lock()
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()
    def attach(self, sink): self._sink = sink
    def _read(self):
        try:
            for line in self.process.stdout:
                assert len(line.encode()) <= 2049
                packet = json.loads(line)
                self.received.append(packet)
                self._sink(packet)
        except BaseException as error:
            self.errors.append(type(error).__name__)
    def send(self, packet):
        raw = json.dumps(packet, allow_nan=False, separators=(',', ':'))
        assert len(raw.encode()) <= 2048
        with self._write_lock:
            self.sent.append(copy.deepcopy(packet))
            self.process.stdin.write(raw+'\n')
            self.process.stdin.flush()
    def wait(self, predicate, timeout=3):
        end = time.monotonic()+timeout
        while time.monotonic()<end:
            if self.errors: pytest.fail('native telemetry reader failed: '+str(self.errors))
            if predicate(): return
            assert self.process.poll() is None
            time.sleep(.005)
        pytest.fail('native controller observation timeout')
    def close(self):
        if self.process.stdin: self.process.stdin.close()
        try: self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill(); self.process.wait(timeout=2)
        self.thread.join(timeout=2)

@pytest.fixture
def wire_rig(native_binary):
    wire = NativeWire(native_binary)
    core = RobotController(wire)
    wire.attach(core.accept)
    core.discover()
    wire.wait(lambda: core.snapshot()['state']=='discovered')
    core.configure('companion_4_lcd')
    core.calibrate([dict(servo=i, min_angle=70, max_angle=110, center_angle=90,
                        max_speed_dps=30, inverted=i==1) for i in range(4)])
    wire.wait(lambda: core.snapshot()['state']=='calibrated')
    core.arm()
    wire.wait(lambda: core.snapshot()['state']=='armed')
    yield wire, core
    core.stop()
    wire.close()


def test_native_mcu_discover_channel_move_done_and_duplicate(wire_rig):
    wire, core = wire_rig
    assert core.snapshot()['capabilities']['firmware_revision'] == 'robot-control-1'
    started = time.monotonic()
    result = core.move(2, 100, 500)
    wire.wait(lambda: any(p['status']=='RUNNING' and p['command_id']==result['command_id'] for p in wire.received))
    command = wire.sent[-1]
    time.sleep(.15)
    wire.send(command)
    wire.wait(lambda: core.snapshot()['state']=='completed')
    elapsed = time.monotonic()-started
    assert .45 <= elapsed < .7
    assert core.snapshot()['commanded_angles'] == [90,90,100,90]
    assert core.snapshot()['measured_angles'] is None
    assert core.snapshot()['last_result']['physical_success'] is None
    assert wire.errors == []


def test_native_named_gesture_contract_and_heartbeat(wire_rig):
    wire, core = wire_rig
    core.gesture('notification_nod', .3)
    last_heartbeat = time.monotonic()
    end = time.monotonic()+4
    while core.snapshot()['state'] != 'completed' and time.monotonic()<end:
        if time.monotonic()-last_heartbeat > .4:
            core.heartbeat(); last_heartbeat=time.monotonic()
        time.sleep(.005)
    assert core.snapshot()['state']=='completed'
    assert core.snapshot()['commanded_angles'][0] == 90
    assert not any(p['status']=='ERROR' for p in wire.received)
    assert all('lease_ms' in p for p in wire.sent)
    assert 'duration_ms' not in next(p for p in wire.sent if p['op']=='gesture')


def test_native_deadman_stops_locally_without_server_poll(wire_rig):
    wire, core = wire_rig
    core.move(0, 100, 5000)
    wire.wait(lambda: core.snapshot()['state']=='stopped', timeout=3)
    assert core.snapshot()['last_error']=='lease_expired'
    assert 90 < core.snapshot()['commanded_angles'][0] < 100
    assert not core.snapshot()['calibrated']
    with pytest.raises(RoboticsError): core.arm()


def test_native_stop_holds_current_position_and_invalidates_session(wire_rig):
    wire, core = wire_rig
    core.move(1, 105, 1000)
    wire.wait(lambda: any(p['status']=='RUNNING' for p in wire.received))
    time.sleep(.15)
    core.stop(mode='hold')
    wire.wait(lambda: any(p['status']=='STOPPED' for p in wire.received))
    stopped = core.snapshot()['commanded_angles'][1]
    assert 90 < stopped < 105
    core.request_state()
    wire.wait(lambda: any(p['status']=='ERROR' and p.get('error')=='session_mismatch' for p in wire.received))
    assert core.snapshot()['state']=='fault'
    with pytest.raises(RoboticsError): core.move(1, 95, 1000)
def test_native_latency_report(wire_rig):
    wire, core = wire_rig
    for index in range(5):
        core.move(0, 95 if index % 2 == 0 else 90, 250)
        wire.wait(lambda: core.snapshot()['state']=='completed')
    core.stop()
    wire.wait(lambda: core.snapshot()['metrics']['stop_latency_p50_s'] is not None)
    metrics = core.snapshot()['metrics']
    report = {'source': 'compiled_mcu_no_hardware', 'action_samples': metrics['action_samples'],
              'action_p50_s': round(metrics['action_p50_s'], 6),
              'action_p95_s': round(metrics['action_p95_s'], 6),
              'stop_latency_p50_s': round(metrics['stop_latency_p50_s'], 6),
              'timeouts': metrics['timeouts'], 'physical_success': None}
    assert report['action_samples'] == 5
    assert report['action_p50_s'] > 0
    assert report['action_p95_s'] >= report['action_p50_s']
    print('ROBOTICS_METRICS '+json.dumps(report, sort_keys=True))