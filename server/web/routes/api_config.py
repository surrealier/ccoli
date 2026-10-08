from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from config_loader import get_config
from ..app import get_agent
from ..auth import require_auth

router = APIRouter(prefix="/api/config", dependencies=[Depends(require_auth)])

_REDACT_KEYS = {
    "openai_api_key", "anthropic_api_key", "gemini_api_key",
    "api_key", "auth_token", "bot_token", "client_secret", "refresh_token",
    "pass", "password", "secret",
}


def _redact(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if k in _REDACT_KEYS:
            out[k] = "***" if v else ""
        elif isinstance(v, dict):
            out[k] = _redact(v)
        else:
            out[k] = v
    return out


@router.get("/")
def read_config():
    cfg = get_config()
    return _redact(cfg.config)


class ConfigPatch(BaseModel):
    section: str
    key: str
    value: Any


@router.patch("/")
def patch_config(body: ConfigPatch):
    cfg = get_config()
    section = cfg.config.get(body.section)
    if not isinstance(section, dict):
        raise HTTPException(status_code=404, detail=f"Unknown config section: {body.section}")
    section[body.key] = body.value
    cfg.save()
    try:
        agent = get_agent()
        runtime_controller = getattr(agent, "runtime_controller", None)
        if runtime_controller is not None:
            runtime_controller.refresh_from_config(save=False)
    except Exception:
        pass
    return {"ok": True}
