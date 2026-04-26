"""Phase 5 — Fine-Tuning REST + SSE endpoints (LLaMA-Factory integration)."""

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

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.lib import llama_factory as lf

# Per-project lock to serialize /start and /cancel so two concurrent clients
# don't both spawn a trainer against the same project.
_PROJECT_LOCKS: Dict[str, threading.Lock] = {}
_PROJECT_LOCKS_GUARD = threading.Lock()

# Training sessions older than this are considered abandoned even if their PID
# happens to still be alive (defence against PID reuse after unclean shutdown).
_STALE_SESSION_MAX_AGE_S = 48 * 3600

_SAFE_TAG = re.compile(r"[^A-Za-z0-9_\-]+")


def _project_lock(project_id: str) -> threading.Lock:
    with _PROJECT_LOCKS_GUARD:
        lock = _PROJECT_LOCKS.get(project_id)
        if lock is None:
            lock = threading.Lock()
            _PROJECT_LOCKS[project_id] = lock
        return lock


def _sanitize_tag(value: str, fallback: str = "dataset") -> str:
    cleaned = _SAFE_TAG.sub("_", str(value or "").strip()).strip("_")
    return cleaned or fallback
from ui.utils.project_store import (
    get_project as _get_project,
    load_project_state as _load_state,
    project_dir_path as _project_dir,
    save_project_state as _save_state,
)

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MODEL_ROOT_DEFAULT = PROJECT_ROOT / "Model"


# ---------- helpers ----------

def _assert_project(project_id: str) -> Dict[str, Any]:
    project = _get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _ft_export_dir(project_id: str) -> Path:
    return _project_dir(project_id) / "finetune_exports"


def _configs_dir(project_id: str) -> Path:
    return _ft_export_dir(project_id) / "configs"


def _logs_dir(project_id: str) -> Path:
    return _ft_export_dir(project_id) / "logs"


def _outputs_root(project_id: str) -> Path:
    return _project_dir(project_id) / "model_outputs"


def _active_job_path(project_id: str) -> Path:
    return _ft_export_dir(project_id) / "active_train_job.json"


def _history_path(project_id: str) -> Path:
    return _ft_export_dir(project_id) / "train_history.json"


def _flow_state_path(project_id: str) -> Path:
    return _project_dir(project_id) / "workflow" / "second_round_flow.json"


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


def _is_within(path: Path, root: Path) -> bool:
    try:
        p = path.resolve()
        r = root.resolve()
        return p == r or r in p.parents
    except Exception:
        return False


def _load_history(project_id: str) -> List[Dict[str, Any]]:
    data = _load_json(_history_path(project_id), [])
    return [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []


def _save_history(project_id: str, rows: List[Dict[str, Any]]) -> None:
    _save_json(_history_path(project_id), rows)


def _append_history(project_id: str, item: Dict[str, Any]) -> None:
    rows = _load_history(project_id)
    rows.append(item)
    _save_history(project_id, rows)


def _update_history(project_id: str, session_id: str, updates: Dict[str, Any]) -> None:
    rows = _load_history(project_id)
    for row in rows:
        if str(row.get("session_id", "")) == str(session_id):
            row.update(updates)
            break
    _save_history(project_id, rows)


def _load_active(project_id: str) -> Dict[str, Any]:
    data = _load_json(_active_job_path(project_id), {})
    return data if isinstance(data, dict) else {}


def _save_active(project_id: str, payload: Dict[str, Any]) -> None:
    _save_json(_active_job_path(project_id), payload)


def _clear_active(project_id: str) -> None:
    p = _active_job_path(project_id)
    if p.exists():
        try:
            p.unlink()
        except Exception:
            pass


def _finalize_if_dead(project_id: str) -> Dict[str, Any]:
    """If the active job's PID is no longer running, write back status to history and clear."""
    active = _load_active(project_id)
    if not active:
        return {}
    pid = int(active.get("pid") or 0)
    started_at = int(active.get("started_at") or 0)
    # Defence against PID reuse after unclean shutdown: if the job is too old,
    # treat as dead regardless of whether the PID is alive.
    stale = started_at and (int(time.time()) - started_at) > _STALE_SESSION_MAX_AGE_S
    if not stale and lf.is_probably_running_llamafactory(pid):
        return active
    session_id = str(active.get("session_id", ""))
    log_path = Path(str(active.get("log_path", "")))
    out_dir = Path(str(active.get("output_dir", "")))
    log_text = lf.read_tail(log_path, 600) if log_path else ""
    if session_id:
        # Preserve a status that was already set explicitly (e.g. via /cancel):
        # only re-infer when the history entry is still "running".
        current = {}
        for row in _load_history(project_id):
            if str(row.get("session_id", "")) == session_id:
                current = row
                break
        prior = str(current.get("status", "running")) if current else "running"
        if prior == "running":
            outcome = (
                "finished"
                if lf.looks_like_training_success(out_dir, log_text)
                else "stopped_or_failed"
            )
            _update_history(
                project_id,
                session_id,
                {"status": outcome, "ended_at": int(time.time())},
            )
        else:
            outcome = prior
        flow = _load_json(_flow_state_path(project_id), {})
        if not isinstance(flow, dict):
            flow = {}
        flow.update(
            {
                "last_training_finished_at": datetime.utcnow().isoformat(),
                "last_training_outcome": outcome,
            }
        )
        if outcome == "finished":
            flow["last_trained_model_dir"] = str(out_dir)
        _save_json(_flow_state_path(project_id), flow)
    _clear_active(project_id)
    return {}


# ---------- Env ----------

class EnvSettingsPayload(BaseModel):
    llamafactory_path: str = ""
    model_root: str = ""


@router.get("/env/check")
def env_check() -> Dict[str, Any]:
    settings = lf.load_settings()
    lf_path = lf.effective_llamafactory_path(PROJECT_ROOT)
    lf_ok = lf.llamafactory_path_ok(lf_path)
    gpu_count, gpus = lf.detect_gpus()
    cuda_home = lf.detect_cuda_home()
    torch_version = lf.detect_torch_version()
    import shutil as _sh

    cli_kind = "llamafactory-cli" if _sh.which("llamafactory-cli") else "python_src"
    model_root = str(settings.get("model_root") or MODEL_ROOT_DEFAULT)
    return {
        "llamafactory_path": str(lf_path),
        "llamafactory_path_ok": lf_ok,
        "cli": cli_kind,
        "cuda_home": cuda_home,
        "cuda_available": bool(cuda_home) or gpu_count > 0,
        "gpu_count": gpu_count,
        "gpus": gpus,
        "torch_version": torch_version,
        "python": sys.version.split(" ", 1)[0],
        "platform": platform.system(),
        "model_root": model_root,
        "model_root_ok": Path(model_root).exists(),
        "settings": settings,
    }


@router.get("/env/settings")
def env_settings_get() -> Dict[str, Any]:
    return {"settings": lf.load_settings()}


@router.put("/env/settings")
def env_settings_put(body: EnvSettingsPayload) -> Dict[str, Any]:
    current = lf.load_settings()
    if body.llamafactory_path is not None:
        current["llamafactory_path"] = str(body.llamafactory_path).strip()
    if body.model_root is not None:
        current["model_root"] = str(body.model_root).strip()
    lf.save_settings(current)
    return {"saved": True, "settings": current}


# ---------- Discovery ----------

@router.get("/{project_id}/datasets")
def list_datasets(project_id: str) -> Dict[str, Any]:
    _assert_project(project_id)
    state = _load_state(project_id)
    session_rows = list(state.get("finetune_data") or [])
    items = lf.discover_datasets(_project_dir(project_id), session_rows)
    return {"datasets": items}


@router.get("/{project_id}/models")
def list_models(project_id: str) -> Dict[str, Any]:
    _assert_project(project_id)
    settings = lf.load_settings()
    model_root = Path(str(settings.get("model_root") or MODEL_ROOT_DEFAULT))
    found = lf.list_local_models(model_root)
    return {"model_root": str(model_root), "models": found}


# ---------- Train config ----------

class TrainConfig(BaseModel):
    # Dataset selection
    dataset_source: str  # "session" | "file"
    dataset_path: str = ""  # required when source=="file"
    dataset_name: str  # label stored in dataset_info.json

    # Model
    model_path: str
    template: str = ""

    # Method
    finetuning_type: str = "lora"  # "lora" | "qlora" | "full"
    lora_rank: int = 8
    lora_alpha: int = 16
    lora_dropout: float = 0.05

    # Train
    learning_rate: float = 5e-5
    warmup_ratio: float = 0.03
    num_train_epochs: float = 3.0
    per_device_train_batch_size: int = 1
    gradient_accumulation_steps: int = 8
    cutoff_len: int = 2048
    max_samples: int = 100000
    logging_steps: int = 5
    save_steps: int = 200

    # Distributed
    nproc_per_node: int = 1


def _resolve_dataset_rows(project_id: str, req: TrainConfig) -> List[Dict[str, Any]]:
    if req.dataset_source == "session":
        state = _load_state(project_id)
        return list(state.get("finetune_data") or [])
    if req.dataset_source == "file":
        path = Path(req.dataset_path).expanduser()
        allowed = [_project_dir(project_id)]
        if not any(_is_within(path, root) for root in allowed):
            raise HTTPException(status_code=400, detail="dataset_path is outside project directory")
        if not path.exists():
            raise HTTPException(status_code=404, detail="dataset file not found")
        data = _load_json(path, [])
        if not isinstance(data, list):
            raise HTTPException(status_code=400, detail="dataset file is not a JSON array")
        return [x for x in data if isinstance(x, dict)]
    raise HTTPException(status_code=400, detail=f"unknown dataset_source: {req.dataset_source}")


def _build_yaml_payload(
    project_id: str,
    req: TrainConfig,
    run_suffix: str = "",
) -> Dict[str, Any]:
    template = req.template.strip() or lf.infer_template(req.model_path)
    model_tag = Path(req.model_path).name or "model"
    dataset_tag = req.dataset_name.strip() or "dataset"
    base_name = f"{dataset_tag}_{model_tag}"
    output_name = (
        f"{base_name}_{_sanitize_tag(run_suffix, fallback='run')}"
        if str(run_suffix).strip()
        else base_name
    )
    output_dir = _outputs_root(project_id) / output_name
    yaml_text = lf.build_train_yaml(
        {
            "model_path": req.model_path,
            "dataset_name": dataset_tag,
            "output_dir": str(output_dir),
            "template": template,
            "finetuning_type": req.finetuning_type,
            "lora_rank": req.lora_rank,
            "lora_alpha": req.lora_alpha,
            "lora_dropout": req.lora_dropout,
            "learning_rate": req.learning_rate,
            "warmup_ratio": req.warmup_ratio,
            "num_train_epochs": req.num_train_epochs,
            "per_device_train_batch_size": req.per_device_train_batch_size,
            "gradient_accumulation_steps": req.gradient_accumulation_steps,
            "cutoff_len": req.cutoff_len,
            "max_samples": req.max_samples,
            "logging_steps": req.logging_steps,
            "save_steps": req.save_steps,
        }
    )
    return {
        "yaml": yaml_text,
        "output_dir": str(output_dir),
        "template": template,
        "model_tag": model_tag,
        "dataset_tag": dataset_tag,
    }


class PreviewYamlRequest(BaseModel):
    config: TrainConfig


@router.post("/{project_id}/preview-yaml")
def preview_yaml(project_id: str, body: PreviewYamlRequest) -> Dict[str, Any]:
    _assert_project(project_id)
    return _build_yaml_payload(project_id, body.config)


# ---------- Start / Active / Cancel ----------

class StartTrainingRequest(BaseModel):
    config: TrainConfig
    yaml_override: str = ""  # if non-empty, user edited YAML in Monaco; use as-is


@router.post("/{project_id}/start")
def start_training(project_id: str, body: StartTrainingRequest) -> Dict[str, Any]:
    _assert_project(project_id)
    if not str(body.config.model_path or "").strip():
        raise HTTPException(status_code=400, detail="model_path is required")

    with _project_lock(project_id):
        _finalize_if_dead(project_id)
        active = _load_active(project_id)
        if active and lf.is_probably_running_llamafactory(int(active.get("pid") or 0)):
            raise HTTPException(
                status_code=409,
                detail=f"Training session {active.get('session_id')} is already running (pid={active.get('pid')})",
            )

        lf_path = lf.effective_llamafactory_path(PROJECT_ROOT)
        if not lf.llamafactory_path_ok(lf_path):
            raise HTTPException(
                status_code=400,
                detail=f"LLaMA-Factory not found at {lf_path}. Configure via /env/settings.",
            )

        # Resolve dataset → write sharegpt + dataset_info.json
        rows = _resolve_dataset_rows(project_id, body.config)
        if not rows:
            raise HTTPException(status_code=400, detail="dataset is empty")
        sharegpt_rows = rows if lf.is_sharegpt_rows(rows) else lf.convert_to_sharegpt(rows)
        if not sharegpt_rows:
            raise HTTPException(status_code=400, detail="sharegpt conversion produced no rows")

        data_dir = lf_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        # Filesystem-safe tag: drop whitespace / parens / other LLaMA-Factory-hostile chars
        dataset_tag = _sanitize_tag(body.config.dataset_name, fallback="dataset")
        data_file = data_dir / f"{dataset_tag}.json"
        _save_json(data_file, sharegpt_rows)

        dataset_info_path = data_dir / "dataset_info.json"
        existing = _load_json(dataset_info_path, {})
        if not isinstance(existing, dict):
            existing = {}
        existing[dataset_tag] = {
            "file_name": data_file.name,
            "formatting": "sharegpt",
            "columns": {"messages": "conversations"},
        }
        _save_json(dataset_info_path, existing)

        # Build YAML (use override if provided)
        run_suffix = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        payload = _build_yaml_payload(project_id, body.config, run_suffix=run_suffix)
        yaml_text = body.yaml_override.strip() or payload["yaml"]
        output_dir = Path(payload["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)

        cfg_dir = _configs_dir(project_id)
        cfg_dir.mkdir(parents=True, exist_ok=True)
        cfg_path = cfg_dir / f"{payload['dataset_tag']}_{payload['model_tag']}_{run_suffix}.yaml"
        cfg_path.write_text(yaml_text, encoding="utf-8")

        log_dir = _logs_dir(project_id)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{payload['dataset_tag']}_{payload['model_tag']}_{int(time.time())}.log"

        # Env + command
        base_env = os.environ.copy()
        env, runtime_meta = lf.prepare_env(base_env, int(body.config.nproc_per_node))
        cmd = lf.resolve_train_cmd(
            sys.executable,
            str(cfg_path),
            int(body.config.nproc_per_node),
            int(runtime_meta["master_port"]),
        )

        # Launch
        try:
            popen_kwargs: Dict[str, Any] = {
                "cwd": str(lf_path),
                "env": env,
            }
            # On POSIX, start_new_session lets us kill the process group.
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
            raise HTTPException(status_code=400, detail=f"Failed to launch training: {exc}")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to launch training: {exc}")

        session_id = str(time.time_ns())
        active_payload = {
            "session_id": session_id,
            "pid": int(proc.pid),
            "cmd": cmd,
            "log_path": str(log_path),
            "cfg_path": str(cfg_path),
            "output_dir": str(output_dir),
            "dataset_name": dataset_tag,
            "model_path": body.config.model_path,
            "model_tag": payload["model_tag"],
            "finetuning_type": body.config.finetuning_type,
            "nproc_per_node": int(body.config.nproc_per_node),
            "master_port": int(runtime_meta.get("master_port", 0)),
            "cuda_home": runtime_meta.get("cuda_home", ""),
            "started_at": int(time.time()),
        }
        _save_active(project_id, active_payload)
        _append_history(
            project_id,
            {
                **active_payload,
                "status": "running",
                "ended_at": None,
                "lora_rank": int(body.config.lora_rank),
                "lora_alpha": int(body.config.lora_alpha),
                "lora_dropout": float(body.config.lora_dropout),
                "learning_rate": float(body.config.learning_rate),
                "warmup_ratio": float(body.config.warmup_ratio),
                "epochs": float(body.config.num_train_epochs),
                "batch_size": int(body.config.per_device_train_batch_size),
                "grad_accum": int(body.config.gradient_accumulation_steps),
                "max_samples": int(body.config.max_samples),
                "template": payload["template"],
            },
        )
        # Flow state hint
        flow = _load_json(_flow_state_path(project_id), {})
        if not isinstance(flow, dict):
            flow = {}
        flow.update(
            {
                "last_training_started_at": datetime.utcnow().isoformat(),
                "last_training_output_dir": str(output_dir),
                "last_training_dataset_name": dataset_tag,
                "last_training_base_model": body.config.model_path,
                "last_training_type": body.config.finetuning_type,
            }
        )
        _save_json(_flow_state_path(project_id), flow)

        return {"session_id": session_id, "pid": int(proc.pid), "active": active_payload}


@router.post("/{project_id}/cancel")
def cancel_training(project_id: str) -> Dict[str, Any]:
    _assert_project(project_id)
    with _project_lock(project_id):
        active = _load_active(project_id)
        if not active:
            raise HTTPException(status_code=404, detail="No active training session")
        pid = int(active.get("pid") or 0)
        # Was the process still alive *before* we try to kill? If it already died
        # on its own we shouldn't overwrite a legitimate "finished" status below.
        was_alive = lf.is_probably_running_llamafactory(pid)
        result = lf.terminate_pid_tree(pid, timeout=8.0)
        session_id = str(active.get("session_id", ""))
        out_dir = Path(str(active.get("output_dir", "")))
        log_path = Path(str(active.get("log_path", "")))
        log_text = lf.read_tail(log_path, 600) if log_path else ""
        if session_id:
            if was_alive:
                status = "stopped_or_failed"
            elif lf.looks_like_training_success(out_dir, log_text):
                status = "finished"
            else:
                status = "stopped_or_failed"
            _update_history(
                project_id,
                session_id,
                {"status": status, "ended_at": int(time.time())},
            )
        _clear_active(project_id)
        return {
            "cancelled": True,
            "pid": pid,
            "was_alive": was_alive,
            "kill_report": result,
        }


@router.get("/{project_id}/active")
def get_active(project_id: str) -> Dict[str, Any]:
    _assert_project(project_id)
    _finalize_if_dead(project_id)
    active = _load_active(project_id)
    if not active:
        return {"active": None}
    pid = int(active.get("pid") or 0)
    alive = lf.is_probably_running_llamafactory(pid)
    return {
        "active": {**active, "alive": alive},
    }


@router.get("/{project_id}/history")
def get_history(project_id: str) -> Dict[str, Any]:
    _assert_project(project_id)
    _finalize_if_dead(project_id)
    rows = _load_history(project_id)
    rows.sort(key=lambda r: int(r.get("started_at") or 0), reverse=True)
    return {"history": rows}


# ---------- Sessions: logs / metrics / output ----------

def _find_session(project_id: str, session_id: str) -> Dict[str, Any]:
    for row in _load_history(project_id):
        if str(row.get("session_id", "")) == session_id:
            return row
    raise HTTPException(status_code=404, detail="Session not found")


@router.get("/{project_id}/sessions/{session_id}/logs")
def get_logs(
    project_id: str,
    session_id: str,
    tail: int = 500,
) -> Dict[str, Any]:
    _assert_project(project_id)
    row = _find_session(project_id, session_id)
    log_path = Path(str(row.get("log_path", "")))
    if not _is_within(log_path, _project_dir(project_id)):
        raise HTTPException(status_code=400, detail="log_path outside project root")
    return {
        "log_path": str(log_path),
        "text": lf.read_tail(log_path, max(1, int(tail))),
    }


@router.get("/{project_id}/sessions/{session_id}/metrics")
def get_metrics(project_id: str, session_id: str, max_points: int = 4000) -> Dict[str, Any]:
    _assert_project(project_id)
    row = _find_session(project_id, session_id)
    log_path = Path(str(row.get("log_path", "")))
    output_dir = Path(str(row.get("output_dir", "")))
    jsonl_path = output_dir / "trainer_log.jsonl"
    points = lf.parse_metrics_jsonl(jsonl_path, max_points=max_points)
    if not points and log_path.exists():
        points = lf.parse_metrics_stdout(
            log_path.read_text(encoding="utf-8", errors="ignore"),
            max_points=max_points,
        )
    return {"source": "jsonl" if jsonl_path.exists() and points else "stdout", "points": points}


@router.get("/{project_id}/sessions/{session_id}/output-tree")
def get_output_tree(project_id: str, session_id: str) -> Dict[str, Any]:
    _assert_project(project_id)
    row = _find_session(project_id, session_id)
    output_dir = Path(str(row.get("output_dir", "")))
    if not _is_within(output_dir, _project_dir(project_id)):
        raise HTTPException(status_code=400, detail="output_dir outside project root")
    return {
        "output_dir": str(output_dir),
        "exists": output_dir.exists(),
        "entries": lf.list_output_tree(output_dir),
    }


# ---------- SSE log stream ----------

async def _log_stream(project_id: str, session_id: str) -> AsyncIterator[bytes]:
    row = _find_session(project_id, session_id)
    log_path = Path(str(row.get("log_path", "")))
    if not _is_within(log_path, _project_dir(project_id)):
        raise HTTPException(status_code=400, detail="log_path outside project root")
    offset = 0
    idle_ticks = 0
    # Emit an initial hello event so the browser reconnect timer doesn't trigger immediately
    yield b": connected\n\n"
    while True:
        # Detect log-file deletion explicitly so the client can stop retrying.
        if not log_path.exists() and offset > 0:
            yield b"event: end\ndata: log-file-missing\n\n"
            return
        text, offset = lf.read_tail_from_offset(log_path, offset, max_bytes=64_000)
        if text:
            idle_ticks = 0
            # Each line becomes its own SSE "data:" payload so the client can split cleanly
            for line in text.split("\n"):
                if not line:
                    continue
                escaped = line.replace("\r", "")
                yield f"data: {escaped}\n\n".encode("utf-8")
        else:
            idle_ticks += 1
        # Check liveness — if job has finalized, send one terminal event then close
        active = _load_active(project_id)
        if not active or str(active.get("session_id")) != session_id:
            # Session is no longer active — send terminal event and exit
            yield b"event: end\ndata: session-not-active\n\n"
            return
        pid_alive = lf.is_probably_running_llamafactory(int(active.get("pid") or 0))
        if not pid_alive:
            # Give the file system one more chance to flush
            await asyncio.sleep(0.5)
            text2, offset = lf.read_tail_from_offset(log_path, offset, max_bytes=64_000)
            if text2:
                for line in text2.split("\n"):
                    if line:
                        yield f"data: {line}\n\n".encode("utf-8")
            yield b"event: end\ndata: pid-dead\n\n"
            return
        # Heartbeat every ~5 idle cycles so proxies don't drop the connection
        if idle_ticks >= 5:
            yield b": heartbeat\n\n"
            idle_ticks = 0
        await asyncio.sleep(1.0)


@router.get("/{project_id}/sessions/{session_id}/logs/stream")
async def stream_logs(project_id: str, session_id: str) -> StreamingResponse:
    _assert_project(project_id)
    # Ensure session exists (raises 404 otherwise)
    _find_session(project_id, session_id)
    headers = {
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        _log_stream(project_id, session_id),
        media_type="text/event-stream",
        headers=headers,
    )
