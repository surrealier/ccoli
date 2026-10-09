"""Authenticated physical setup controls; user JSON is never sensor measurement."""
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt
from src.robotics.models import RoboticsError
from src.robotics.profiles import public_profiles
from ..app import get_agent
from ..auth import require_auth

router = APIRouter(prefix='/api/robotics', dependencies=[Depends(require_auth)])


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Source(Input):
    source: Literal['atom','sim']


class Profile(Input):
    profile_id: Annotated[str, Field(min_length=1,max_length=48)]


class Calibration(Input):
    channels: Annotated[list[dict], Field(min_length=1,max_length=8)]
    wiring_confirmed: Literal[True]


class Arm(Input):
    confirmed: StrictBool


class Move(Input):
    servo: Annotated[StrictInt, Field(ge=0,le=7)]
    angle: Annotated[float, Field(strict=True,allow_inf_nan=False,ge=-180,le=180)]
    duration_ms: Annotated[StrictInt, Field(ge=1,le=5000)] = 1000


class Gesture(Input):
    gesture_id: Annotated[str, Field(min_length=1,max_length=48)]
    intensity: Annotated[float, Field(strict=True,allow_inf_nan=False,ge=0,le=1)] = .3


class Stop(Input):
    mode: Literal['detach','hold'] = 'detach'


class Task(Input):
    skill: Literal['button_press','camera_scan','notification','sensor_actuation','object_tidy']
    params: dict
    confirmed: StrictBool


class Observation(Input):
    kind: Literal['rgb','joint','sensor','objects']
    source_id: Annotated[str, Field(min_length=1,max_length=48)]
    data: dict
    sequence: Annotated[StrictInt, Field(ge=1,le=0xffffffff)]


class Recording(Input):
    enabled: StrictBool


class Fault(Input):
    fault: Literal['drop','error','freeze','disconnect'] | None = None


def runtime():
    value = getattr(get_agent(), 'robotics_runtime', None)
    if value is None:
        raise HTTPException(503, 'Restart the server to enable device setup')
    return value


def call(operation, *args, **kwargs):
    try:
        return operation(*args, **kwargs)
    except RoboticsError as error:
        status = 422 if error.code == 'explicit_authorization_required' else 409
        raise HTTPException(status, {'code':error.code,'message':'Check device setup and try again'}) from None
    except Exception:
        raise HTTPException(503, 'Device action failed. Check the connection and try again') from None


@router.get('/status')
def status():
    return runtime().snapshot()


@router.get('/profiles')
def profiles():
    return {'profiles':public_profiles()}


@router.post('/source')
def source(body: Source):
    return call(runtime().select_source, body.source)


@router.post('/discover')
def discover():
    return call(runtime().discover)


@router.post('/configure')
def profile(body: Profile):
    return call(runtime().configure, body.profile_id)


@router.post('/calibrate')
def calibrate(body: Calibration):
    return call(runtime().calibrate, body.channels, wiring_confirmed=body.wiring_confirmed)


@router.post('/arm')
def arm(body: Arm):
    return call(runtime().arm, confirmed=body.confirmed)


@router.post('/move')
def move(body: Move):
    return call(runtime().move, body.servo, body.angle, body.duration_ms)


@router.post('/gesture')
def gesture(body: Gesture):
    return call(runtime().gesture, body.gesture_id, body.intensity)


@router.post('/stop')
def stop():
    # Empty body and a direct stop button; no planner or model invocation.
    return runtime().stop()


@router.post('/tasks')
def task(body: Task):
    return call(runtime().start_task, body.skill, body.params, confirmed=body.confirmed)


@router.post('/recording')
def recording(body: Recording):
    return call(runtime().set_recording, body.enabled)


@router.post('/sim/observation')
def observation(body: Observation):
    return call(runtime().simulated_observation, body.kind, body.source_id, body.data, body.sequence)


@router.post('/sim/fault')
def fault(body: Fault):
    call(runtime().inject_fault, body.fault)
    return {'ok':True}
