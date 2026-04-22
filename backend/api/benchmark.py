from __future__ import annotations

import threading
import traceback
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.lib.jobs import JobRegistry
from proda.benchmark_generator import generate_benchmark_mcq
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


class StartBenchmarkRequest(BaseModel):
    max_workers: int = 4
    questions_per_chain: int = 5
    temperature: float = 0.3
    retries: int = 2
    max_refill_rounds: int = 4
    adaptive_concurrency: bool = True
    resume: bool = False
    llm: LlmCtx


def _assert_project(project_id: str) -> Dict[str, Any]:
    project = _get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _run_benchmark(
    job_id: str,
    project_id: str,
    req: StartBenchmarkRequest,
    l3_chains: List[Dict[str, Any]],
) -> None:
    cancel_event = _reg.cancel_event(job_id)

    target_total = max(1, len(l3_chains) * max(1, int(req.questions_per_chain)))

    # Load existing MCQs when resuming
    existing_mcqs: List[Dict[str, Any]] = []
    if req.resume:
        state_snap = _load_state(project_id)
        existing_mcqs = list(state_snap.get("benchmark_mcq") or [])

    # Compute how many valid questions we already have (capped per chain)
    pre_done = 0
    if existing_mcqs:
        from collections import Counter
        chain_counts: Counter = Counter(
            str(m.get("chain_id", "")) for m in existing_mcqs
        )
        for cnt in chain_counts.values():
            pre_done += min(cnt, int(req.questions_per_chain))
        pre_done = min(pre_done, target_total)

    def on_progress(done: int, total: int) -> None:
        t = max(1, int(total))
        d = int(max(0, min(done, t)))
        _reg.update(
            job_id,
            total=t,
            done=d,
            progress=int(d * 100 / t),
            message=f"Generating MCQs: {d}/{t}",
        )

    try:
        _reg.update(
            job_id,
            status="running",
            message=(
                f"Resuming benchmark · {pre_done}/{target_total} already done"
                if req.resume and pre_done > 0
                else f"Starting benchmark generation on {len(l3_chains)} chains..."
            ),
            total=target_total,
            done=pre_done,
            progress=int(pre_done * 100 / target_total),
        )
        rows = generate_benchmark_mcq(
            l3_chains=l3_chains,
            provider=req.llm.provider,
            model=req.llm.model,
            api_key=req.llm.api_key,
            api_base=req.llm.api_base,
            max_workers=int(req.max_workers),
            questions_per_chain=int(req.questions_per_chain),
            temperature=float(req.temperature),
            retries=int(req.retries),
            max_refill_rounds=int(req.max_refill_rounds),
            adaptive_concurrency=bool(req.adaptive_concurrency),
            existing_mcqs=existing_mcqs if existing_mcqs else None,
            progress_callback=on_progress,
            cancel_event=cancel_event,
        )
        stats = getattr(generate_benchmark_mcq, "last_run_stats", {}) or {}

        state = _load_state(project_id)
        state["benchmark_mcq"] = list(rows or [])
        _save_state(project_id, state)

        if stats.get("cancelled"):
            _reg.update(
                job_id,
                status="cancelled",
                progress=100,
                message=f"Cancelled · kept {len(rows)} MCQs",
                result={"mcqs": list(rows or []), "stats": stats},
            )
        else:
            _reg.update(
                job_id,
                status="done",
                progress=100,
                message=f"Done · {len(rows)} MCQs",
                result={"mcqs": list(rows or []), "stats": stats},
            )
    except Exception as exc:  # noqa: BLE001
        _reg.update(
            job_id,
            status="error",
            error=f"{exc}\n{traceback.format_exc()}",
            message=f"Error: {exc}",
        )


@router.post("/{project_id}/start")
def start_job(project_id: str, body: StartBenchmarkRequest) -> Dict[str, Any]:
    _assert_project(project_id)
    if not body.llm.api_key:
        raise HTTPException(status_code=400, detail="LLM api_key is required")

    state = _load_state(project_id)
    core = state.get("knowledge_core") or {}
    l3_chains = core.get("l3_chains") or []
    if not l3_chains:
        raise HTTPException(
            status_code=400,
            detail="No L3 chains. Run Step 1 (Data Processing) first.",
        )

    job_id = _reg.create(
        project_id,
        extra={
            "chains": len(l3_chains),
            "questions_per_chain": int(body.questions_per_chain),
        },
    )
    thread = threading.Thread(
        target=_run_benchmark,
        args=(job_id, project_id, body, l3_chains),
        daemon=True,
        name=f"benchmark-{job_id}",
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
