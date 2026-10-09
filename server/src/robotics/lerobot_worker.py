"""Isolated Python 3.12 LeRobot worker. Importing this module does not load Torch."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import gc
import json
import math
import os
from pathlib import Path
import statistics
import queue
import threading
import sys
import time

from .vla_adapter import (BACKBONE, BACKBONE_REVISION, BASE_CHECKPOINT, BASE_REVISION,
                          PolicyManifest, SO101_JOINTS, SO101_UNITS, named_action_plan)
_WORK_ROOT=Path('/work')


def _local_path(value: str | Path, root: Path | None = None) -> Path:
    root=root or _WORK_ROOT
    path = Path(value).resolve()
    if not path.is_relative_to(root.resolve()) or path.is_symlink():
        raise ValueError('Worker data must stay inside its local work directory')
    return path


def _write_json(path: str | Path, data: dict) -> None:
    target = _local_path(path)
    target.parent.mkdir(parents=True,exist_ok=True)
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
    temporary.replace(target)


class SmolVLAWorker:
    def __init__(self, checkpoint: str = BASE_CHECKPOINT, revision: str = BASE_REVISION,
                 device: str = 'cpu', *, work_root: Path | None = None):
        from importlib.metadata import version
        if version('lerobot') != '0.6.1':
            raise ValueError('LeRobot 0.6.1 is required')
        import torch
        from huggingface_hub import snapshot_download
        from transformers import AutoConfig, AutoProcessor
        from lerobot.policies.smolvla import SmolVLAPolicy, SmolVLAConfig
        from lerobot.policies import make_pre_post_processors
        self.torch = torch
        self.device = torch.device(device)
        self.work_root = (work_root or _WORK_ROOT).resolve()
        if self.device.type=='cuda' and not torch.cuda.is_available():
            raise ValueError('CUDA worker requires an available explicitly passed GPU')
        torch.set_num_threads(max(1,min(8,int(os.environ.get('OMP_NUM_THREADS','4')))))
        self.revision, self.checkpoint = revision, checkpoint
        if checkpoint.startswith('local:'):
            local = _local_path(self.work_root/checkpoint.removeprefix('local:'),self.work_root)
            if hashlib.sha256((local/'model.safetensors').read_bytes()).hexdigest()!=revision:
                raise ValueError('Local checkpoint digest mismatch')
            self.policy_path = local
        else:
            if checkpoint != BASE_CHECKPOINT or revision != BASE_REVISION:
                raise ValueError('Download a reviewed, pinned checkpoint before selecting it')
            self.policy_path = Path(snapshot_download(checkpoint,revision=revision,token=False,
                allow_patterns=['config.json','model.safetensors','policy_*.json','policy_*.safetensors']))
        # No remote Python files are downloaded. Transformer loaders are explicitly validated without remote code.
        backbone = Path(snapshot_download(BACKBONE,revision=BACKBONE_REVISION,token=False,
            allow_patterns=['*.json','*.txt','*.model','*.tiktoken']))
        AutoConfig.from_pretrained(backbone,local_files_only=True,trust_remote_code=False)
        AutoProcessor.from_pretrained(backbone,local_files_only=True,trust_remote_code=False)
        self.backbone_path = backbone
        config = SmolVLAConfig.from_pretrained(self.policy_path,local_files_only=True)
        config.vlm_model_name = str(backbone)
        # The policy checkpoint contains VLM weights; avoid downloading/loading a second VLM weight set.
        config.load_vlm_weights = False
        config.device = str(self.device)
        config.push_to_hub = False
        config.compile_model = False
        config.train_expert_only = True
        config.freeze_vision_encoder = True
        self.policy = SmolVLAPolicy.from_pretrained(self.policy_path,config=config,local_files_only=True,
                                                  token=False,trust_remote_code=False).to(self.device)
        self.preprocess,self.postprocess = make_pre_post_processors(config,str(self.policy_path),
            preprocessor_overrides={'device_processor':{'device':str(self.device)},
                                    'tokenizer_processor':{'tokenizer_name':str(backbone)}},
            postprocessor_overrides={'device_processor':{'device':'cpu'}})
        self.camera_features = {key:tuple(value.shape) for key,value in config.input_features.items()
                                if key.startswith('observation.images.')}
        if tuple(config.input_features['observation.state'].shape)!=(6,) or tuple(config.output_features['action'].shape)!=(6,):
            raise ValueError('Checkpoint state/action features must have six named dimensions')
        self.features = {'action':{'dtype':'float32','shape':(6,), 'names':[f'{name}.pos' for name in SO101_JOINTS]},
                         'observation.state':{'dtype':'float32','shape':(6,), 'names':[f'{name}.pos' for name in SO101_JOINTS]}}
        for key,shape in self.camera_features.items():
            self.features[key]={'dtype':'image','shape':(shape[1],shape[2],shape[0]),'names':['height','width','channels']}
        self.policy.eval()

    def _batch(self, request: dict):
        import numpy as np
        from lerobot.policies.utils import build_inference_frame
        state = request.get('state')
        if not isinstance(state,list) or len(state)!=6 or any(type(value) not in (int,float) or not math.isfinite(value) for value in state):
            raise ValueError('A finite six-joint state is required')
        frames = request.get('frames')
        if not isinstance(frames,dict) or set(frames)!=set(self.camera_features):
            raise ValueError('Camera features must exactly match this checkpoint')
        observation = {f'{name}.pos':float(value) for name,value in zip(SO101_JOINTS,state)}
        for key,shape in self.camera_features.items():
            frame=frames[key]
            if not isinstance(frame,dict) or type(frame.get('width')) is not int or type(frame.get('height')) is not int:
                raise ValueError('Invalid RGB frame')
            width,height=frame['width'],frame['height']
            if not 1<=width<=1280 or not 1<=height<=720:
                raise ValueError('Invalid RGB dimensions')
            pixels=frame.get('rgb')
            if not isinstance(pixels,list) or len(pixels)!=width*height*3 or any(type(value) is not int or not 0<=value<=255 for value in pixels):
                raise ValueError('Invalid RGB pixels')
            image=np.asarray(pixels,dtype=np.uint8).reshape(height,width,3)
            if image.shape!=(shape[1],shape[2],shape[0]):
                import cv2
                image=cv2.resize(image,(shape[2],shape[1]),interpolation=cv2.INTER_AREA)
            observation[key.removeprefix('observation.images.')]=image
        task=request.get('instruction')
        if not isinstance(task,str) or not task.strip() or len(task)>2000:
            raise ValueError('Invalid instruction')
        frame=build_inference_frame(observation,self.device,self.features,task=task,robot_type='so101_follower')
        return self.preprocess(frame)

    def infer(self, request: dict) -> dict:
        from lerobot.policies.utils import make_robot_action
        if 'manifest' in request:
            manifest=PolicyManifest.parse(request['manifest'])
            if manifest.checkpoint!=self.checkpoint or manifest.revision!=self.revision or set(manifest.camera_features)!=set(self.camera_features):
                raise ValueError('Manifest does not match the loaded checkpoint')
        started=time.monotonic()
        batch=self._batch(request)
        # Every new planning request must use the current observation/instruction, not a prior action queue.
        self.policy.reset()
        with self.torch.inference_mode():
            action=self.postprocess(self.policy.select_action(batch))
        if tuple(action.shape)!=(1,6):
            raise ValueError('Unexpected postprocessed action dimensions')
        named=make_robot_action(action,self.features)
        if set(named)!={f'{name}.pos' for name in SO101_JOINTS}:
            raise ValueError('SDK returned unexpected action feature names')
        named={key:float(value) for key,value in named.items()}
        if not all(math.isfinite(value) for value in named.values()):
            raise ValueError('Nonfinite learned action')
        return {'revision':self.revision,'action':named,'duration_s':round(time.monotonic()-started,4),
                'raw_internal_dim':self.policy.config.max_action_dim,'postprocessed_dim':6,
                'provenance':'learned_checkpoint','hardware_actuated':False}

    def warmup(self) -> dict:
        result=self.infer(fixture(self.camera_features,chunk_size=self.policy.config.chunk_size)[0])
        self.policy.reset()
        return {'duration_s':result['duration_s'],'provenance':'synthetic_fixture',
                'hardware_actuated':False,'action_queue_cleared':True}

    def loss(self, row: dict, *, gradients: bool = False, seed: int = 42):
        batch=self._batch(row)
        actions=row.get('actions')
        if not isinstance(actions,list) or len(actions)!=self.policy.config.chunk_size:
            raise ValueError('Training actions must match the checkpoint action horizon')
        for action in actions:
            if not isinstance(action,list) or len(action)!=6 or any(type(value) not in (int,float) or not math.isfinite(value) for value in action):
                raise ValueError('Invalid demonstration action')
        raw=self.torch.tensor(actions,dtype=self.torch.float32,device=self.device).unsqueeze(0)
        # Use the checkpoint's actual action normalizer, not guessed degree/statistics conversions.
        full=dict(batch)
        # Normalize only raw demonstration actions; _batch has already normalized observation.state.
        normalizer=next(step for step in self.preprocess.steps if step.__class__.__name__=='NormalizerProcessorStep')
        from lerobot.processor.converters import batch_to_transition, transition_to_batch
        full['action']=transition_to_batch(normalizer(batch_to_transition({'action':raw})))['action']
        self.torch.manual_seed(seed)
        self.policy.train(gradients)
        with self.torch.enable_grad() if gradients else self.torch.no_grad():
            loss,metrics=self.policy(full)
        return loss,metrics

    def train(self, rows: list[dict], output: str | Path, steps: int = 2) -> dict:
        if not 1<=steps<=100000 or not rows:
            raise ValueError('Training requires demonstrations and a positive step count')
        target=_local_path(output,self.work_root)
        if target.exists():
            raise ValueError('Use a new checkpoint directory; previous checkpoints are retained for rollback')
        training=[row for row in rows if row.get('split')=='train']
        held_out=[row for row in rows if row.get('split')=='eval']
        if not training or not held_out or {r['episode_id'] for r in training}&{r['episode_id'] for r in held_out}:
            raise ValueError('Disjoint training/evaluation episodes are required')
        before=self.evaluate(held_out)
        optimizer=self.torch.optim.AdamW((p for p in self.policy.parameters() if p.requires_grad),lr=1e-5)
        losses=[]
        for index in range(steps):
            optimizer.zero_grad(set_to_none=True)
            loss,_=self.loss(training[index%len(training)],gradients=True,seed=42+index)
            if not self.torch.isfinite(loss):
                raise ValueError('Nonfinite training loss')
            loss.backward()
            self.torch.nn.utils.clip_grad_norm_(self.policy.parameters(),1.0)
            optimizer.step()
            losses.append(float(loss.detach()))
        after=self.evaluate(held_out)
        target.mkdir(parents=True)
        _write_json(target/'training_progress.json',{'steps':steps,'train_losses':losses,
                    'held_out_before':before,'held_out_after':after,'checkpoint_saved':False,
                    'hardware_actuated':False,'uploaded':False})
        # CUDA safetensors serialization otherwise stages the full state repeatedly while
        # optimizer buffers remain live. Release training buffers and save from CPU tensors.
        optimizer.zero_grad(set_to_none=True)
        del optimizer
        gc.collect()
        self.policy.to('cpu')
        if self.device.type=='cuda':
            self.torch.cuda.empty_cache()
        self.policy.config.push_to_hub=False
        self.policy.save_pretrained(target)
        self.preprocess.save_pretrained(target)
        self.postprocess.save_pretrained(target)
        digest=hashlib.sha256((target/'model.safetensors').read_bytes()).hexdigest()
        report={'schema_version':1,'base_revision':self.revision,'checkpoint_digest':digest,
                'steps':steps,'train_losses':losses,'held_out_before':before,'held_out_after':after,
                'dataset_provenance':sorted({row.get('provenance','unverified') for row in rows}),
                'physical_success_verified':False,'uploaded':False,'hardware_actuated':False}
        _write_json(target/'training_report.json',report)
        checkpoint='local:'+str(target.relative_to(self.work_root)).replace('\\','/')
        _write_json(target/'deployment_manifest.template.json',
                    deployment_template(checkpoint,digest,list(self.camera_features)))
        self.policy.to(self.device)
        return report

    def evaluate(self, rows: list[dict]) -> dict:
        if not rows:
            raise ValueError('Evaluation episodes are required')
        losses=[]
        for row in rows:
            loss,_=self.loss(row,seed=1729)
            losses.append(float(loss))
        return {'episodes':len({row['episode_id'] for row in rows}), 'samples':len(rows),
                'flow_matching_loss':statistics.mean(losses),'physical_success_verified':False}


def fixture(camera_features: dict, *, chunk_size: int = 50) -> list[dict]:
    """Public synthetic tensors exercise real training; they do not certify a household task."""
    rows=[]
    for index,(split,color) in enumerate((('train',40),('train',80),('eval',120))):
        frames={key:{'frame_id':f'synthetic-{index}','width':32,'height':32,
                     'rgb':[color,0,255-color]*(32*32)} for key in camera_features}
        state=[0.0]*5+[50.0]
        row={'episode_id':f'synthetic-{index}','split':split,'provenance':'synthetic_fixture',
             'instruction':'Move the small red block to the blue tray.','state':state,'frames':frames,
             'actions':[[float(index)*.1]*5+[50.0] for _ in range(chunk_size)]}
        rows.append(row)
    return rows


def deployment_template(checkpoint: str, revision: str, camera_features: list[str]) -> dict:
    """Metadata is a template until camera/calibration bindings and hardware trials exist."""
    value={'schema_version':1,'checkpoint':checkpoint,'revision':revision,
           'joint_order':list(SO101_JOINTS),'joint_units':list(SO101_UNITS),'units':'mixed',
           'profile_id':'so101','firmware_revision':'lerobot-0.6.1','calibration_id':'0'*64,
           'camera_features':{name:f'bind-camera-{index+1}' for index,name in enumerate(camera_features)},
           'action_feature_names':[f'{name}.pos' for name in SO101_JOINTS],
           'state_feature_names':[f'{name}.pos' for name in SO101_JOINTS],'hardware_validated':False}
    return PolicyManifest.parse(value).public()


def rows_from_episodes(episodes: list[dict], manifest: dict, *, eval_episode_ids: set[str],
                       chunk_size: int = 50) -> list[dict]:
    """Convert explicitly recorded local episodes; preserve physical/simulated provenance."""
    from .episodes import validate_episode
    policy=PolicyManifest.parse(manifest)
    if not 1<=chunk_size<=200:
        raise ValueError('Invalid action horizon')
    rows=[]
    for episode in episodes:
        validate_episode(episode)
        physical=episode.get('metadata',{}).get('source')=='physical'
        result=next((event['data'] for event in reversed(episode['events']) if event['kind']=='result'),{})
        if result.get('status')!='completed' or (physical and result.get('physical_success') is not True):
            continue
        latest=None; corrected=False; blocked=False; segment_start=len(rows)
        for event in episode['events']:
            if event['kind']=='observation' and 'observations' in event['data']:
                latest=event
            elif event['kind']=='intervention':
                corrected=True; blocked=False; segment_start=len(rows)
            elif event['kind']=='failure':
                # A later human correction cannot turn the failed segment into ground truth.
                del rows[segment_start:]
                blocked=True
            elif event['kind']=='action' and event['data'].get('op')=='move_joints':
                if blocked:
                    continue
                if latest is None:
                    raise ValueError('A synchronized camera/joint observation is required')
                observations=latest['data']['observations']
                robot_state=latest['data'].get('robot_state',{})
                if robot_state.get('sdk_calibration_id')!=policy.calibration_id:
                    raise ValueError('Recorded SDK calibration differs from the policy binding')
                joint=next((item for item in observations if item.get('kind')=='joint'),None)
                cameras={item['source_id']:item for item in observations if item.get('kind')=='rgb'}
                if not joint or set(policy.camera_features.values())-set(cameras):
                    raise ValueError('The recorded episode does not contain every required camera/joint feature')
                selected=[joint]+[cameras[source] for source in policy.camera_features.values()]
                if physical and (any(item.get('provenance')!='measured' or not item.get('driver_id') or item.get('stale') is True or item.get('age_s',math.inf)>2 for item in selected)
                                 or event['timestamp']-latest['timestamp']>2):
                    raise ValueError('Physical demonstrations require fresh measured observations')
                values=event['data']['joints']
                if not isinstance(values,list) or len(values)!=6 or [item.get('servo') for item in values]!=list(range(6)):
                    raise ValueError('Demonstration joint order mismatch')
                native={f'{name}.pos':item['angle'] for name,item in zip(SO101_JOINTS,values)}
                named_action_plan(native,policy,duration_ms=event['data']['duration_ms'])
                rows.append({'episode_id':episode['episode_id'],
                             'split':'eval' if episode['episode_id'] in eval_episode_ids else 'train',
                             'provenance':'measured_episode' if physical else 'simulated_episode',
                             'human_corrected':corrected,'instruction':episode['task'],
                             'state':joint['data']['angles'],
                             'frames':{key:copy_frame(cameras[source]['data']) for key,source in policy.camera_features.items()},
                             'actions':[[float(native[f'{name}.pos']) for name in SO101_JOINTS] for _ in range(chunk_size)]})
    if not rows:
        raise ValueError('No completed synchronized demonstrations were found')
    return rows


def copy_frame(frame: dict) -> dict:
    return {'frame_id':frame['frame_id'],'width':frame['width'],'height':frame['height'],'rgb':list(frame['rgb'])}


def serve_sdk(port: str,robot_id: str) -> None:
    """Explicit device worker. STOP publishes cancellation without waiting for normal commands."""
    from .drivers.lerobot import SO101Driver
    from importlib.metadata import version
    if version('lerobot')!='0.6.1':
        raise ValueError('LeRobot 0.6.1 is required')
    protocol_stdout=sys.stdout
    output_lock=threading.Lock()
    def output(value: dict) -> None:
        with output_lock:
            print(json.dumps(value,allow_nan=False),file=protocol_stdout,flush=True)
    driver=SO101Driver(port,robot_id,calibration_dir=_WORK_ROOT/'calibration',sink=output)
    commands=queue.Queue(maxsize=16)
    def consume() -> None:
        while True:
            value=commands.get()
            if value is None:
                return
            with contextlib.redirect_stdout(sys.stderr):
                driver.send(value)
    consumer=threading.Thread(target=consume,daemon=True,name='so101-commands'); consumer.start()
    output({'ready':True,'sdk':'lerobot-0.6.1','connected':False,'hardware_actuated':False})
    try:
        for line in sys.stdin:
            try:
                if len(line)>65536:
                    raise ValueError('SDK command too large')
                payload=json.loads(line)
                if not isinstance(payload,dict):
                    raise ValueError('Invalid SDK command')
                if payload.get('op')=='stop':
                    # Drop queued old-session work before the immediate cancellation path.
                    while True:
                        try:
                            commands.get_nowait()
                        except queue.Empty:
                            break
                    driver.send(payload)
                else:
                    commands.put_nowait(payload)
            except Exception:
                output({'v':1,'status':'ERROR','error':'sdk_command_rejected','armed':driver.armed})
    finally:
        driver.close()


def main(argv: list[str] | None = None) -> int:
    global _WORK_ROOT
    parser=argparse.ArgumentParser(description='Isolated, local-only learned robotics policy worker')
    parser.add_argument('command',choices=['smoke','serve','serve-sdk','train','eval','fixture','prepare-episodes','activate','sdk-info','sdk-calibrate'])
    parser.add_argument('--checkpoint',default=BASE_CHECKPOINT)
    parser.add_argument('--revision',default=BASE_REVISION)
    parser.add_argument('--device',choices=['cpu','cuda'],default='cpu')
    parser.add_argument('--output')
    parser.add_argument('--work-root',default='/work')
    parser.add_argument('--warmup',action='store_true')
    parser.add_argument('--samples',type=int,default=3)
    parser.add_argument('--dataset')
    parser.add_argument('--steps',type=int,default=2)
    parser.add_argument('--port')
    parser.add_argument('--robot-id',default='ccoli-so101')
    parser.add_argument('--manifest')
    parser.add_argument('--eval-episodes',default='')
    args=parser.parse_args(argv)
    _WORK_ROOT=Path(args.work_root).resolve()
    args.output=args.output or str(_WORK_ROOT/'smoke.json')
    if not 1<=args.samples<=100:
        parser.error('Choose between one and one hundred synthetic samples')
    os.environ['WANDB_MODE']='disabled'
    os.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN']='1'
    os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
    if args.command=='serve-sdk':
        if not args.port:
            parser.error('An explicitly selected SO101 port is required')
        serve_sdk(args.port,args.robot_id)
        return 0
    if args.command=='prepare-episodes':
        if not args.dataset or not args.manifest:
            parser.error('An explicit local episode directory and policy manifest are required')
        directory=_local_path(args.dataset)
        episode_paths=sorted(directory.glob('*.json'))
        episodes=[]
        for path in episode_paths:
            path=_local_path(path)
            if path.stat().st_size>128_000_000:
                parser.error('Episode too large')
            episodes.append(json.loads(path.read_text()))
        manifest=json.loads(_local_path(args.manifest).read_text())
        prepared=rows_from_episodes(episodes,manifest,eval_episode_ids=set(filter(None,args.eval_episodes.split(','))))
        _write_json(args.output,{'schema_version':1,'rows':prepared,'uploaded':False})
        print(json.dumps({'samples':len(prepared),'uploaded':False})); return 0
    if args.command=='sdk-info':
        from lerobot.robots.so_follower import SO101Follower,SO101FollowerConfig
        from .drivers.lerobot import discover_ports
        robot=SO101Follower(SO101FollowerConfig(port='/dev/not-connected',id='offline-poc',use_degrees=True))
        value={'sdk':'lerobot-0.6.1','joint_order':list(robot.bus.motors),
               'joint_units':list(SO101_UNITS),'connected':robot.is_connected,
               'candidates':discover_ports(),'hardware_actuated':False}
        _write_json(args.output,value); print(json.dumps(value)); return 0
    if args.command=='sdk-calibrate':
        if not args.port or not sys.stdin.isatty():
            parser.error('Explicit port and an interactive human calibration session are required')
        from .drivers.lerobot import SO101Driver
        driver=SO101Driver(args.port,args.robot_id,calibration_dir=_WORK_ROOT/'calibration')
        try:
            driver.connect(); print(json.dumps(driver.calibrate_sdk()))
        finally:
            driver.close()
        return 0
    if args.command=='activate':
        if args.checkpoint.startswith('local:'):
            target=_local_path(_WORK_ROOT/args.checkpoint.removeprefix('local:'))
            digest=hashlib.sha256((target/'model.safetensors').read_bytes()).hexdigest()
        elif args.checkpoint==BASE_CHECKPOINT and args.revision==BASE_REVISION:
            from huggingface_hub import snapshot_download
            snapshot_download(BASE_CHECKPOINT,revision=BASE_REVISION,token=False,local_files_only=True,
                              allow_patterns=['config.json','model.safetensors'])
            digest=BASE_REVISION
        else:
            parser.error('Select a verified local checkpoint or the pinned public baseline')
        if digest!=args.revision:
            parser.error('Checkpoint digest mismatch')
        previous=_WORK_ROOT/'active-checkpoint.json'
        old=json.loads(previous.read_text()) if previous.exists() else None
        if isinstance(old,dict):
            old={key:old[key] for key in ('checkpoint','revision') if key in old}
        _write_json(previous,{'checkpoint':args.checkpoint,'revision':digest,'previous':old,
                              'physical_motion_enabled':False})
        print(json.dumps({'selected':args.checkpoint,'physical_motion_enabled':False})); return 0
    with contextlib.redirect_stdout(sys.stderr):
        worker=SmolVLAWorker(args.checkpoint,args.revision,args.device)
    rows=fixture(worker.camera_features,chunk_size=worker.policy.config.chunk_size)
    warmup=None
    if args.warmup or (args.command=='serve' and args.device=='cuda'):
        with contextlib.redirect_stdout(sys.stderr):
            warmup=worker.warmup()
    if args.command=='fixture':
        _write_json(args.output,{'schema_version':1,'rows':rows,'provenance':'synthetic_fixture'})
        return 0
    if args.command=='serve':
        print(json.dumps({'ready':True,'revision':worker.revision,'warmup':warmup,'hardware_actuated':False}),flush=True)
        for line in sys.stdin:
            try:
                if len(line)>12_000_000:
                    raise ValueError('Request too large')
                request=json.loads(line)
                with contextlib.redirect_stdout(sys.stderr):
                    result=worker.infer(request)
                print(json.dumps(result,allow_nan=False),flush=True)
            except Exception as exc:
                print(json.dumps({'error':type(exc).__name__,'hardware_actuated':False}),flush=True)
        return 0
    if args.dataset:
        data=json.loads(_local_path(args.dataset).read_text())
        if data.get('schema_version')!=1 or not isinstance(data.get('rows'),list):
            parser.error('Invalid local demonstration dataset')
        rows=data['rows']
    if args.command=='smoke':
        measurements=[]
        for index in range(args.samples):
            measurements.append(worker.infer(rows[index%len(rows)]))
        from importlib.metadata import version
        report={'checkpoint':worker.checkpoint,'revision':worker.revision,'backbone_revision':BACKBONE_REVISION,
                'versions':{name:version(name) for name in ('lerobot','torch','transformers')},
                'device':str(worker.device),'gpu_name':worker.torch.cuda.get_device_name(0) if worker.device.type=='cuda' else None,
                'warmup':warmup,
                'parameters':sum(parameter.numel() for parameter in worker.policy.parameters()),
                'camera_features':list(worker.camera_features),'samples':measurements,
                'provenance':'synthetic_rgb_state_learned_checkpoint', 'physical_success_verified':False,
                'hardware_actuated':False,'uploaded':False}
    elif args.command=='train':
        report=worker.train(rows,args.output,args.steps)
        print(json.dumps(report,allow_nan=False)); return 0
    else:
        report=worker.evaluate([row for row in rows if row.get('split')=='eval'])
    _write_json(args.output,report)
    print(json.dumps(report,allow_nan=False))
    return 0
