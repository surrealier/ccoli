"""Authenticated setup routes with bounded JSON and token-safe errors."""
from __future__ import annotations

import json
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from src.integrations.home_assistant_setup import HomeAssistantSetupService, HomeSetupError
from ..app import get_agent
from ..auth import require_auth

router = APIRouter(prefix="/api/home-setup", dependencies=[Depends(require_auth)])
MAX_BODY = 16 * 1024


def _service() -> HomeAssistantSetupService:
    service = getattr(get_agent(), "home_setup_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail={"code": "setup_unavailable", "message": "홈 설정 서비스를 다시 시작해 주세요."})
    return service


def _invalid(status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": "invalid_request", "message": "주소·토큰·기기 선택 입력을 확인해 주세요."})


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate key")
        value[key] = item
    return value


def _constant(_: str) -> None:
    raise ValueError("nonfinite number")


async def _body(request: Request, allowed: set[str], required: set[str]) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if content_type != "application/json":
        raise _invalid()
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_BODY:
            raise _invalid(413)
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
        if not isinstance(value, dict) or not required <= set(value) or not set(value) <= allowed:
            raise ValueError("schema")
        if "base_url" in value and (not isinstance(value["base_url"], str) or len(value["base_url"]) > 2048):
            raise ValueError("url type")
        if "token" in value and value["token"] is not None and (not isinstance(value["token"], str) or len(value["token"]) > 4096):
            raise ValueError("token type")
        if "allowed_entities" in value and (not isinstance(value["allowed_entities"], list)
                or len(value["allowed_entities"]) > 256
                or any(not isinstance(item, str) or len(item) > 255 for item in value["allowed_entities"])):
            raise ValueError("selection type")
        return value
    except (ValueError, UnicodeError, RecursionError, TypeError):
        raise _invalid() from None


async def _call(function: Callable[..., dict[str, Any]], *args: Any) -> dict[str, Any]:
    try:
        return await run_in_threadpool(function, *args)
    except HomeSetupError as error:
        status_code = 409 if error.code in {"operation_superseded", "verification_required"} else 400
        if error.code in {"storage_failed", "activation_failed"}:
            status_code = 503
        raise HTTPException(status_code=status_code, detail={"code": error.code, "message": error.message}) from None


@router.get("/status")
@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
def status() -> dict[str, Any]:
    return _service().status()


@router.post("/connect")
async def connect(request: Request) -> dict[str, Any]:
    value = await _body(request, {"base_url", "token"}, {"base_url"})
    return await _call(_service().connect, value["base_url"], value.get("token"))


@router.post("/selection")
async def selection(request: Request) -> dict[str, Any]:
    value = await _body(request, {"allowed_entities"}, {"allowed_entities"})
    return await _call(_service().select, value["allowed_entities"])


@router.post("/disconnect")
async def disconnect(request: Request) -> dict[str, Any]:
    await _body(request, set(), set())
    return await _call(_service().disconnect)