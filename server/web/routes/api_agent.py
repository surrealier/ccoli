"""Capability and execution metadata, without personal tool arguments."""
from fastapi import APIRouter, Depends
from ..app import get_agent
from ..auth import require_auth

router = APIRouter(prefix="/api/agent", dependencies=[Depends(require_auth)])


@router.get("/")
def agent_status():
    engine = getattr(get_agent(), "tool_agent", None)
    return {
        "enabled": engine is not None,
        "tools": engine.catalog() if engine else [],
        "recent_runs": engine.recent_runs() if engine else [],
    }