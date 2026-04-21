from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter
from pydantic import BaseModel

from ui.utils.llm_config import (
    configured_model_options,
    default_llm_profiles,
    normalize_llm_profiles,
    parse_selected_model,
    test_connectivity,
)

router = APIRouter()


class TestConnectivityRequest(BaseModel):
    provider: str
    api_key: str
    api_base: str = ""
    model_name: str


class NormalizeRequest(BaseModel):
    profiles: Dict[str, Dict[str, Any]]


@router.get("/defaults")
def get_defaults() -> Dict[str, Any]:
    return {"profiles": default_llm_profiles()}


@router.post("/test")
def test_connection(body: TestConnectivityRequest) -> Dict[str, Any]:
    ok, models, error = test_connectivity(
        body.provider, body.api_key, body.api_base, body.model_name
    )
    return {"ok": ok, "models": models, "error": error}


@router.post("/normalize")
def normalize(body: NormalizeRequest) -> Dict[str, Any]:
    return {"profiles": normalize_llm_profiles(body.profiles)}


@router.post("/options")
def options(body: NormalizeRequest) -> Dict[str, Any]:
    opts = configured_model_options(body.profiles)
    return {"options": [{"key": k, "label": v} for k, v in opts]}


class ParseModelRequest(BaseModel):
    key: str


@router.post("/parse")
def parse(body: ParseModelRequest) -> Dict[str, Any]:
    provider, model = parse_selected_model(body.key)
    return {"provider": provider, "model": model}
