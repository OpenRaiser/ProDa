"""Phase 7 — Workspace Results (dashboard + artifacts browsing + export bundle)."""

from __future__ import annotations

import io
import json
import mimetypes
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ui.utils.project_store import (
    get_project as _get_project,
    load_project_state as _load_state,
    project_dir_path as _project_dir,
)

router = APIRouter()

MAX_ARTIFACT_TEXT_BYTES = 2 * 1024 * 1024  # 2MB
MAX_TREE_DEPTH = 5
TEXT_SUFFIXES = {
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".py",
    ".txt",
    ".log",
    ".md",
    ".csv",
    ".cfg",
    ".ini",
    ".env",
}
# Anything bigger than this is shown only by metadata; don't even try to read.
MAX_READ_SIZE_ABSOLUTE = 20 * 1024 * 1024


# ---------- helpers ----------

def _assert_project(project_id: str) -> Dict[str, Any]:
    project = _get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _is_within(path: Path, root: Path) -> bool:
    try:
        p = path.resolve()
        r = root.resolve()
        return p == r or r in p.parents
    except Exception:
        return False


def _summarize_kc(kc: Any) -> Dict[str, int]:
    if not isinstance(kc, dict):
        return {"l1": 0, "l2": 0, "l3": 0}
    return {
        "l1": len(kc.get("l1_concepts") or []),
        "l2": len(kc.get("l2_statements") or []),
        "l3": len(kc.get("l3_chains") or []),
    }


def _summarize_benchmark(rows: Any) -> Dict[str, Any]:
    if not isinstance(rows, list):
        return {"count": 0, "by_type": {}}
    by_type: Dict[str, int] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        q = str(r.get("question_type", "single_choice")).lower() or "single_choice"
        by_type[q] = by_type.get(q, 0) + 1
    return {"count": len(rows), "by_type": by_type}


def _summarize_finetune(rows: Any) -> Dict[str, Any]:
    if not isinstance(rows, list):
        return {"count": 0, "by_type": {}}
    counts = {"qa": 0, "choice": 0, "tf": 0, "other": 0}
    for r in rows:
        if not isinstance(r, dict):
            continue
        q = str(r.get("question_type", "")).lower()
        if q == "qa":
            counts["qa"] += 1
        elif q in {"single_choice", "multiple_choice"}:
            counts["choice"] += 1
        elif q == "true_false":
            counts["tf"] += 1
        else:
            counts["other"] += 1
    return {"count": len(rows), "by_type": counts}


def _summarize_training(project_dir: Path) -> Dict[str, Any]:
    hist = _load_json(project_dir / "finetune_exports" / "train_history.json", [])
    if not isinstance(hist, list):
        hist = []
    statuses = {"finished": 0, "stopped_or_failed": 0, "running": 0}
    for row in hist:
        if not isinstance(row, dict):
            continue
        s = str(row.get("status", "running"))
        statuses[s] = statuses.get(s, 0) + 1
    flow = _load_json(project_dir / "workflow" / "second_round_flow.json", {})
    latest_model_dir = ""
    if isinstance(flow, dict):
        latest_model_dir = str(flow.get("last_trained_model_dir", "") or "")
    return {
        "total": len(hist),
        "finished": statuses.get("finished", 0),
        "failed": statuses.get("stopped_or_failed", 0),
        "running": statuses.get("running", 0),
        "latest_model_dir": latest_model_dir,
    }


def _summarize_evaluation(project_dir: Path) -> Dict[str, Any]:
    hist = _load_json(project_dir / "evaluations" / "opencompass" / "history.json", [])
    if not isinstance(hist, list):
        hist = []
    statuses = {"finished": 0, "stopped_or_failed": 0, "running": 0}
    best_acc: Optional[float] = None
    best_model: Optional[str] = None
    for row in hist:
        if not isinstance(row, dict):
            continue
        s = str(row.get("status", "running"))
        statuses[s] = statuses.get(s, 0) + 1
        result_file = Path(str(row.get("result_file", "")))
        if not _is_within(result_file, project_dir) or not result_file.exists():
            continue
        payload = _load_json(result_file, {})
        if not isinstance(payload, dict):
            continue
        viz = payload.get("viz") or {}
        lb = viz.get("leaderboard") or []
        for item in lb:
            if not isinstance(item, dict):
                continue
            try:
                acc = float(item.get("accuracy", 0.0))
            except Exception:
                continue
            if best_acc is None or acc > best_acc:
                best_acc = acc
                best_model = str(item.get("model", ""))
    return {
        "total": len(hist),
        "finished": statuses.get("finished", 0),
        "failed": statuses.get("stopped_or_failed", 0),
        "running": statuses.get("running", 0),
        "best_accuracy": best_acc,
        "best_model": best_model,
    }


def _read_flow(project_dir: Path) -> Dict[str, Any]:
    flow = _load_json(project_dir / "workflow" / "second_round_flow.json", {})
    return flow if isinstance(flow, dict) else {}


# ---------- Timeline ----------

def _ts_epoch(value: Any) -> int:
    """Coerce mixed timestamp fields to integer unix epoch seconds."""
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip()
    if not s:
        return 0
    if s.isdigit():
        return int(s)
    try:
        return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
    except Exception:
        return 0


def _timeline_events(project_dir: Path) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []

    # Training sessions
    train_hist = _load_json(project_dir / "finetune_exports" / "train_history.json", [])
    if isinstance(train_hist, list):
        for row in train_hist:
            if not isinstance(row, dict):
                continue
            events.append(
                {
                    "id": f"train::{row.get('session_id', '')}",
                    "kind": "train",
                    "title": f"train · {row.get('dataset_name', '?')} → {row.get('model_tag') or row.get('model_path', '?')}",
                    "status": str(row.get("status", "running")),
                    "timestamp": _ts_epoch(row.get("started_at")),
                    "target": {
                        "page": "fine_tuning",
                        "session_id": str(row.get("session_id", "")),
                    },
                    "metadata": {
                        "finetuning_type": row.get("finetuning_type", ""),
                        "epochs": row.get("epochs"),
                        "lr": row.get("learning_rate"),
                        "output_dir": row.get("output_dir", ""),
                    },
                }
            )

    # OpenCompass runs
    eval_hist = _load_json(project_dir / "evaluations" / "opencompass" / "history.json", [])
    if isinstance(eval_hist, list):
        for row in eval_hist:
            if not isinstance(row, dict):
                continue
            abbrs = row.get("models") or []
            abbr_text = ""
            if isinstance(abbrs, list):
                names = []
                for m in abbrs:
                    if isinstance(m, dict):
                        names.append(str(m.get("abbr", "")))
                    else:
                        names.append(str(m))
                abbr_text = ", ".join(x for x in names if x)
            events.append(
                {
                    "id": f"eval::{row.get('run_id', '')}",
                    "kind": "eval",
                    "title": f"eval · {abbr_text or '(?)'}",
                    "status": str(row.get("status", "running")),
                    "timestamp": _ts_epoch(row.get("started_at") or row.get("created_at")),
                    "target": {
                        "page": "opencompass",
                        "run_id": str(row.get("run_id", "")),
                    },
                    "metadata": {
                        "summary_file": row.get("summary_file", ""),
                    },
                }
            )

    # Diagnostic reports
    diag_hist = _load_json(project_dir / "diagnosis" / "history.json", [])
    if isinstance(diag_hist, list):
        for row in diag_hist:
            if not isinstance(row, dict):
                continue
            events.append(
                {
                    "id": f"diag::{row.get('report_id', '')}",
                    "kind": "diag",
                    "title": f"diag · {row.get('model_name', '?')} · acc={float(row.get('accuracy', 0)) * 100:.1f}%",
                    "status": "finished",
                    "timestamp": _ts_epoch(row.get("created_at")),
                    "target": {
                        "page": "finetune",
                        "finetune_section": "diagnose",
                        "report_id": str(row.get("report_id", "")),
                    },
                    "metadata": {
                        "run_id": row.get("run_id", ""),
                        "error_samples_count": row.get("error_samples_count", 0),
                    },
                }
            )

    # Supplement datasets
    sup_hist = _load_json(
        project_dir / "diagnosis" / "supplements" / "history.json", []
    )
    if isinstance(sup_hist, list):
        for row in sup_hist:
            if not isinstance(row, dict):
                continue
            events.append(
                {
                    "id": f"supplement::{row.get('dataset_id', '')}",
                    "kind": "supplement",
                    "title": f"supplement · {row.get('row_count', 0)} rows",
                    "status": "finished",
                    "timestamp": _ts_epoch(row.get("created_at")),
                    "target": {
                        "page": "finetune",
                        "finetune_section": "supplement",
                        "dataset_id": str(row.get("dataset_id", "")),
                    },
                    "metadata": {
                        "report_id": row.get("report_id", ""),
                    },
                }
            )

    # Merge event (single, from flow_state)
    flow = _read_flow(project_dir)
    if flow.get("merged_ready"):
        events.append(
            {
                "id": "merge::current",
                "kind": "merge",
                "title": f"merge · {flow.get('merged_rows', 0)} rows ready for round-2 SFT",
                "status": "finished",
                "timestamp": _ts_epoch(flow.get("merged_at")),
                "target": {
                    "page": "finetune",
                    "finetune_section": "merge",
                },
                "metadata": {
                    "merged_file": flow.get("merged_file", ""),
                    "source_dataset_id": flow.get("source_dataset_id", ""),
                },
            }
        )

    events.sort(key=lambda e: int(e.get("timestamp") or 0), reverse=True)
    return events


# ---------- Artifacts tree ----------

_SKIP_ROOTS = {
    ".git",
    "__pycache__",
    ".mypy_cache",
    "_preview",  # Phase 6 reuses this dir for in-flight preview configs (see opencompass.py)
    "_jsonl_cache",  # evaluator._json_to_jsonl intermediate cache
}
_SKIP_FILENAMES = {"active_train_job.json", "active_eval_job.json"}


def _classify_file(path: Path) -> Dict[str, Any]:
    suffix = path.suffix.lower()
    is_text = suffix in TEXT_SUFFIXES
    mime, _ = mimetypes.guess_type(str(path))
    try:
        size = path.stat().st_size
        mtime = int(path.stat().st_mtime)
    except Exception:
        size, mtime = 0, 0
    return {
        "name": path.name,
        "kind": "file",
        "size": size,
        "mtime": mtime,
        "suffix": suffix,
        "is_text": is_text,
        "mime": mime or "",
    }


def _build_tree(
    current: Path,
    project_dir: Path,
    depth: int = 0,
) -> Optional[Dict[str, Any]]:
    if depth > MAX_TREE_DEPTH:
        return None
    if current.name in _SKIP_ROOTS:
        return None
    relative = str(current.relative_to(project_dir)) if current != project_dir else ""
    if current.is_file():
        if current.name in _SKIP_FILENAMES:
            return None
        entry = _classify_file(current)
        entry["relative"] = relative
        return entry
    # Directory
    try:
        children_paths = sorted(
            current.iterdir(), key=lambda p: (p.is_file(), p.name.lower())
        )
    except Exception:
        children_paths = []
    children: List[Dict[str, Any]] = []
    total_size = 0
    file_count = 0
    for child in children_paths:
        node = _build_tree(child, project_dir, depth + 1)
        if node is None:
            continue
        if node["kind"] == "dir":
            total_size += int(node.get("size", 0) or 0)
            file_count += int(node.get("file_count", 0) or 0)
        else:
            total_size += int(node.get("size", 0) or 0)
            file_count += 1
        children.append(node)
    try:
        mtime = int(current.stat().st_mtime)
    except Exception:
        mtime = 0
    return {
        "name": current.name if current != project_dir else ".proda_projects/",
        "kind": "dir",
        "relative": relative,
        "size": total_size,
        "file_count": file_count,
        "mtime": mtime,
        "children": children,
    }


# ---------- Endpoints ----------

@router.get("/{project_id}/dashboard")
def get_dashboard(project_id: str) -> Dict[str, Any]:
    project = _assert_project(project_id)
    state = _load_state(project_id)
    project_dir = _project_dir(project_id)
    return {
        "project": project,
        "summary": {
            "kc": _summarize_kc(state.get("knowledge_core")),
            "benchmark": _summarize_benchmark(state.get("benchmark_mcq")),
            "finetune": _summarize_finetune(state.get("finetune_data")),
            "training": _summarize_training(project_dir),
            "evaluation": _summarize_evaluation(project_dir),
            "flow": _read_flow(project_dir),
        },
        "timeline": _timeline_events(project_dir),
        "artifacts": _build_tree(project_dir, project_dir, 0) or {
            "name": ".proda_projects/",
            "kind": "dir",
            "relative": "",
            "size": 0,
            "file_count": 0,
            "mtime": 0,
            "children": [],
        },
    }


@router.get("/{project_id}/artifact")
def get_artifact(project_id: str, path: str = Query(..., description="relative path within project dir")) -> Dict[str, Any]:
    _assert_project(project_id)
    project_dir = _project_dir(project_id)
    target = (project_dir / path).resolve()
    if not _is_within(target, project_dir):
        raise HTTPException(status_code=400, detail="path is outside project dir")
    if not target.exists():
        raise HTTPException(status_code=404, detail="artifact not found")
    if target.is_dir():
        raise HTTPException(status_code=400, detail="path is a directory")

    meta = _classify_file(target)
    meta["relative"] = str(target.relative_to(project_dir))

    if meta["size"] > MAX_READ_SIZE_ABSOLUTE:
        meta["text"] = None
        meta["reason"] = f"file size exceeds {MAX_READ_SIZE_ABSOLUTE} bytes; open externally"
        return meta

    if not meta["is_text"] or meta["size"] > MAX_ARTIFACT_TEXT_BYTES:
        meta["text"] = None
        meta["reason"] = "binary or too large for in-browser preview"
        return meta

    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        meta["text"] = None
        meta["reason"] = f"read failed: {exc}"
        return meta
    meta["text"] = text
    return meta


class ExportBundleRequest(BaseModel):
    paths: Optional[List[str]] = None  # relative paths within project; if None, bundle all


@router.post("/{project_id}/export-bundle")
def export_bundle(project_id: str, body: Optional[ExportBundleRequest] = None) -> StreamingResponse:
    _assert_project(project_id)
    project_dir = _project_dir(project_id)

    selected: List[Path] = []
    paths = (body.paths if body else None) or []
    if paths:
        for rel in paths:
            target = (project_dir / rel).resolve()
            if not _is_within(target, project_dir):
                continue
            if not target.exists() or not target.is_file():
                continue
            selected.append(target)
    else:
        for p in project_dir.rglob("*"):
            if not p.is_file():
                continue
            if p.name in _SKIP_FILENAMES:
                continue
            if any(part in _SKIP_ROOTS for part in p.parts):
                continue
            selected.append(p)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in selected:
            try:
                arcname = p.relative_to(project_dir).as_posix()
            except Exception:
                continue
            try:
                zf.write(p, arcname=arcname)
            except Exception:
                continue
    buffer.seek(0)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"pro-ide-export-{project_id}-{ts}.zip"

    def iterator():
        while True:
            chunk = buffer.read(64 * 1024)
            if not chunk:
                break
            yield chunk

    return StreamingResponse(
        iterator(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Bundle-Count": str(len(selected)),
        },
    )
