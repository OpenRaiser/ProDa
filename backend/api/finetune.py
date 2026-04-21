from __future__ import annotations

import threading
import traceback
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.lib.jobs import JobRegistry
from proda.finetune_generator import generate_finetune_data
from ui.utils.project_store import (
    get_project as _get_project,
    load_project_state as _load_state,
    save_project_state as _save_state,
)

router = APIRouter()
_reg = JobRegistry()


class LlmCtx(BaseModel):
    provider: str
    model: str
    api_key: str
    api_base: str = ""


class StartFineTuneRequest(BaseModel):
    total_samples: int = 300
    qa_ratio: float = 0.6
    choice_ratio: float = 0.3
    single_choice_ratio: float = 0.7
    true_ratio: float = 0.6
    author_notes: str = ""
    max_workers: int = 6
    retries: int = 2
    max_refill_rounds: int = 4
    adaptive_concurrency: bool = True
    batch_size: int = 8
    l2_window_size: int = 8
    l1_topn: int = 20
    allow_l2_reuse_after_exhausted: bool = True
    llm: LlmCtx


def _assert_project(project_id: str) -> Dict[str, Any]:
    project = _get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _run_generate(
    job_id: str,
    project_id: str,
    req: StartFineTuneRequest,
    knowledge_core: Dict[str, Any],
) -> None:
    cancel_event = _reg.cancel_event(job_id)
    target_total = max(1, int(req.total_samples))

    def on_progress(done: int, total: int) -> None:
        t = max(1, int(total))
        d = int(max(0, min(done, t)))
        _reg.update(
            job_id,
            total=t,
            done=d,
            progress=int(d * 100 / t),
            message=f"Generating samples: {d}/{t}",
        )

    try:
        _reg.update(
            job_id,
            status="running",
            message="Starting FineTune generation...",
            total=target_total,
            done=0,
            progress=2,
        )
        rows = generate_finetune_data(
            knowledge_core=knowledge_core,
            provider=req.llm.provider,
            model=req.llm.model,
            api_key=req.llm.api_key,
            api_base=req.llm.api_base,
            total_samples=int(req.total_samples),
            qa_ratio=float(req.qa_ratio),
            choice_ratio=float(req.choice_ratio),
            single_choice_ratio=float(req.single_choice_ratio),
            true_ratio=float(req.true_ratio),
            author_notes=str(req.author_notes or ""),
            max_workers=int(req.max_workers),
            retries=int(req.retries),
            max_refill_rounds=int(req.max_refill_rounds),
            adaptive_concurrency=bool(req.adaptive_concurrency),
            batch_size=int(req.batch_size),
            l2_window_size=int(req.l2_window_size),
            l1_topn=int(req.l1_topn),
            allow_l2_reuse_after_exhausted=bool(req.allow_l2_reuse_after_exhausted),
            progress_callback=on_progress,
            cancel_event=cancel_event,
        )
        stats = getattr(generate_finetune_data, "last_run_stats", {}) or {}

        state = _load_state(project_id)
        state["finetune_data"] = list(rows or [])
        _save_state(project_id, state)

        if stats.get("cancelled"):
            _reg.update(
                job_id,
                status="cancelled",
                progress=100,
                message=f"Cancelled · kept {len(rows)} rows",
                result={"rows": list(rows or []), "stats": stats},
            )
        else:
            _reg.update(
                job_id,
                status="done",
                progress=100,
                message=f"Done · {len(rows)} rows",
                result={"rows": list(rows or []), "stats": stats},
            )
    except Exception as exc:  # noqa: BLE001
        _reg.update(
            job_id,
            status="error",
            error=f"{exc}\n{traceback.format_exc()}",
            message=f"Error: {exc}",
        )


@router.post("/{project_id}/start")
def start_job(project_id: str, body: StartFineTuneRequest) -> Dict[str, Any]:
    _assert_project(project_id)
    if not body.llm.api_key:
        raise HTTPException(status_code=400, detail="LLM api_key is required")

    state = _load_state(project_id)
    core = state.get("knowledge_core") or {}
    l2 = core.get("l2_statements") or []
    if not l2:
        raise HTTPException(
            status_code=400,
            detail="No L2 statements. Run Step 1 (Data Processing) first.",
        )

    job_id = _reg.create(
        project_id,
        extra={
            "total_samples": int(body.total_samples),
            "qa_ratio": float(body.qa_ratio),
            "choice_ratio": float(body.choice_ratio),
            "true_ratio": float(body.true_ratio),
        },
    )
    thread = threading.Thread(
        target=_run_generate,
        args=(job_id, project_id, body, core),
        daemon=True,
        name=f"finetune-{job_id}",
    )
    thread.start()
    return {"job_id": job_id}


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> Dict[str, Any]:
    job = _reg.get_public(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> Dict[str, Any]:
    job = _reg.request_cancel(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{project_id}/jobs")
def list_jobs(project_id: str) -> Dict[str, Any]:
    _assert_project(project_id)
    return {"jobs": _reg.list_for_project(project_id)}
