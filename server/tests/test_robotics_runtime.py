"""The dashboard and live Atom use the same capability/command state machine."""
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from src.robotics.runtime import RobotRuntime
from src.robotics.models import RoboticsError
from web.app import create_app
from web.auth import configure


class Clock:
    now = 10.0
    def __call__(self): return self.now
    def advance(self, seconds): self.now += seconds


def client_rig():
    clock = Clock()
    runtime = RobotRuntime(clock=clock)
    agent = SimpleNamespace(robotics_runtime=runtime)
    app = create_app(lambda:agent,lambda:None,lambda:'agent',lambda:{})
    configure('')
    return TestClient(app), runtime, clock


def setup_sim(client):
    assert client.post('/api/robotics/source',json={'source':'sim'}).status_code == 200
    assert client.post('/api/robotics/discover').status_code == 200
    assert client.post('/api/robotics/configure',json={'profile_id':'direct_1'}).status_code == 200
    channel = {'servo':0,'min_angle':70,'center_angle':90,'max_angle':110,'max_speed_dps':30,'inverted':False}
    assert client.post('/api/robotics/calibrate',json={'channels':[channel],'wiring_confirmed':True}).status_code == 200
    assert client.post('/api/robotics/arm',json={'confirmed':True}).status_code == 200


def test_initial_state_reports_missing_hardware_and_setup_parts():
    client, runtime, clock = client_rig()
    status = client.get('/api/robotics/status').json()
    assert status['controller']['state'] == 'disconnected'
    assert status['physical_connected'] is False
    profiles = client.get('/api/robotics/profiles').json()['profiles']
    assert {'voice_only','direct_1','companion_4_lcd','so101'} <= {p['id'] for p in profiles}
    assert all(p['motion_enabled_by_selection'] is False for p in profiles)
    assert client.post('/api/robotics/arm',json={'confirmed':True}).status_code == 409


def test_simulator_selection_does_not_arm_and_real_moves_never_claim_physical_success():
    client, runtime, clock = client_rig()
    setup_sim(client)
    response = client.post('/api/robotics/move',json={'servo':0,'angle':100,'duration_ms':1000})
    assert response.status_code == 200
    assert response.json()['status'] == 'pending'
    assert response.json()['source'] == 'sim'
    for _ in range(12):
        clock.advance(.1)
        runtime.tick()
    status = client.get('/api/robotics/status').json()
    assert status['controller']['state'] == 'completed'
    assert status['controller']['commanded_angles'][0] == 100
    assert status['controller']['last_result']['physical_success'] is not True
    assert client.post('/api/robotics/stop').status_code == 200
    assert client.get('/api/robotics/status').json()['controller']['armed'] is False
    assert client.post('/api/robotics/move',json={'servo':0,'angle':90,'duration_ms':1000}).status_code == 409


@pytest.mark.parametrize('body', [{'servo':True,'angle':95}, {'servo':0,'angle':True}, {'servo':0,'angle':-1}, {'servo':0,'angle':190}, {'servo':0,'angle':95,'duration_ms':0}, {'servo':0,'angle':95,'extra':'ignored'}])
def test_invalid_move_never_dispatches(body):
    client, runtime, clock = client_rig()
    setup_sim(client)
    before = len(runtime.sim_driver.sent)
    assert client.post('/api/robotics/move',json=body).status_code in {409,422}
    assert len(runtime.sim_driver.sent) == before


def test_confirmation_and_auth_are_required_before_motion():
    client, runtime, clock = client_rig()
    setup_sim(client)
    assert client.post('/api/robotics/arm',json={'confirmed':False}).status_code == 422
    configure('synthetic-auth')
    try:
        for path in ('status','profiles'):
            assert client.get('/api/robotics/'+path).status_code == 401
        assert client.post('/api/robotics/stop').status_code == 401
    finally:
        configure('')


def test_old_connection_telemetry_cannot_change_new_core():
    runtime = RobotRuntime()
    first, second = [], []
    old = runtime.bind_atom(lambda packet:first.append(packet))
    runtime.discover()
    old_command = first[-1]
    new = runtime.bind_atom(lambda packet:second.append(packet))
    assert new != old
    assert runtime.accept_atom(old, {'v':1,'status':'DONE',**old_command}) is False
    runtime.unbind_atom(old)
    assert runtime.snapshot()['physical_connected'] is True
    runtime.unbind_atom(new)
    assert runtime.snapshot()['physical_connected'] is False


def test_manual_simulated_observation_cannot_be_marked_measured():
    client, runtime, clock = client_rig()
    setup_sim(client)
    body = {'kind':'sensor','source_id':'button','data':{'pressed':False},'sequence':1,'provenance':'measured'}
    assert client.post('/api/robotics/sim/observation',json=body).status_code == 422
    del body['provenance']
    assert client.post('/api/robotics/sim/observation',json=body).status_code == 200
    observation = runtime.observations.get('sensor','button')
    assert observation['provenance'] == 'simulated'


def test_stop_and_heartbeat_do_not_wait_for_long_task_planning(monkeypatch):
    import threading
    client, runtime, clock = client_rig()
    setup_sim(client)
    entered, release = threading.Event(), threading.Event()
    runner = runtime._pair()[1]
    def slow_start(*_args, **_kwargs):
        entered.set()
        assert release.wait(3)
        return {'status':'stopped','physical_success':False}
    monkeypatch.setattr(runner, 'start', slow_start)
    worker = threading.Thread(target=lambda:runtime.start_task('notification',{},confirmed=True))
    worker.start()
    assert entered.wait(1)
    clock.advance(.5)
    runtime.tick()
    assert runtime.sim_driver.sent[-1]['op'] == 'heartbeat'
    assert runtime.snapshot()['task']['status'] == 'planning'
    assert client.post('/api/robotics/stop').status_code == 200
    assert runtime.sim_driver.sent[-1]['op'] == 'stop'
    assert not runtime.controller.snapshot()['armed']
    release.set()
    worker.join(1)
    assert not worker.is_alive()


def test_simulator_calibration_has_source_device_profile_storage(tmp_path):
    clock=Clock()
    runtime=RobotRuntime(clock=clock,data_directory=tmp_path)
    real=tmp_path/'atom'/'existing-device'/'direct_1.json'
    real.parent.mkdir(parents=True)
    real.write_text('physical-calibration-do-not-overwrite',encoding='utf-8')
    runtime.select_source('sim')
    runtime.discover()
    runtime.configure('direct_1')
    runtime.calibrate([dict(servo=0,min_angle=70,center_angle=90,max_angle=110,max_speed_dps=30,inverted=False)],wiring_confirmed=True)
    saved=list((tmp_path/'sim').rglob('*.json'))
    assert len(saved)==1
    assert 'direct_1' in saved[0].name
    assert real.read_text(encoding='utf-8')=='physical-calibration-do-not-overwrite'
    assert not (tmp_path/'calibration.json').exists()


def test_late_planning_failure_cannot_replace_new_connection_state(monkeypatch):
    import threading
    runtime=RobotRuntime()
    runtime.bind_atom(lambda _packet:None)
    old=runtime._pair()
    entered,release=threading.Event(),threading.Event()
    failures=[]
    def delayed(*_args,**_kwargs):
        entered.set()
        assert release.wait(3)
        raise RoboticsError('old_policy_failed')
    monkeypatch.setattr(old[1],'start',delayed)
    def start():
        try:runtime.start_task('notification',{},confirmed=True)
        except RoboticsError as error:failures.append(error.code)
    thread=threading.Thread(target=start)
    thread.start()
    assert entered.wait(1)
    runtime.bind_atom(lambda _packet:None)
    release.set()
    thread.join(1)
    assert failures==['old_policy_failed']
    assert runtime.snapshot()['task']['status']=='idle'


def test_unexpected_recorder_failure_stops_motion_and_keeps_heartbeat_thread(monkeypatch):
    import threading
    client,runtime,clock=client_rig()
    setup_sim(client)
    observed=threading.Event()
    calls=[]
    def broken_tick():
        calls.append(1)
        if len(calls)==1:raise OSError('synthetic-private-disk-path')
        observed.set()
    monkeypatch.setattr(runtime,'tick',broken_tick)
    runtime.start()
    try:
        assert observed.wait(2)
        assert runtime._thread.is_alive()
        assert not runtime.controller.snapshot()['armed']
        assert runtime.sim_driver.sent[-1]['op']=='stop'
        assert runtime.snapshot()['task']['reason_code']=='runtime_failed'
    finally:runtime.close()


def test_active_episode_disk_failure_preserves_data_and_safety_thread(tmp_path, monkeypatch):
    import threading
    from pathlib import Path
    client,runtime,clock=client_rig()
    setup_sim(client)
    runtime.recorder.directory=tmp_path/'episodes'
    runtime.recorder.set_enabled(True)
    episode_id=runtime.recorder.start('notification',{'source':'sim'})
    runtime.recorder.record('observation',{'public_marker':'keep-this-frame'},timestamp=clock())
    observed=threading.Event()
    calls=[]
    def disk_failed(*_args,**_kwargs):raise OSError('synthetic-private-disk-path')
    monkeypatch.setattr(Path,'write_text',disk_failed)
    def tick():
        calls.append(1)
        if len(calls)==1:runtime.recorder.finish({'status':'done'},timestamp=clock())
        observed.set()
    monkeypatch.setattr(runtime,'tick',tick)
    runtime.start()
    try:
        assert observed.wait(2)
        assert runtime._thread.is_alive()
        assert not runtime.recorder.enabled
        assert not runtime.controller.snapshot()['armed']
        episode=runtime.recorder.load(episode_id)
        assert episode['events'][0]['data']=={'public_marker':'keep-this-frame'}
        assert episode['events'][-1]['data']['status']=='aborted'
    finally:runtime.close()
