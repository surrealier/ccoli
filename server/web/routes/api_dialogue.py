"""Authenticated, immediately applied conversation preferences."""
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr
from config_loader import get_config
from ..app import get_agent
from ..auth import require_auth

router = APIRouter(prefix='/api/dialogue', dependencies=[Depends(require_auth)])


class DialoguePatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    language: Literal['auto','ko','en','zh','ja','es'] = 'auto'
    short_responses: StrictBool = True
    fast_model: Annotated[StrictStr, Field(max_length=96, pattern=r'^(?:[A-Za-z0-9][A-Za-z0-9_.:-]*)?$')] = ''


@router.get('/')
def get_preferences():
    agent = get_agent()
    if not hasattr(agent, 'describe_dialogue'):
        raise HTTPException(503, 'Restart the server to enable conversation settings')
    return agent.describe_dialogue()


@router.patch('/')
def update_preferences(body: DialoguePatch):
    runtime = getattr(get_agent(), 'runtime_controller', None)
    if runtime is None or not hasattr(runtime, 'update_dialogue'):
        raise HTTPException(503, 'Restart the server to enable conversation settings')
    try:
        settings = runtime.update_dialogue(body.model_dump(exclude_unset=True))
    except ValueError:
        raise HTTPException(422, 'Choose one of the supported conversation settings') from None
    except Exception:
        raise HTTPException(503, 'Settings were not saved. Check the server and try again') from None
    return {'ok': True, **settings}
