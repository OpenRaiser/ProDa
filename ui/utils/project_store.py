from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from ui.utils.llm_config import default_llm_profiles


ROOT_DIR = Path(__file__).resolve().parent.parent.parent
PROJECTS_DIR = ROOT_DIR / ".proda_projects"
INDEX_PATH = PROJECTS_DIR / "index.json"


def _ensure_dirs() -> None:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)


def _load_json(path: Path, default: Any):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _default_index() -> Dict[str, Any]:
    return {"projects": [], "updated_at": "", "last_opened_project_id": ""}


def load_index() -> Dict[str, Any]:
    _ensure_dirs()
    return _load_json(INDEX_PATH, _default_index())


def save_index(index_data: Dict[str, Any]) -> None:
    _ensure_dirs()
    index_data["updated_at"] = datetime.utcnow().isoformat()
    _save_json(INDEX_PATH, index_data)


def list_projects() -> List[Dict[str, Any]]:
    projects = load_index().get("projects", [])
    return sorted(
        projects,
        key=lambda x: str(x.get("updated_at", "") or x.get("created_at", "")),
        reverse=True,
    )


def get_project(project_id: str) -> Optional[Dict[str, Any]]:
    for p in list_projects():
        if p.get("id") == project_id:
            return p
    return None


def create_project(name: str, description: str = "") -> Dict[str, Any]:
    index_data = load_index()
    project_id = uuid4().hex[:12]
    now = datetime.utcnow().isoformat()
    project = {
        "id": project_id,
        "name": name.strip(),
        "description": description.strip(),
        "created_at": now,
        "updated_at": now,
    }
    index_data["projects"].append(project)
    index_data["last_opened_project_id"] = project_id
    save_index(index_data)

    project_dir = project_dir_path(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)
    save_project_state(project_id, _default_project_state())
    return project


def rename_project(project_id: str, new_name: str, new_description: str = "") -> bool:
    index_data = load_index()
    found = False
    for p in index_data.get("projects", []):
        if p.get("id") == project_id:
            p["name"] = new_name.strip()
            p["description"] = new_description.strip()
            p["updated_at"] = datetime.utcnow().isoformat()
            found = True
            break
    if not found:
        return False
    save_index(index_data)
    return True


def delete_project(project_id: str) -> bool:
    index_data = load_index()
    before = len(index_data.get("projects", []))
    index_data["projects"] = [p for p in index_data.get("projects", []) if p.get("id") != project_id]
    after = len(index_data["projects"])
    if before == after:
        return False
    if index_data.get("last_opened_project_id") == project_id:
        index_data["last_opened_project_id"] = ""
    save_index(index_data)
    project_dir = project_dir_path(project_id)
    if project_dir.exists():
        shutil.rmtree(project_dir, ignore_errors=True)
    return True


def mark_project_opened(project_id: str) -> None:
    index_data = load_index()
    for p in index_data.get("projects", []):
        if p.get("id") == project_id:
            p["updated_at"] = datetime.utcnow().isoformat()
            break
    index_data["last_opened_project_id"] = project_id
    save_index(index_data)


def project_dir_path(project_id: str) -> Path:
    return PROJECTS_DIR / project_id


def project_state_path(project_id: str) -> Path:
    return project_dir_path(project_id) / "state.json"


def _default_project_state() -> Dict[str, Any]:
    return {
        "llm_profiles": default_llm_profiles(),
        "selected_model": "",
        "knowledge_core": None,
        "benchmark_mcq": [],
        "finetune_data": [],
        "json_fields": [],
    }


def load_project_state(project_id: str) -> Dict[str, Any]:
    path = project_state_path(project_id)
    state = _load_json(path, _default_project_state())
    merged = _default_project_state()
    merged.update(state if isinstance(state, dict) else {})
    return merged


def save_project_state(project_id: str, state: Dict[str, Any]) -> None:
    project_dir = project_dir_path(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)
    _save_json(project_state_path(project_id), state)

    index_data = load_index()
    for p in index_data.get("projects", []):
        if p.get("id") == project_id:
            p["updated_at"] = datetime.utcnow().isoformat()
    index_data["last_opened_project_id"] = project_id
    save_index(index_data)

