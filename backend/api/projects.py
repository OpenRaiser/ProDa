from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ui.utils.project_store import (
    create_project as _create_project,
    delete_project as _delete_project,
    get_project as _get_project,
    list_projects as _list_projects,
    load_index as _load_index,
    load_project_state as _load_state,
    mark_project_opened as _mark_opened,
    rename_project as _rename_project,
    save_project_state as _save_state,
)

router = APIRouter()


class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""


class ProjectUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""


class ProjectStateUpdateRequest(BaseModel):
    state: Dict[str, Any]


@router.get("")
def list_projects() -> Dict[str, Any]:
    idx = _load_index()
    return {
        "projects": _list_projects(),
        "last_opened_project_id": idx.get("last_opened_project_id", ""),
    }


@router.post("")
def create_project(body: ProjectCreateRequest) -> Dict[str, Any]:
    project = _create_project(body.name, body.description)
    return project


@router.get("/{project_id}")
def get_project(project_id: str) -> Dict[str, Any]:
    project = _get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    state = _load_state(project_id)
    return {"project": project, "state": state}


@router.put("/{project_id}")
def rename_project(project_id: str, body: ProjectUpdateRequest) -> Dict[str, Any]:
    ok = _rename_project(project_id, body.name, body.description)
    if not ok:
        raise HTTPException(status_code=404, detail="Project not found")
    return _get_project(project_id) or {}


@router.delete("/{project_id}")
def delete_project(project_id: str) -> Dict[str, Any]:
    ok = _delete_project(project_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"deleted": True, "project_id": project_id}


@router.post("/{project_id}/open")
def open_project(project_id: str) -> Dict[str, Any]:
    project = _get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    _mark_opened(project_id)
    state = _load_state(project_id)
    return {"project": project, "state": state}


@router.put("/{project_id}/state")
def update_project_state(project_id: str, body: ProjectStateUpdateRequest) -> Dict[str, Any]:
    project = _get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    _save_state(project_id, body.state)
    return {"saved": True}


class KnowledgeCoreUpdateRequest(BaseModel):
    knowledge_core: Optional[Dict[str, Any]] = None


@router.get("/{project_id}/knowledge-core")
def get_knowledge_core(project_id: str) -> Dict[str, Any]:
    project = _get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    state = _load_state(project_id)
    return {"knowledge_core": state.get("knowledge_core")}


@router.put("/{project_id}/knowledge-core")
def update_knowledge_core(
    project_id: str, body: KnowledgeCoreUpdateRequest
) -> Dict[str, Any]:
    project = _get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    state = _load_state(project_id)
    state["knowledge_core"] = body.knowledge_core
    _save_state(project_id, state)
    return {"saved": True}


@router.put("/{project_id}/json-fields")
def update_json_fields(
    project_id: str, body: Dict[str, List[str]]
) -> Dict[str, Any]:
    project = _get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    state = _load_state(project_id)
    state["json_fields"] = body.get("json_fields", [])
    _save_state(project_id, state)
    return {"saved": True}


class BenchmarkUpdateRequest(BaseModel):
    benchmark_mcq: List[Dict[str, Any]]


@router.get("/{project_id}/benchmark")
def get_benchmark(project_id: str) -> Dict[str, Any]:
    project = _get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    state = _load_state(project_id)
    return {"benchmark_mcq": state.get("benchmark_mcq", [])}


@router.put("/{project_id}/benchmark")
def update_benchmark(
    project_id: str, body: BenchmarkUpdateRequest
) -> Dict[str, Any]:
    project = _get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    state = _load_state(project_id)
    state["benchmark_mcq"] = body.benchmark_mcq
    _save_state(project_id, state)
    return {"saved": True, "count": len(body.benchmark_mcq)}


class FineTuneUpdateRequest(BaseModel):
    finetune_data: List[Dict[str, Any]]


@router.get("/{project_id}/finetune")
def get_finetune(project_id: str) -> Dict[str, Any]:
    project = _get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    state = _load_state(project_id)
    return {"finetune_data": state.get("finetune_data", [])}


@router.put("/{project_id}/finetune")
def update_finetune(
    project_id: str, body: FineTuneUpdateRequest
) -> Dict[str, Any]:
    project = _get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    state = _load_state(project_id)
    state["finetune_data"] = body.finetune_data
    _save_state(project_id, state)
    return {"saved": True, "count": len(body.finetune_data)}
