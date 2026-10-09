import importlib
import math
import time
import threading

import pytest


JOINTS=['shoulder_pan','shoulder_lift','elbow_flex','wrist_flex','wrist_roll','gripper']
UNITS=['degrees']*5+['percent']


def manifest():
    return {'schema_version':1,'checkpoint':'lerobot/smolvla_base','revision':'a'*40,
        'joint_order':JOINTS,'joint_units':UNITS,'units':'mixed','profile_id':'so101',
        'firmware_revision':'lerobot-0.6.1','calibration_id':'b'*64,
        'camera_features':{'observation.images.camera1':'front','observation.images.camera2':'wrist','observation.images.camera3':'side'},
        'action_feature_names':[f'{joint}.pos' for joint in JOINTS],
        'state_feature_names':[f'{joint}.pos' for joint in JOINTS],
        'hardware_validated':False}


def test_manifest_keeps_checkpoint_revision_units_feature_order_and_calibration():
    from src.robotics.vla_adapter import PolicyManifest
    parsed=PolicyManifest.parse(manifest())
    assert parsed.joint_units==tuple(UNITS)
    for key,value in [('joint_units',['degrees']*6),('revision','main'),
                      ('action_feature_names',['pad']*32),('calibration_id',''),('calibration_id','made-up'),('hardware_validated','false')]:
        bad=manifest(); bad[key]=value
        with pytest.raises(ValueError):
            PolicyManifest.parse(bad)


def test_policy_never_slices_raw_padded_actions_into_robot_angles():
    from src.robotics.vla_adapter import named_action_plan, PolicyManifest
    parsed=PolicyManifest.parse(manifest())
    values={f'{name}.pos':(-5 if i<5 else 50) for i,name in enumerate(JOINTS)}
    plan=named_action_plan(values,parsed,duration_ms=1000)
    assert plan['actions'][0]['joints'][0]=={'servo':0,'angle':-5.0}
    assert plan['joint_units']==UNITS
    with pytest.raises(ValueError):
        named_action_plan(list(range(32)),parsed,duration_ms=1000)
    for value in (True,float('nan'),float('inf'),999):
        invalid=dict(values); invalid['gripper.pos']=value
        with pytest.raises(ValueError):
            named_action_plan(invalid,parsed,duration_ms=1000)


def test_vla_import_does_not_load_torch_in_voice_runtime():
    import sys
    before=set(sys.modules)
    importlib.import_module('src.robotics.vla_adapter')
    importlib.import_module('src.robotics.drivers.lerobot')
    assert 'torch' not in set(sys.modules)-before


class FakeBus:
    def __init__(self):
        self.calls=[]
        self.is_connected=False
        self.is_calibrated=True
        self.motors={joint:object() for joint in JOINTS}
    def connect(self):
        self.calls.append('connect'); self.is_connected=True
    def disable_torque(self):
        self.calls.append('disable')
    def enable_torque(self):
        self.calls.append('enable')
    def disconnect(self,disable_torque=True):
        self.calls.append('disconnect'); self.is_connected=False


class FakeRobot:
    def __init__(self):
        self.bus=FakeBus(); self.cameras={}; self.sent=[]
        self.positions={f'{name}.pos':0.0 for name in JOINTS}
        self.positions['gripper.pos']=50.0
        self.calibration={name:{'id':i+1} for i,name in enumerate(JOINTS)}
    @property
    def is_connected(self):
        return self.bus.is_connected
    @property
    def is_calibrated(self):
        return self.bus.is_calibrated
    def configure(self):
        self.bus.calls.append('configure')
    def calibrate(self):
        self.bus.calls.append('calibrate')
    def get_observation(self):
        return dict(self.positions)
    def send_action(self,action):
        self.sent.append(dict(action)); self.positions.update(action); return dict(action)
    def disconnect(self):
        self.bus.disconnect()


def test_sdk_discovery_leaves_torque_disabled_and_requires_calibration_before_arm(tmp_path):
    from src.robotics.drivers.lerobot import SO101Driver
    robot=FakeRobot()
    driver=SO101Driver('COM_TEST','arm_one',calibration_dir=tmp_path,robot_factory=lambda **kwargs:robot)
    caps=driver.connect()
    assert robot.bus.calls==['connect','disable']
    assert caps['joint_order']==JOINTS and caps['joint_units']==UNITS
    assert caps['feedback_kind']=='measured'
    assert driver.read_state()['measured_angles']==[0.0]*5+[50.0]
    with pytest.raises(ValueError):
        driver.arm()
    driver.close()


def test_sdk_human_takeover_disables_inference_motion(tmp_path):
    from src.robotics.drivers.lerobot import SO101Driver
    robot=FakeRobot()
    driver=SO101Driver('COM_TEST','arm_one',calibration_dir=tmp_path,robot_factory=lambda **kwargs:robot)
    driver.connect()
    driver.human_takeover()
    assert robot.bus.calls[-1]=='disable'
    assert driver.read_state()['armed'] is False
    assert robot.sent==[]
    driver.close()


def limits():
    return [{'servo':index,'min_angle':-30 if index<5 else 0,'max_angle':30 if index<5 else 100,
             'center_angle':0 if index<5 else 50,'max_speed_dps':20,'inverted':False} for index in range(6)]


def command(driver,op,seq,**values):
    return {'cmd':'ROBOT_CONTROL','v':1,'op':op,'command_id':f'command-{seq}',
            'session_id':'session-one','seq':seq,'valid_for_ms':2000,'lease_ms':2000,
            'boot_id':driver.boot_id,**values}


def test_sdk_motion_uses_named_native_values_and_duplicate_never_replays(tmp_path):
    from src.robotics.drivers.lerobot import SO101Driver
    robot=FakeRobot(); statuses=[]
    driver=SO101Driver('COM_TEST','arm_one',calibration_dir=tmp_path,robot_factory=lambda **kwargs:robot,sink=statuses.append)
    driver.send(command(driver,'discover',1))
    driver.send(command(driver,'calibrate',2,channels=limits()))
    driver.send(command(driver,'arm',3))
    driver.send(command(driver,'move',4,joints=[{'servo':0,'angle':-1}],duration_ms=100))
    driver._motion.join(timeout=1)
    assert statuses[-1]['status']=='DONE'
    assert robot.sent[-1]['shoulder_pan.pos']==-1
    calls=len(robot.sent)
    driver.send(command(driver,'move',4,joints=[{'servo':0,'angle':-1}],duration_ms=100))
    assert len(robot.sent)==calls
    driver.send(command(driver,'stop',5,mode='detach'))
    assert statuses[-1]['status']=='STOPPED' and driver.armed is False
    driver.close()


def test_invalid_trajectory_does_not_send_any_joint_and_deadman_disables(tmp_path):
    from src.robotics.drivers.lerobot import SO101Driver
    robot=FakeRobot(); statuses=[]
    now=[0.0]
    driver=SO101Driver('COM_TEST','arm_one',calibration_dir=tmp_path,robot_factory=lambda **kwargs:robot,sink=statuses.append,clock=lambda:now[0])
    driver.send(command(driver,'discover',1))
    driver.send(command(driver,'calibrate',2,channels=limits()))
    driver.send(command(driver,'arm',3))
    before=len(robot.sent)
    driver.send(command(driver,'move',4,joints=[{'servo':0,'angle':1},{'servo':1,'angle':999}],duration_ms=1000))
    assert len(robot.sent)==before
    assert statuses[-1]['status']=='ERROR'
    now[0]=3.0
    assert driver._watchdog_thread.is_alive()
    driver._closed.wait(.05)
    assert driver.armed is False and robot.bus.calls[-1]=='disable'
    driver.close()


def test_unvalidated_checkpoint_never_calls_worker_and_stale_inference_never_moves():
    from src.robotics.vla_adapter import SmolVLAAdapter
    calls=[]
    adapter=SmolVLAAdapter(manifest(),lambda request:calls.append(request))
    with pytest.raises(ValueError,match='policy_hardware_validation_required'):
        adapter.plan('Move block',{}, {})
    assert calls==[]


def test_physical_plan_binds_sdk_calibration_and_rejects_old_observation():
    from src.robotics.vla_adapter import SmolVLAAdapter
    value=manifest(); value['hardware_validated']=True
    binding={'firmware_revision':'lerobot-0.6.1','joint_order':JOINTS,'profile_id':'so101'}
    state={'armed':True,'calibrated':True,'profile_id':'so101','sdk_calibration_id':'b'*64,
           'capabilities':{'controller':'so101','feedback_kind':'measured','joint_order':JOINTS,'joint_units':UNITS,
                           'units':'mixed','firmware_revision':'lerobot-0.6.1'},'calibration':limits()}
    pixels={'width':1,'height':1,'rgb':[0,0,0],'frame_id':'frame-one'}
    observation={'joint':{'provenance':'measured','driver_id':'so101-sdk-test','calibration':binding,'age_s':0,
                          'data':{'angles':[0]*5+[50]}},
                 'rgb':{'source_id':'front','driver_id':'camera-sdk-test','provenance':'measured','age_s':0,'data':pixels}}
    now=[0.0]
    def worker(request):
        now[0]=3.0
        return {'revision':'a'*40,'action':{f'{name}.pos':0 if index<5 else 50 for index,name in enumerate(JOINTS)}}
    adapter=SmolVLAAdapter(value,worker,clock=lambda:now[0],
                          observation_provider=lambda source:{'source_id':source,'driver_id':'camera-sdk-test','provenance':'measured','age_s':0,'data':pixels})
    with pytest.raises(ValueError,match='observation_stale'):
        adapter.plan('Move block',observation,state)
    state['sdk_calibration_id']='different'
    with pytest.raises(ValueError,match='policy_calibration_or_capability_mismatch'):
        adapter.plan('Move block',observation,state)


def test_local_recorded_episode_conversion_retains_split_and_native_joint_labels():
    from src.robotics.lerobot_worker import rows_from_episodes
    value=manifest()
    observations=[{'kind':'joint','source_id':'arm_one','provenance':'simulated','data':{'angles':[0]*5+[50]}}]
    for source in ('front','wrist','side'):
        observations.append({'kind':'rgb','source_id':source,'provenance':'simulated',
                             'data':{'frame_id':'frame-one','width':1,'height':1,'rgb':[0,0,0]}})
    episode={'v':1,'episode_id':'episode-one','task':'object_tidy','metadata':{'source':'sim'},'events':[
        {'kind':'observation','timestamp':1,'data':{'robot_state':{'sdk_calibration_id':'b'*64},'observations':observations}},
        {'kind':'intervention','timestamp':1.5,'data':{'op':'correct'}},
        {'kind':'action','timestamp':2,'data':{'op':'move_joints','duration_ms':1000,
         'joints':[{'servo':i,'angle':-1 if i<5 else 45} for i in range(6)]}},
        {'kind':'result','timestamp':3,'data':{'status':'completed'}}]}
    rows=rows_from_episodes([episode],value,eval_episode_ids={'episode-one'})
    assert rows[0]['split']=='eval' and rows[0]['provenance']=='simulated_episode'
    assert rows[0]['human_corrected'] is True
    assert rows[0]['actions'][0]==[-1.0]*5+[45.0]
    episode['metadata']['source']='physical'
    with pytest.raises(ValueError):
        rows_from_episodes([episode],value,eval_episode_ids=set())


def test_manual_sdk_leader_targets_are_named_validated_and_read_only():
    from src.robotics.drivers.lerobot import read_teleoperator_target
    class Leader:
        is_connected=True
        is_calibrated=True
        def get_action(self):
            return {f'{joint}.pos':-1 if index<5 else 60 for index,joint in enumerate(JOINTS)}
    joints=read_teleoperator_target(Leader())
    assert joints==[{'servo':index,'angle':-1.0 if index<5 else 60.0} for index in range(6)]
    leader=Leader(); leader.is_calibrated=False
    with pytest.raises(ValueError):
        read_teleoperator_target(leader)


def test_stop_cancels_arm_in_progress_before_final_enable(tmp_path):
    from src.robotics.drivers.lerobot import SO101Driver
    robot=FakeRobot(); entered=threading.Event(); release=threading.Event(); errors=[]
    def configure():
        entered.set()
        assert release.wait(2)
        robot.bus.calls.append('configure')
    robot.configure=configure
    driver=SO101Driver('COM_TEST','arm_one',calibration_dir=tmp_path,robot_factory=lambda **kwargs:robot)
    driver.connect(); driver.set_limits(limits())
    def arming():
        try:
            driver.arm()
        except ValueError as exc:
            errors.append(str(exc))
    arm_thread=threading.Thread(target=arming); arm_thread.start()
    assert entered.wait(1)
    stop_thread=threading.Thread(target=driver.stop); stop_thread.start()
    assert driver._halt.wait(1)
    release.set(); arm_thread.join(2); stop_thread.join(2)
    assert not arm_thread.is_alive() and not stop_thread.is_alive()
    assert driver.armed is False and driver._halt.is_set() and driver.channels==[]
    assert 'enable' not in robot.bus.calls
    assert errors==['arm_cancelled']
    driver.close()


def test_failed_torque_io_still_invalidates_limits_and_arming(tmp_path):
    from src.robotics.drivers.lerobot import SO101Driver
    robot=FakeRobot()
    driver=SO101Driver('COM_TEST','arm_one',calibration_dir=tmp_path,robot_factory=lambda **kwargs:robot)
    driver.connect(); driver.set_limits(limits()); driver.arm()
    original=robot.bus.disable_torque
    def failing_disable():
        raise OSError('synthetic bus failure')
    robot.bus.disable_torque=failing_disable
    with pytest.raises(OSError):
        driver.stop()
    assert not driver.armed and driver.channels==[] and driver._halt.is_set()
    robot.bus.disable_torque=original
    driver.close()


def test_isolated_worker_client_matches_revision_and_rejects_timeout():
    import sys
    from src.robotics.vla_adapter import SubprocessPolicyWorker
    responder="import json,sys; print(json.dumps({'ready':True,'revision':'a'*40}),flush=True); [print(json.dumps({'revision':'a'*40,'action':{'gripper.pos':50}}),flush=True) for line in sys.stdin]"
    with SubprocessPolicyWorker([sys.executable,'-u','-c',responder],revision='a'*40,startup_timeout_s=2,request_timeout_s=1) as worker:
        assert worker({'instruction':'public synthetic'})['action']=={'gripper.pos':50}
    delayed="import json,time; print(json.dumps({'ready':True,'revision':'a'*40}),flush=True); time.sleep(2)"
    with SubprocessPolicyWorker([sys.executable,'-u','-c',delayed],revision='a'*40,startup_timeout_s=2,request_timeout_s=.05) as worker:
        with pytest.raises(ValueError,match='policy_worker_timeout'):
            worker({'instruction':'public synthetic'})
        assert worker.closed


def test_failed_moves_are_not_relabelled_as_successful_human_demonstrations():
    from src.robotics.lerobot_worker import rows_from_episodes
    observations=[{'kind':'joint','source_id':'arm_one','provenance':'simulated','data':{'angles':[0]*5+[50]}}]
    for source in ('front','wrist','side'):
        observations.append({'kind':'rgb','source_id':source,'provenance':'simulated',
            'data':{'frame_id':'frame-one','width':1,'height':1,'rgb':[0,0,0]}})
    action={'op':'move_joints','duration_ms':1000,'joints':[{'servo':i,'angle':0 if i<5 else 50} for i in range(6)]}
    episode={'v':1,'episode_id':'corrected-one','task':'object_tidy','metadata':{'source':'sim'},'events':[
        {'kind':'observation','timestamp':1,'data':{'robot_state':{'sdk_calibration_id':'b'*64},'observations':observations}},
        {'kind':'action','timestamp':1.2,'data':action},
        {'kind':'failure','timestamp':1.3,'data':{'reason':'collision'}},
        {'kind':'intervention','timestamp':1.4,'data':{'op':'correct'}},
        {'kind':'action','timestamp':1.5,'data':action},
        {'kind':'result','timestamp':2,'data':{'status':'completed'}}]}
    rows=rows_from_episodes([episode],manifest(),eval_episode_ids=set())
    assert len(rows)==1 and rows[0]['human_corrected'] is True


def test_training_manifest_template_remains_explicitly_unvalidated():
    from src.robotics.lerobot_worker import deployment_template
    value=deployment_template('local:checkpoints/public-test','c'*64,
        ['observation.images.camera1','observation.images.camera2','observation.images.camera3'])
    assert value['hardware_validated'] is False and value['calibration_id']=='0'*64
    assert value['joint_units']==UNITS and value['state_feature_names']==[f'{joint}.pos' for joint in JOINTS]


def test_sdk_subprocess_transport_forwards_actual_protocol_events_without_torch():
    import sys
    from src.robotics.drivers.lerobot import SubprocessRobotTransport
    program="import json,sys; print(json.dumps({'ready':True,'sdk':'lerobot-0.6.1'}),flush=True); [print(json.dumps({'status':'STOPPED','command_id':json.loads(line)['command_id']}),flush=True) for line in sys.stdin]"
    received=[]; arrived=threading.Event()
    def sink(value):
        received.append(value); arrived.set()
    transport=SubprocessRobotTransport([sys.executable,'-u','-c',program],startup_timeout_s=2)
    transport.bind(sink)
    transport.send({'cmd':'ROBOT_CONTROL','op':'stop','command_id':'public-test'})
    assert arrived.wait(1) and received[0]['status']=='STOPPED'
    assert transport.source=='physical'
    transport.close()


def test_sdk_arm_validates_actual_measurement_before_goal_or_enable(tmp_path):
    from src.robotics.drivers.lerobot import SO101Driver
    robot=FakeRobot(); driver=SO101Driver('COM_TEST','arm_one',calibration_dir=tmp_path,robot_factory=lambda **kwargs:robot)
    driver.connect(); driver.set_limits(limits())
    for invalid in (True,float('nan'),999):
        robot.positions['shoulder_pan.pos']=invalid
        with pytest.raises(ValueError):
            driver.arm()
    assert robot.sent==[] and 'enable' not in robot.bus.calls
    driver.close()


def test_sdk_watchdog_survives_io_failure_with_disarmed_state(tmp_path):
    from src.robotics.drivers.lerobot import SO101Driver
    robot=FakeRobot(); now=[0.0]
    driver=SO101Driver('COM_TEST','arm_one',calibration_dir=tmp_path,robot_factory=lambda **kwargs:robot,clock=lambda:now[0])
    driver.connect(); driver.set_limits(limits()); driver.arm()
    original=robot.bus.disable_torque
    def failing():
        raise OSError('public synthetic transport failure')
    robot.bus.disable_torque=failing; now[0]=3
    time.sleep(.08)
    assert driver._watchdog_thread.is_alive() and not driver.armed and driver._halt.is_set()
    robot.bus.disable_torque=original
    driver.close()


def test_sdk_deadman_emits_last_command_stop_telemetry(tmp_path):
    from src.robotics.drivers.lerobot import SO101Driver
    robot=FakeRobot(); now=[0.0]; received=[]
    driver=SO101Driver('COM_TEST','arm_one',calibration_dir=tmp_path,
        robot_factory=lambda **kwargs:robot,clock=lambda:now[0],sink=received.append)
    driver.send(command(driver,'discover',1)); driver.send(command(driver,'calibrate',2,channels=limits()))
    driver.send(command(driver,'arm',3)); now[0]=3
    time.sleep(.08)
    assert received[-1]['status']=='STOPPED' and received[-1]['error']=='lease_expired'
    assert received[-1]['command_id']=='command-3' and received[-1]['armed'] is False
    driver.close()


def test_cuda_profile_is_opt_in_and_preserves_cpu_image():
    from pathlib import Path
    import yaml
    root=Path(__file__).resolve().parents[2]
    compose=yaml.safe_load((root/'docker'/'docker-compose.robotics.yml').read_text())
    assert compose['services']['policy-worker']['image']=='ccoli-vla:0.6.1'
    gpu=compose['services']['policy-worker-cuda']
    assert gpu['profiles']==['cuda'] and gpu['image']=='ccoli-vla-cuda:0.6.1'
    assert gpu['build']['args']['TORCH_WHEEL_INDEX']=='https://download.pytorch.org/whl/cu128'
    assert gpu['gpus']==[{'driver':'nvidia','count':'all'}] and '--device' in gpu['command'] and 'cuda' in gpu['command']


@pytest.mark.parametrize('extra_source,extra_driver',[('wrong-source','camera-test'),('wrist',''),('wrist',True)])
def test_vla_extra_camera_must_have_registered_driver_and_exact_source(extra_source,extra_driver):
    from src.robotics.vla_adapter import SmolVLAAdapter
    value=manifest(); value['hardware_validated']=True
    binding={'firmware_revision':'lerobot-0.6.1','joint_order':JOINTS,'profile_id':'so101'}
    state={'armed':True,'calibrated':True,'profile_id':'so101','sdk_calibration_id':'b'*64,
        'capabilities':{'controller':'so101','feedback_kind':'measured','joint_order':JOINTS,
                        'joint_units':UNITS,'units':'mixed','firmware_revision':'lerobot-0.6.1'},'calibration':limits()}
    pixels={'width':1,'height':1,'rgb':[0,0,0],'frame_id':'frame-one'}
    observation={'joint':{'provenance':'measured','driver_id':'so101-test','calibration':binding,'age_s':0,
                           'data':{'angles':[0]*5+[50]}},
                 'rgb':{'source_id':'front','driver_id':'camera-test','provenance':'measured','age_s':0,'data':pixels}}
    calls=[]
    def provider(source):
        return {'source_id':extra_source if source=='wrist' else source,'driver_id':extra_driver,
                'provenance':'measured','age_s':0,'data':pixels}
    adapter=SmolVLAAdapter(value,lambda request:calls.append(request),observation_provider=provider)
    with pytest.raises(ValueError):
        adapter.plan('Move public block',observation,state)
    assert calls==[]


def test_windows_sdk_launch_uses_separate_interpreter_and_native_com_not_docker(tmp_path):
    from src.robotics.drivers.lerobot import sdk_worker_launch
    python=tmp_path/'robot-sdk'/'python.exe'; python.parent.mkdir(); python.touch()
    script=tmp_path/'robotics_policy.py'; script.touch()
    args=sdk_worker_launch(str(python),str(script),port='COM12',robot_id='arm_one',
                           work_dir=str(tmp_path/'episodes'),platform='win32')
    assert args[0]==str(python.resolve()) and args[1]=='-u'
    assert args[args.index('--port')+1]=='COM12'
    assert args[args.index('--work-root')+1]==str((tmp_path/'episodes').resolve())
    assert 'docker' not in args
    with pytest.raises(ValueError,match='unsupported_sdk_port'):
        sdk_worker_launch(str(python),str(script),port='/dev/ttyUSB0',robot_id='arm_one',
                          work_dir=str(tmp_path/'episodes'),platform='win32')


def test_model_warmup_only_uses_public_fixture_and_clears_policy_action_queue():
    from src.robotics.lerobot_worker import SmolVLAWorker
    calls=[]
    class Policy:
        class Config:
            chunk_size=50
        config=Config()
        def reset(self):
            calls.append('reset')
    worker=SmolVLAWorker.__new__(SmolVLAWorker)
    worker.policy=Policy(); worker.camera_features={'observation.images.camera1':None}
    worker.infer=lambda request:(calls.append(request) or {'duration_s':.5,'action':{'gripper.pos':20}})
    result=worker.warmup()
    assert calls[0]['provenance']=='synthetic_fixture' and calls[1]=='reset'
    assert result['duration_s']==.5 and result['hardware_actuated'] is False and 'action' not in result


@pytest.mark.parametrize('stop_path',['stop','human_takeover','calibrate_sdk','lease_expired'])
def test_every_local_stop_invalidates_old_armed_reply_and_session(tmp_path,stop_path):
    from src.robotics.drivers.lerobot import SO101Driver
    robot=FakeRobot(); now=[0.0]; received=[]
    driver=SO101Driver('COM_TEST','arm_one',calibration_dir=tmp_path,
        robot_factory=lambda **kwargs:robot,clock=lambda:now[0],sink=received.append)
    driver.send(command(driver,'discover',1)); driver.send(command(driver,'calibrate',2,channels=limits()))
    old_arm=command(driver,'arm',3); driver.send(old_arm)
    assert received[-1]['armed'] is True
    if stop_path=='lease_expired':
        now[0]=3; driver._expire_lease()
    else:
        getattr(driver,stop_path)()
    driver.send(old_arm)
    assert received[-1]['status']=='ERROR' and received[-1]['armed'] is False
    assert received[-1]['error']=='session_mismatch'
    driver.close()


def test_sdk_measured_source_is_registered_only_after_valid_read_and_removed_on_close(tmp_path):
    from src.robotics.drivers.lerobot import SO101Driver
    from src.robotics.observations import ObservationStore
    robot=FakeRobot(); store=ObservationStore()
    driver=SO101Driver('COM_TEST','arm_one',calibration_dir=tmp_path,
        robot_factory=lambda **kwargs:robot,observation_store=store)
    driver.connect()
    assert ('joint','arm_one') not in store._sources
    driver.read_state()
    assert store.get('joint','arm_one')['driver_id'].startswith('so101-sdk-')
    driver.close()
    with pytest.raises(ValueError):
        store.get('joint','arm_one')
