"""Phase 6 — OpenCompass evaluation REST + SSE endpoints."""

from __future__ import annotations

import asyncio
import json
import os
import platform
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.lib import llama_factory as lf  # for settings helpers
from backend.lib import opencompass as oc
from backend.lib import proc as _proc
from ui.utils.project_store import (
    get_project as _get_project,
    load_project_state as _load_state,
    project_dir_path as _project_dir,
    save_project_state as _save_state,
)

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_STALE_SESSION_MAX_AGE_S = 48 * 3600
_SAFE_TAG = re.compile(r"[^A-Za-z0-9_\-]+")

_PROJECT_LOCKS: Dict[str, threading.Lock] = {}
_PROJECT_LOCKS_GUARD = threading.Lock()


def _project_lock(project_id: str) -> threading.Lock:
    with _PROJECT_LOCKS_GUARD:
        lock = _PROJECT_LOCKS.get(project_id)
        if lock is None:
            lock = threading.Lock()
            _PROJECT_LOCKS[project_id] = lock
        return lock


def _sanitize_tag(value: str, fallback: str = "run") -> str:
    cleaned = _SAFE_TAG.sub("_", str(value or "").strip()).strip("_")
    return cleaned or fallback


# ---------- Path / file helpers ----------

def _assert_project(project_id: str) -> Dict[str, Any]:
    project = _get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _oc_root(project_id: str) -> Path:
    return _project_dir(project_id) / "evaluations" / "opencompass"


def _inputs_dir(project_id: str) -> Path:
    return _oc_root(project_id) / "inputs"


def _runs_dir(project_id: str) -> Path:
    return _oc_root(project_id) / "runs"


def _active_path(project_id: str) -> Path:
    return _oc_root(project_id) / "active_eval_job.json"


def _history_path(project_id: str) -> Path:
    return _oc_root(project_id) / "history.json"


def _flow_state_path(project_id: str) -> Path:
    return _project_dir(project_id) / "workflow" / "second_round_flow.json"


def _is_within(path: Path, root: Path) -> bool:
    try:
        p = path.resolve()
        r = root.resolve()
        return p == r or r in p.parents
    except Exception:
        return False


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_history(project_id: str) -> List[Dict[str, Any]]:
    data = _load_json(_history_path(project_id), [])
    return [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []


def _save_history(project_id: str, rows: List[Dict[str, Any]]) -> None:
    _save_json(_history_path(project_id), rows)


def _append_history(project_id: str, item: Dict[str, Any]) -> None:
    rows = _load_history(project_id)
    rows.append(item)
    _save_history(project_id, rows)


def _update_history(project_id: str, run_id: str, updates: Dict[str, Any]) -> None:
    rows = _load_history(project_id)
    for r in rows:
        if str(r.get("run_id", "")) == run_id:
            r.update(updates)
            break
    _save_history(project_id, rows)


def _load_active(project_id: str) -> Dict[str, Any]:
    data = _load_json(_active_path(project_id), {})
    return data if isinstance(data, dict) else {}


def _save_active(project_id: str, payload: Dict[str, Any]) -> None:
    _save_json(_active_path(project_id), payload)


def _clear_active(project_id: str) -> None:
    p = _active_path(project_id)
    if p.exists():
        try:
            p.unlink()
        except Exception:
            pass


def _finalize_if_dead(project_id: str) -> Dict[str, Any]:
    active = _load_active(project_id)
    if not active:
        return {}
    pid = int(active.get("pid") or 0)
    started_at = int(active.get("started_at") or 0)
    stale = started_at and (int(time.time()) - started_at) > _STALE_SESSION_MAX_AGE_S
    if not stale and oc.is_probably_running_opencompass(pid):
        return active
    run_id = str(active.get("run_id", ""))
    if run_id:
        current = {}
        for row in _load_history(project_id):
            if str(row.get("run_id", "")) == run_id:
                current = row
                break
        prior = str(current.get("status", "running"))
        if prior == "running":
            # Decide terminal state from artifacts / log
            out_path = Path(str(active.get("work_dir", "")))
            summary_path = _find_summary_in_workdir(out_path)
            log_text = _read_tail(Path(str(active.get("log_path", ""))), 400)
            succeeded = bool(summary_path) and "✅" in log_text
            if not succeeded:
                succeeded = bool(summary_path)
            status = "finished" if succeeded else "stopped_or_failed"
            _update_history(
                project_id,
                run_id,
                {
                    "status": status,
                    "ended_at": int(time.time()),
                    "summary_file": str(summary_path) if summary_path else "",
                },
            )
            _finalize_run_file(project_id, run_id, status, active)
    _clear_active(project_id)
    return {}


def _find_summary_in_workdir(work_dir: Path) -> Optional[Path]:
    if not work_dir or not work_dir.exists():
        return None
    _, summary_file, _ = oc.find_summary(work_dir)
    return summary_file


def _read_tail(path: Path, max_lines: int = 400) -> str:
    if not path or not path.exists():
        return ""
    try:
        txt = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    lines = txt.splitlines()
    return "\n".join(lines[-max_lines:])


def _finalize_run_file(
    project_id: str,
    run_id: str,
    status: str,
    active: Dict[str, Any],
) -> None:
    """Once a run concludes, assemble the permanent evaluation_result.json."""
    work_dir = Path(str(active.get("work_dir", "")))
    benchmark_json = Path(str(active.get("benchmark_json", "")))
    _, summary_file, summary_data = oc.find_summary(work_dir) if work_dir.exists() else (None, None, None)
    models = active.get("models") or []
    viz = {}
    try:
        if summary_data is not None:
            viz = oc.parse_for_viz(summary_data, models)
    except Exception:
        viz = {}
    run_dir_root = _runs_dir(project_id) / run_id
    run_dir_root.mkdir(parents=True, exist_ok=True)
    result_file = run_dir_root / "evaluation_result.json"
    payload = {
        "run_id": run_id,
        "status": status,
        "created_at": active.get("created_at") or datetime.utcnow().isoformat(),
        "ended_at": datetime.utcnow().isoformat(),
        "config_path": str(active.get("cfg_path", "")),
        "benchmark_json": str(benchmark_json),
        "opencompass_dir": str(active.get("opencompass_dir", "")),
        "work_dir": str(work_dir),
        "models": models,
        "result": {
            "success": status == "finished",
            "returncode": active.get("returncode"),
            "summary_file": str(summary_file) if summary_file else "",
            "summary_data": summary_data,
        },
        "viz": viz,
    }
    _save_json(result_file, payload)
    _update_history(
        project_id,
        run_id,
        {
            "result_file": str(result_file),
            "success": status == "finished",
            "models": [m.get("abbr", "") for m in models if isinstance(m, dict)],
            "summary_file": str(summary_file) if summary_file else "",
        },
    )


# ---------- Env ----------

class EnvSettingsPayload(BaseModel):
    opencompass_path: Optional[str] = None


@router.get("/env/check")
def env_check() -> Dict[str, Any]:
    oc_path = oc.effective_opencompass_path(PROJECT_ROOT)
    ok = oc.opencompass_path_ok(oc_path)
    gpu_count, gpus = _proc.detect_gpus()
    cuda_home = _proc.detect_cuda_home()
    torch_version = _proc.detect_torch_version()
    settings = lf.load_settings()
    return {
        "opencompass_path": str(oc_path),
        "opencompass_path_ok": ok,
        "cuda_home": cuda_home,
        "cuda_available": bool(cuda_home) or gpu_count > 0,
        "gpu_count": gpu_count,
        "gpus": gpus,
        "torch_version": torch_version,
        "python": _proc.python_version(),
        "platform": platform.system(),
        "settings": {
            "opencompass_path": settings.get("opencompass_path", ""),
        },
    }


@router.get("/env/settings")
def env_settings_get() -> Dict[str, Any]:
    return {"settings": lf.load_settings()}


@router.put("/env/settings")
def env_settings_put(body: EnvSettingsPayload) -> Dict[str, Any]:
    current = lf.load_settings()
    if body.opencompass_path is not None:
        current["opencompass_path"] = str(body.opencompass_path).strip()
    lf.save_settings(current)
    return {"saved": True, "settings": current}


# ---------- Discovery ----------

@router.get("/{project_id}/benchmarks")
def list_benchmarks(project_id: str) -> Dict[str, Any]:
    _assert_project(project_id)
    state = _load_state(project_id)
    items: List[Dict[str, Any]] = []
    benchmark_mcq = state.get("benchmark_mcq") or []
    if isinstance(benchmark_mcq, list) and benchmark_mcq:
        items.append(
            {
                "source": "state",
                "name": "current-benchmark_mcq",
                "path": "",
                "row_count": len(benchmark_mcq),
            }
        )
    for up in oc.list_benchmark_uploads(_project_dir(project_id)):
        items.append({"source": "upload", **up})
    return {"benchmarks": items}


@router.post("/{project_id}/upload-benchmark")
async def upload_benchmark(project_id: str, file: UploadFile = File(...)) -> Dict[str, Any]:
    _assert_project(project_id)
    if not file.filename or not file.filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="Only .json files are accepted")
    raw = await file.read()
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")
    if not isinstance(payload, list):
        raise HTTPException(
            status_code=400, detail="Benchmark JSON must be a list of MCQ objects"
        )
    if not payload:
        raise HTTPException(status_code=400, detail="Benchmark list is empty")
    dest_dir = _inputs_dir(project_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stem = _sanitize_tag(Path(file.filename).stem, fallback="benchmark")
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    dest = dest_dir / f"{stem}_{ts}.json"
    _save_json(dest, payload)
    return {
        "source": "upload",
        "name": dest.stem,
        "path": str(dest),
        "row_count": len(payload),
        "mtime": dest.stat().st_mtime,
    }


@router.get("/{project_id}/peft-candidates")
def list_peft(project_id: str) -> Dict[str, Any]:
    _assert_project(project_id)
    items = oc.list_peft_candidates(_project_dir(project_id))
    return {"candidates": items}


@router.get("/{project_id}/flow-suggestion")
def flow_suggestion(project_id: str) -> Dict[str, Any]:
    _assert_project(project_id)
    flow = _load_json(_flow_state_path(project_id), {})
    if not isinstance(flow, dict):
        return {"suggestion": None}
    trained_dir = str(flow.get("last_trained_model_dir", "")).strip()
    base_model = str(flow.get("last_training_base_model", "")).strip()
    if not trained_dir:
        return {"suggestion": None}
    adapter_cfg = Path(trained_dir) / "adapter_config.json"
    if adapter_cfg.exists():
        return {
            "suggestion": {
                "kind": "lora",
                "path": base_model,
                "peft_path": trained_dir,
                "abbr": f"{Path(base_model).name or 'base'}_{Path(trained_dir).name}",
            }
        }
    return {
        "suggestion": {
            "kind": "full",
            "path": trained_dir,
            "peft_path": "",
            "abbr": Path(trained_dir).name,
        }
    }


# ---------- Preview config ----------

class ModelEntry(BaseModel):
    enabled: bool = True
    is_local: bool = True
    abbr: str
    path: str = ""
    peft_path: str = ""
    api_key: str = ""
    api_base: str = ""
    temperature: float = 0.0
    max_out_len: int = 15
    query_per_second: int = 4
    num_procs: int = 4
    batch_size: int = 1
    num_gpus: int = 1


class EvalConfigRequest(BaseModel):
    benchmark_source: str  # "state" | "upload"
    benchmark_path: str = ""  # required when source=="upload"
    models: List[ModelEntry]
    max_samples: Optional[int] = Field(default=None)
    dataset_abbr: str = "proda_bench"
    work_dir: str = ""


def _resolve_benchmark_rows(
    project_id: str, req: EvalConfigRequest
) -> List[Dict[str, Any]]:
    if req.benchmark_source == "state":
        state = _load_state(project_id)
        rows = state.get("benchmark_mcq") or []
        if not isinstance(rows, list) or not rows:
            raise HTTPException(
                status_code=400, detail="No benchmark_mcq in project state"
            )
        return [r for r in rows if isinstance(r, dict)]
    if req.benchmark_source == "upload":
        p = Path(req.benchmark_path).expanduser()
        if not _is_within(p, _project_dir(project_id)):
            raise HTTPException(
                status_code=400, detail="benchmark_path outside project"
            )
        if not p.exists():
            raise HTTPException(status_code=404, detail="benchmark_path not found")
        data = _load_json(p, [])
        if not isinstance(data, list) or not data:
            raise HTTPException(status_code=400, detail="benchmark file empty or invalid")
        return [r for r in data if isinstance(r, dict)]
    raise HTTPException(status_code=400, detail=f"unknown benchmark_source: {req.benchmark_source}")


def _materialize_benchmark_json(
    project_id: str, rows: List[Dict[str, Any]], tag: str
) -> Path:
    dest_dir = _inputs_dir(project_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"benchmark_{tag}.json"
    _save_json(dest, rows)
    return dest


def _build_config(
    project_id: str,
    req: EvalConfigRequest,
    run_id: str,
    preview: bool,
) -> Dict[str, Any]:
    """Produce (config text + paths). When `preview=True` we reuse a single
    throw-away directory instead of creating a fresh `runs/{ts}/work` for every
    keystroke, avoiding unbounded disk pollution.
    """
    rows = _resolve_benchmark_rows(project_id, req)
    normalized, errors = oc.validate_models([m.model_dump() for m in req.models])
    if errors:
        raise HTTPException(status_code=400, detail={"model_errors": errors})
    if not normalized:
        raise HTTPException(status_code=400, detail="No enabled models to evaluate")

    oc_path = oc.effective_opencompass_path(PROJECT_ROOT)
    if not oc.opencompass_path_ok(oc_path):
        raise HTTPException(
            status_code=400,
            detail=f"OpenCompass not found at {oc_path}. Configure via /env/settings.",
        )

    tag = "_preview" if preview else run_id
    benchmark_json = _materialize_benchmark_json(project_id, rows, tag)
    if preview:
        work_dir = _runs_dir(project_id) / "_preview" / "work"
    elif req.work_dir:
        work_dir = Path(req.work_dir).expanduser()
    else:
        work_dir = _runs_dir(project_id) / run_id / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = oc.generate_eval_config(
        benchmark_json=benchmark_json,
        models=normalized,
        work_dir=work_dir,
        opencompass_dir=oc_path,
        max_samples=int(req.max_samples) if req.max_samples is not None else None,
        dataset_abbr=str(req.dataset_abbr).strip() or "proda_bench",
    )
    return {
        "run_id": run_id,
        "cfg_path": str(cfg_path),
        "benchmark_json": str(benchmark_json),
        "work_dir": str(work_dir),
        "opencompass_dir": str(oc_path),
        "models": normalized,
        "row_count": len(rows),
        "yaml": cfg_path.read_text(encoding="utf-8"),
    }


@router.post("/{project_id}/preview-config")
def preview_config(project_id: str, body: EvalConfigRequest) -> Dict[str, Any]:
    _assert_project(project_id)
    # Preview reuses a fixed `_preview` directory so per-keystroke previews
    # don't pile up timestamped work dirs.
    return _build_config(project_id, body, run_id="_preview", preview=True)


# ---------- Start / Cancel / Active / History ----------

class StartEvalRequest(BaseModel):
    config: EvalConfigRequest


@router.post("/{project_id}/start")
def start_eval(project_id: str, body: StartEvalRequest) -> Dict[str, Any]:
    _assert_project(project_id)
    with _project_lock(project_id):
        _finalize_if_dead(project_id)
        active = _load_active(project_id)
        if active and oc.is_probably_running_opencompass(int(active.get("pid") or 0)):
            raise HTTPException(
                status_code=409,
                detail=f"Eval run {active.get('run_id')} is already active (pid={active.get('pid')})",
            )
        run_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        prepared = _build_config(
            project_id, body.config, run_id=run_id, preview=False
        )
        cfg_path = Path(prepared["cfg_path"])
        work_dir = Path(prepared["work_dir"])
        oc_path = Path(prepared["opencompass_dir"])
        benchmark_json = Path(prepared["benchmark_json"])
        models = prepared["models"]

        # Logging
        log_dir = _runs_dir(project_id) / run_id
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "eval.log"

        # Env + cmd
        env = oc.build_eval_env(os.environ.copy(), oc_path)
        cmd = oc.resolve_eval_cmd(sys.executable, str(cfg_path), str(work_dir))

        # Launch
        try:
            popen_kwargs: Dict[str, Any] = {"cwd": str(oc_path), "env": env}
            if os.name != "nt":
                popen_kwargs["start_new_session"] = True
            logf = open(log_path, "w", encoding="utf-8")
            proc = subprocess.Popen(
                cmd,
                stdout=logf,
                stderr=subprocess.STDOUT,
                **popen_kwargs,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail=f"Failed to launch eval: {exc}")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to launch eval: {exc}")

        active_payload = {
            "run_id": run_id,
            "pid": int(proc.pid),
            "cmd": cmd,
            "cfg_path": str(cfg_path),
            "benchmark_json": str(benchmark_json),
            "work_dir": str(work_dir),
            "opencompass_dir": str(oc_path),
            "log_path": str(log_path),
            "models": models,
            "created_at": datetime.utcnow().isoformat(),
            "started_at": int(time.time()),
        }
        _save_active(project_id, active_payload)
        _append_history(
            project_id,
            {
                **active_payload,
                "status": "running",
                "ended_at": None,
            },
        )
        return {"run_id": run_id, "pid": int(proc.pid), "active": active_payload}


@router.post("/{project_id}/cancel")
def cancel_eval(project_id: str) -> Dict[str, Any]:
    _assert_project(project_id)
    with _project_lock(project_id):
        active = _load_active(project_id)
        if not active:
            raise HTTPException(status_code=404, detail="No active eval run")
        pid = int(active.get("pid") or 0)
        was_alive = oc.is_probably_running_opencompass(pid)
        result = _proc.terminate_pid_tree(pid, timeout=8.0)
        run_id = str(active.get("run_id", ""))
        if run_id:
            work_dir = Path(str(active.get("work_dir", "")))
            summary_path = _find_summary_in_workdir(work_dir)
            log_text = _read_tail(Path(str(active.get("log_path", ""))), 400)
            if was_alive:
                status = "stopped_or_failed"
            elif summary_path or "✅" in log_text:
                status = "finished"
            else:
                status = "stopped_or_failed"
            _update_history(
                project_id,
                run_id,
                {"status": status, "ended_at": int(time.time())},
            )
            _finalize_run_file(project_id, run_id, status, active)
        _clear_active(project_id)
        return {"cancelled": True, "pid": pid, "was_alive": was_alive, "kill_report": result}


@router.get("/{project_id}/active")
def get_active(project_id: str) -> Dict[str, Any]:
    _assert_project(project_id)
    # Finalize under lock so two concurrent GETs (e.g., two browser tabs) don't
    # both run _finalize_run_file and race on evaluation_result.json write.
    with _project_lock(project_id):
        _finalize_if_dead(project_id)
        active = _load_active(project_id)
    if not active:
        return {"active": None}
    pid = int(active.get("pid") or 0)
    return {"active": {**active, "alive": oc.is_probably_running_opencompass(pid)}}


@router.get("/{project_id}/history")
def list_history(project_id: str) -> Dict[str, Any]:
    _assert_project(project_id)
    with _project_lock(project_id):
        _finalize_if_dead(project_id)
        rows = _load_history(project_id)
    rows.sort(key=lambda r: int(r.get("started_at") or 0), reverse=True)
    return {"history": rows}


# ---------- Run detail / samples / annotations ----------

def _load_run_result(project_id: str, run_id: str) -> Dict[str, Any]:
    hist = _load_history(project_id)
    for row in hist:
        if str(row.get("run_id", "")) == run_id:
            result_file = Path(str(row.get("result_file", "")))
            if _is_within(result_file, _oc_root(project_id)) and result_file.exists():
                data = _load_json(result_file, {})
                if isinstance(data, dict):
                    return data
            # Fallback: try the conventional layout even if history row is missing result_file.
            fallback = _runs_dir(project_id) / run_id / "evaluation_result.json"
            if fallback.exists():
                data = _load_json(fallback, {})
                if isinstance(data, dict):
                    return data
            return row
    raise HTTPException(status_code=404, detail="Run not found")


@router.get("/{project_id}/runs/{run_id}")
def get_run(project_id: str, run_id: str) -> Dict[str, Any]:
    _assert_project(project_id)
    return _load_run_result(project_id, run_id)


def _annotations_path(project_id: str, run_id: str) -> Path:
    return _runs_dir(project_id) / run_id / "annotations.json"


@router.get("/{project_id}/runs/{run_id}/samples")
def get_run_samples(
    project_id: str,
    run_id: str,
    model: Optional[str] = None,
    status: Optional[str] = None,  # "pass" | "fail"
    subject: Optional[str] = None,
    question_type: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> Dict[str, Any]:
    _assert_project(project_id)
    payload = _load_run_result(project_id, run_id)
    benchmark_path = Path(str(payload.get("benchmark_json", "")))
    if not _is_within(benchmark_path, _project_dir(project_id)) or not benchmark_path.exists():
        raise HTTPException(status_code=404, detail="benchmark_json missing")
    rows = _load_json(benchmark_path, [])
    if not isinstance(rows, list):
        rows = []
    work_dir = Path(str(payload.get("work_dir", "")))
    # OpenCompass nests results under a timestamp; look for summary to locate the actual run_dir.
    oc_run_dir, _, _ = oc.find_summary(work_dir) if work_dir.exists() else (None, None, None)
    if not oc_run_dir:
        oc_run_dir = work_dir  # best-effort
    models = payload.get("models") or []
    all_samples = oc.collect_samples(
        run_dir=Path(oc_run_dir) if oc_run_dir else work_dir,
        benchmark_rows=[r for r in rows if isinstance(r, dict)],
        models=[m for m in models if isinstance(m, dict)],
    )
    # Filter
    filtered = all_samples
    if model:
        filtered = [s for s in filtered if s.get("model") == model]
    if status == "pass":
        filtered = [s for s in filtered if s.get("pass")]
    elif status == "fail":
        filtered = [s for s in filtered if not s.get("pass")]
    if subject:
        filtered = [s for s in filtered if s.get("subject") == subject]
    if question_type:
        filtered = [s for s in filtered if s.get("question_type") == question_type]
    total = len(filtered)
    sliced = filtered[max(0, offset) : max(0, offset) + max(0, limit)]
    # Build facet hints for UI filters
    models_list = sorted({s["model"] for s in all_samples})
    subjects_list = sorted({s["subject"] for s in all_samples if s.get("subject")})
    types_list = sorted({s["question_type"] for s in all_samples if s.get("question_type")})
    return {
        "total": total,
        "offset": max(0, offset),
        "limit": max(0, limit),
        "rows": sliced,
        "facets": {
            "models": models_list,
            "subjects": subjects_list,
            "question_types": types_list,
        },
    }


class AnnotationPayload(BaseModel):
    sample_id: str
    model: str = ""
    issue_type: str  # "concept_gap" | "capability_deficit" | "unlabeled"
    note: str = ""


@router.get("/{project_id}/runs/{run_id}/annotations")
def get_annotations(project_id: str, run_id: str) -> Dict[str, Any]:
    _assert_project(project_id)
    _ = _load_run_result(project_id, run_id)  # 404 if no such run
    data = _load_json(_annotations_path(project_id, run_id), {"annotations": []})
    if not isinstance(data, dict):
        data = {"annotations": []}
    data.setdefault("annotations", [])
    return data


@router.put("/{project_id}/runs/{run_id}/annotations")
def put_annotation(
    project_id: str,
    run_id: str,
    body: AnnotationPayload,
) -> Dict[str, Any]:
    _assert_project(project_id)
    _ = _load_run_result(project_id, run_id)
    valid = {"concept_gap", "capability_deficit", "unlabeled"}
    if body.issue_type not in valid:
        raise HTTPException(
            status_code=400, detail=f"issue_type must be one of {sorted(valid)}"
        )
    if not str(body.sample_id).strip():
        raise HTTPException(status_code=400, detail="sample_id is required")
    # Serialize concurrent annotation writes so two parallel PUTs don't lose data.
    with _project_lock(project_id):
        data = _load_json(_annotations_path(project_id, run_id), {"annotations": []})
        if not isinstance(data, dict):
            data = {"annotations": []}
        items = data.setdefault("annotations", [])
        if not isinstance(items, list):
            items = []
            data["annotations"] = items
        key = (str(body.sample_id), str(body.model))
        updated = False
        now = datetime.utcnow().isoformat()
        for entry in items:
            if (
                str(entry.get("sample_id")) == key[0]
                and str(entry.get("model", "")) == key[1]
            ):
                entry.update(
                    {
                        "issue_type": body.issue_type,
                        "note": body.note,
                        "updated_at": now,
                    }
                )
                updated = True
                break
        if not updated:
            items.append(
                {
                    "sample_id": body.sample_id,
                    "model": body.model,
                    "issue_type": body.issue_type,
                    "note": body.note,
                    "created_at": now,
                    "updated_at": now,
                }
            )
        _save_json(_annotations_path(project_id, run_id), data)
    return {"saved": True, "annotations": items}


# ---------- Logs (tail + SSE) ----------

@router.get("/{project_id}/runs/{run_id}/logs")
def get_logs(project_id: str, run_id: str, tail: int = 500) -> Dict[str, Any]:
    _assert_project(project_id)
    hist = _load_history(project_id)
    log_path: Optional[Path] = None
    for row in hist:
        if str(row.get("run_id", "")) == run_id:
            log_path = Path(str(row.get("log_path", "")))
            break
    if not log_path or not _is_within(log_path, _oc_root(project_id)):
        raise HTTPException(status_code=404, detail="log_path missing / outside root")
    return {"log_path": str(log_path), "text": _read_tail(log_path, max(1, int(tail)))}


async def _log_stream(project_id: str, run_id: str) -> AsyncIterator[bytes]:
    hist = _load_history(project_id)
    log_path: Optional[Path] = None
    for row in hist:
        if str(row.get("run_id", "")) == run_id:
            log_path = Path(str(row.get("log_path", "")))
            break
    if not log_path or not _is_within(log_path, _oc_root(project_id)):
        raise HTTPException(status_code=404, detail="log_path missing / outside root")
    offset = 0
    idle_ticks = 0
    yield b": connected\n\n"
    while True:
        if not log_path.exists() and offset > 0:
            yield b"event: end\ndata: log-file-missing\n\n"
            return
        # Inline tail-from-offset (simpler than pulling from another lib)
        try:
            size = log_path.stat().st_size if log_path.exists() else offset
        except Exception:
            size = offset
        if size < offset:
            offset = 0
        if log_path.exists() and size > offset:
            with log_path.open("rb") as f:
                f.seek(offset)
                chunk = f.read(min(64_000, size - offset))
            offset += len(chunk)
            text = chunk.decode("utf-8", errors="replace")
            for line in text.split("\n"):
                if not line:
                    continue
                escaped = line.replace("\r", "")
                yield f"data: {escaped}\n\n".encode("utf-8")
            if text:
                idle_ticks = 0
            else:
                idle_ticks += 1
        else:
            idle_ticks += 1
        active = _load_active(project_id)
        active_run_id = str(active.get("run_id", ""))
        if not active or active_run_id != run_id:
            yield b"event: end\ndata: session-not-active\n\n"
            return
        if not oc.is_probably_running_opencompass(int(active.get("pid") or 0)):
            await asyncio.sleep(0.5)
            # final flush
            if log_path.exists():
                try:
                    size2 = log_path.stat().st_size
                except Exception:
                    size2 = offset
                if size2 > offset:
                    with log_path.open("rb") as f:
                        f.seek(offset)
                        chunk = f.read(min(64_000, size2 - offset))
                    offset += len(chunk)
                    text2 = chunk.decode("utf-8", errors="replace")
                    for line in text2.split("\n"):
                        if line:
                            yield f"data: {line}\n\n".encode("utf-8")
            yield b"event: end\ndata: pid-dead\n\n"
            return
        if idle_ticks >= 5:
            yield b": heartbeat\n\n"
            idle_ticks = 0
        await asyncio.sleep(1.0)


@router.get("/{project_id}/runs/{run_id}/logs/stream")
async def stream_logs(project_id: str, run_id: str) -> StreamingResponse:
    _assert_project(project_id)
    headers = {
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        _log_stream(project_id, run_id),
        media_type="text/event-stream",
        headers=headers,
    )
