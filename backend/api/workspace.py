from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from ui.utils.project_store import project_dir_path

router = APIRouter()


def _safe_resolve(project_id: str, rel: str) -> Path:
    base = project_dir_path(project_id).resolve()
    target = (base / rel).resolve() if rel else base
    try:
        target.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=400, detail="Path escapes project root")
    return target


def _tree(root: Path, depth: int = 3) -> List[Dict[str, Any]]:
    if depth < 0 or not root.exists():
        return []
    items: List[Dict[str, Any]] = []
    try:
        entries = sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except (PermissionError, OSError):
        return []
    for p in entries:
        if p.name.startswith("."):
            continue
        node: Dict[str, Any] = {
            "name": p.name,
            "type": "dir" if p.is_dir() else "file",
            "path": str(p.relative_to(root.parents[0])).replace("\\", "/") if root.parent else p.name,
        }
        if p.is_dir():
            node["children"] = _tree(p, depth - 1)
        else:
            try:
                node["size"] = p.stat().st_size
            except OSError:
                node["size"] = 0
        items.append(node)
    return items


@router.get("/{project_id}/tree")
def get_tree(project_id: str) -> Dict[str, Any]:
    base = project_dir_path(project_id)
    if not base.exists():
        raise HTTPException(status_code=404, detail="Project workspace not found")
    return {"root": base.name, "children": _tree(base, depth=3)}
