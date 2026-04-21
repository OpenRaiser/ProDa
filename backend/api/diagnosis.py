from __future__ import annotations

import json
import re
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from backend.lib.jobs import JobRegistry
from proda.diagnosis import generate_diagnostic_report
from proda.diagnosis_supplement import (
    generate_diagnostic_training_data,
    merge_diagnostic_with_original,
)
from ui.utils.project_store import (
    get_project as _get_project,
    load_project_state as _load_state,
    project_dir_path as _project_dir,
    save_project_state as _save_state,
)

router = APIRouter()
_reg = JobRegistry()

_SAFE_ID = re.compile(r"[^A-Za-z0-9_\-]")


class LlmCtx(BaseModel):
    provider: str
    model: str
    api_key: str
    api_base: str = ""


# --------- path helpers ---------
def _assert_project(project_id: str) -> Dict[str, Any]:
    project = _get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _diagnosis_root(project_id: str) -> Path:
    return _project_dir(project_id) / "diagnosis"


def _reports_dir(project_id: str) -> Path:
    return _diagnosis_root(project_id) / "reports"


def _supplement_root(project_id: str) -> Path:
    return _diagnosis_root(project_id) / "supplements"


def _diagnosis_history_path(project_id: str) -> Path:
    return _diagnosis_root(project_id) / "history.json"


def _supplement_history_path(project_id: str) -> Path:
    return _supplement_root(project_id) / "history.json"


def _opencompass_root(project_id: str) -> Path:
    return _project_dir(project_id) / "evaluations" / "opencompass"


def _opencompass_history_path(project_id: str) -> Path:
    return _opencompass_root(project_id) / "history.json"


def _flow_state_path(project_id: str) -> Path:
    return _project_dir(project_id) / "workflow" / "second_round_flow.json"


def _uploaded_eval_dir(project_id: str) -> Path:
    return _diagnosis_root(project_id) / "uploaded_evals"


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


def _safe_id(value: str) -> str:
    cleaned = _SAFE_ID.sub("_", str(value or "").strip())
    return cleaned or datetime.utcnow().strftime("%Y%m%d_%H%M%S")


def _is_within(path: Path, root: Path) -> bool:
    try:
        p = path.resolve()
        r = root.resolve()
        return p == r or r in p.parents
    except Exception:
        return False


# --------- 1. OpenCompass runs (history + uploaded fallback) ---------
@router.get("/{project_id}/opencompass-runs")
def list_opencompass_runs(project_id: str) -> Dict[str, Any]:
    _assert_project(project_id)

    runs: List[Dict[str, Any]] = []
    history = _load_json(_opencompass_history_path(project_id), [])
    if isinstance(history, list):
        for item in history:
            if not isinstance(item, dict):
                continue
            runs.append(
                {
                    "source": "opencompass",
                    "run_id": str(item.get("run_id", "")),
                    "created_at": str(item.get("created_at", "")),
                    "success": bool(item.get("success", False)),
                    "result_file": str(item.get("result_file", "")),
                }
            )

    uploaded_dir = _uploaded_eval_dir(project_id)
    if uploaded_dir.exists():
        for f in sorted(uploaded_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            runs.append(
                {
                    "source": "uploaded",
                    "run_id": f.stem,
                    "created_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                    "success": True,
                    "result_file": str(f),
                }
            )

    runs.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
    return {"runs": runs}


@router.post("/{project_id}/upload-eval")
async def upload_eval(project_id: str, file: UploadFile = File(...)) -> Dict[str, Any]:
    _assert_project(project_id)
    if not file.filename or not file.filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="Only .json files are accepted")

    raw = await file.read()
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")

    if not isinstance(payload, dict) or "models" not in payload:
        raise HTTPException(
            status_code=400,
            detail="Eval JSON must be an object with a 'models' array",
        )

    dest_dir = _uploaded_eval_dir(project_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_id(Path(file.filename).stem)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    dest = dest_dir / f"{stem}_{ts}.json"
    _save_json(dest, payload)

    return {
        "source": "uploaded",
        "run_id": dest.stem,
        "result_file": str(dest),
        "created_at": datetime.utcnow().isoformat(),
    }


@router.get("/{project_id}/eval-models")
def get_eval_models(project_id: str, result_file: str) -> Dict[str, Any]:
    _assert_project(project_id)

    path = Path(result_file).expanduser()
    allowed_roots = [_opencompass_root(project_id), _uploaded_eval_dir(project_id)]
    if not any(_is_within(path, root) for root in allowed_roots):
        raise HTTPException(status_code=400, detail="result_file is outside allowed roots")
    if not path.exists():
        raise HTTPException(status_code=404, detail="result_file not found")

    payload = _load_json(path, {})
    models = payload.get("models", []) if isinstance(payload, dict) else []
    out: List[Dict[str, Any]] = []
    for m in models:
        if not isinstance(m, dict):
            continue
        if not m.get("enabled", True) or not m.get("is_local", False):
            continue
        abbr = str(m.get("abbr", "")).strip()
        if not abbr:
            continue
        out.append({"abbr": abbr, "is_local": True, "enabled": True})
    return {"models": out}


# --------- 2. Diagnostic report job ---------
class StartReportRequest(BaseModel):
    result_file: str
    target_model_abbr: str
    run_id: str
    max_diagnose: int = 0
    max_workers: int = 8
    temperature: float = 0.2
    max_tokens: int = 1024
    retries: int = 3
    llm: LlmCtx


def _run_report(job_id: str, project_id: str, req: StartReportRequest) -> None:
    try:
        _reg.update(
            job_id,
            status="running",
            message="Loading eval payload...",
            progress=2,
        )

        result_path = Path(req.result_file).expanduser()
        allowed = [_opencompass_root(project_id), _uploaded_eval_dir(project_id)]
        if not any(_is_within(result_path, root) for root in allowed):
            raise RuntimeError("result_file is outside allowed roots")
        if not result_path.exists():
            raise RuntimeError(f"result_file not found: {result_path}")
        eval_payload = _load_json(result_path, {})

        def on_progress(done: int, total: int) -> None:
            t = max(1, int(total))
            d = int(max(0, min(done, t)))
            _reg.update(
                job_id,
                total=t,
                done=d,
                progress=int(d * 100 / t),
                message=f"Diagnosing: {d}/{t}",
            )

        report = generate_diagnostic_report(
            eval_payload=eval_payload,
            target_model_abbr=req.target_model_abbr,
            provider=req.llm.provider,
            model=req.llm.model,
            api_key=req.llm.api_key,
            api_base=req.llm.api_base,
            max_diagnose=int(req.max_diagnose),
            max_workers=int(req.max_workers),
            temperature=float(req.temperature),
            max_tokens=int(req.max_tokens),
            retries=int(req.retries),
            progress_callback=on_progress,
        )

        reports_dir = _reports_dir(project_id)
        reports_dir.mkdir(parents=True, exist_ok=True)
        run_tag = _safe_id(req.run_id or "run")
        model_tag = _safe_id(req.target_model_abbr)
        ts = str(report.get("timestamp", datetime.utcnow().strftime("%Y%m%d_%H%M%S")))
        report_id = f"diagnostic_report_{run_tag}_{model_tag}_{ts}"
        report_path = reports_dir / f"{report_id}.json"
        _save_json(report_path, report)

        history = _load_json(_diagnosis_history_path(project_id), [])
        if not isinstance(history, list):
            history = []
        history.append(
            {
                "report_id": report_id,
                "run_id": req.run_id,
                "model_name": req.target_model_abbr,
                "created_at": datetime.utcnow().isoformat(),
                "report_file": str(report_path),
                "accuracy": float(report.get("accuracy", 0.0)),
                "total_samples": int(report.get("total_samples", 0)),
                "error_samples_count": int(report.get("error_samples_count", 0)),
                "diagnosis_model": f"{req.llm.provider}::{req.llm.model}",
            }
        )
        _save_json(_diagnosis_history_path(project_id), history)

        ev = _reg.cancel_event(job_id)
        is_cancelled = bool(ev and ev.is_set())
        _reg.update(
            job_id,
            status="cancelled" if is_cancelled else "done",
            progress=100,
            message=(
                f"Cancelled · report saved ({report_id})"
                if is_cancelled
                else f"Done · {report_id}"
            ),
            result={
                "report_id": report_id,
                "report_file": str(report_path),
                "accuracy": float(report.get("accuracy", 0.0)),
                "total_samples": int(report.get("total_samples", 0)),
                "error_samples_count": int(report.get("error_samples_count", 0)),
            },
        )
    except Exception as exc:  # noqa: BLE001
        _reg.update(
            job_id,
            status="error",
            error=f"{exc}\n{traceback.format_exc()}",
            message=f"Error: {exc}",
        )


@router.post("/{project_id}/reports/start")
def start_report(project_id: str, body: StartReportRequest) -> Dict[str, Any]:
    _assert_project(project_id)
    if not body.llm.api_key:
        raise HTTPException(status_code=400, detail="LLM api_key is required")
    if not body.target_model_abbr.strip():
        raise HTTPException(status_code=400, detail="target_model_abbr is required")
    if not body.result_file.strip():
        raise HTTPException(status_code=400, detail="result_file is required")

    job_id = _reg.create(
        project_id,
        extra={
            "kind": "report",
            "target_model": body.target_model_abbr,
            "run_id": body.run_id,
        },
    )
    thread = threading.Thread(
        target=_run_report,
        args=(job_id, project_id, body),
        daemon=True,
        name=f"diag-report-{job_id}",
    )
    thread.start()
    return {"job_id": job_id}


@router.get("/{project_id}/reports")
def list_reports(project_id: str) -> Dict[str, Any]:
    _assert_project(project_id)
    history = _load_json(_diagnosis_history_path(project_id), [])
    if not isinstance(history, list):
        return {"reports": []}
    items = [x for x in history if isinstance(x, dict) and str(x.get("report_id", "")).strip()]
    items.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
    return {"reports": items}


@router.get("/{project_id}/reports/{report_id}")
def get_report(project_id: str, report_id: str) -> Dict[str, Any]:
    _assert_project(project_id)
    history = _load_json(_diagnosis_history_path(project_id), [])
    if not isinstance(history, list):
        raise HTTPException(status_code=404, detail="Report not found")
    for item in history:
        if isinstance(item, dict) and str(item.get("report_id", "")) == report_id:
            report_path = Path(str(item.get("report_file", "")))
            if not _is_within(report_path, _reports_dir(project_id)):
                raise HTTPException(status_code=400, detail="report_file outside allowed root")
            if not report_path.exists():
                raise HTTPException(status_code=404, detail="report file missing on disk")
            return {"summary": item, "report": _load_json(report_path, {})}
    raise HTTPException(status_code=404, detail="Report not found")


@router.delete("/{project_id}/reports/{report_id}")
def delete_report(project_id: str, report_id: str) -> Dict[str, Any]:
    _assert_project(project_id)
    history = _load_json(_diagnosis_history_path(project_id), [])
    if not isinstance(history, list):
        history = []
    remained: List[Dict[str, Any]] = []
    deleted = False
    for item in history:
        if isinstance(item, dict) and str(item.get("report_id", "")) == report_id and not deleted:
            deleted = True
            path = Path(str(item.get("report_file", "")))
            if _is_within(path, _reports_dir(project_id)) and path.exists():
                try:
                    path.unlink()
                except Exception:
                    pass
            continue
        remained.append(item)
    if not deleted:
        raise HTTPException(status_code=404, detail="Report not found")
    _save_json(_diagnosis_history_path(project_id), remained)
    return {"deleted": True, "report_id": report_id}


# --------- 3. Supplement job ---------
class IssueWindows(BaseModel):
    qa: int = 0
    choice: int = 0
    tf: int = 0


class StartSupplementRequest(BaseModel):
    report_id: str
    max_error_samples: int = 300
    max_workers: int = 6
    max_tokens: int = 2048
    retries: int = 2
    concept_gap: IssueWindows = IssueWindows(qa=4, choice=2, tf=1)
    capability_deficit: IssueWindows = IssueWindows(qa=3, choice=3, tf=1)
    llm: LlmCtx


def _summarize_types(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {"qa": 0, "choice": 0, "tf": 0}
    for row in rows:
        if not isinstance(row, dict):
            continue
        qtype = str(row.get("question_type", "")).strip()
        if qtype == "qa":
            counts["qa"] += 1
        elif qtype in {"single_choice", "multiple_choice"}:
            counts["choice"] += 1
        elif qtype == "true_false":
            counts["tf"] += 1
    return counts


def _run_supplement(
    job_id: str,
    project_id: str,
    req: StartSupplementRequest,
    report_history_item: Dict[str, Any],
) -> None:
    try:
        _reg.update(job_id, status="running", message="Loading report...", progress=2)

        report_path = Path(str(report_history_item.get("report_file", "")))
        if not _is_within(report_path, _reports_dir(project_id)) or not report_path.exists():
            raise RuntimeError("Diagnostic report file is missing or outside allowed root")
        report = _load_json(report_path, {})
        if not isinstance(report, dict) or not report:
            raise RuntimeError("Diagnostic report is empty")

        def on_progress(done: int, total: int) -> None:
            t = max(1, int(total))
            d = int(max(0, min(done, t)))
            _reg.update(
                job_id,
                total=t,
                done=d,
                progress=int(d * 100 / t),
                message=f"Generating supplement: {d}/{t}",
            )

        issue_windows = {
            "concept_gap": {
                "qa": int(req.concept_gap.qa),
                "choice": int(req.concept_gap.choice),
                "tf": int(req.concept_gap.tf),
            },
            "capability_deficit": {
                "qa": int(req.capability_deficit.qa),
                "choice": int(req.capability_deficit.choice),
                "tf": int(req.capability_deficit.tf),
            },
        }

        rows, stats = generate_diagnostic_training_data(
            diagnostic_report=report,
            provider=req.llm.provider,
            model=req.llm.model,
            api_key=req.llm.api_key,
            api_base=req.llm.api_base,
            issue_windows=issue_windows,
            max_error_samples=int(req.max_error_samples),
            max_workers=int(req.max_workers),
            max_tokens=int(req.max_tokens),
            retries=int(req.retries),
            progress_callback=on_progress,
        )

        type_counts = _summarize_types(rows or [])
        stats = dict(stats or {})
        stats["type_counts"] = type_counts

        ds_root = _supplement_root(project_id)
        ds_root.mkdir(parents=True, exist_ok=True)
        dataset_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        data_file = ds_root / f"diagnostic_sft_{dataset_id}.json"
        _save_json(data_file, list(rows or []))

        history = _load_json(_supplement_history_path(project_id), [])
        if not isinstance(history, list):
            history = []
        entry = {
            "dataset_id": dataset_id,
            "created_at": datetime.utcnow().isoformat(),
            "report_id": req.report_id,
            "report_file": str(report_path),
            "report_created_at": str(report_history_item.get("created_at", "")),
            "data_file": str(data_file),
            "row_count": int(len(rows or [])),
            "issue_windows": issue_windows,
            "stats": stats,
        }
        history.append(entry)
        _save_json(_supplement_history_path(project_id), history)

        ev = _reg.cancel_event(job_id)
        is_cancelled = bool(ev and ev.is_set())
        _reg.update(
            job_id,
            status="cancelled" if is_cancelled else "done",
            progress=100,
            message=(
                f"Cancelled · saved dataset {dataset_id} ({len(rows or [])} rows)"
                if is_cancelled
                else f"Done · {len(rows or [])} rows · dataset {dataset_id}"
            ),
            result=entry,
        )
    except Exception as exc:  # noqa: BLE001
        _reg.update(
            job_id,
            status="error",
            error=f"{exc}\n{traceback.format_exc()}",
            message=f"Error: {exc}",
        )


@router.post("/{project_id}/supplements/start")
def start_supplement(project_id: str, body: StartSupplementRequest) -> Dict[str, Any]:
    _assert_project(project_id)
    if not body.llm.api_key:
        raise HTTPException(status_code=400, detail="LLM api_key is required")

    history = _load_json(_diagnosis_history_path(project_id), [])
    report_item: Optional[Dict[str, Any]] = None
    if isinstance(history, list):
        for item in history:
            if isinstance(item, dict) and str(item.get("report_id", "")) == body.report_id:
                report_item = item
                break
    if not report_item:
        raise HTTPException(status_code=404, detail="Report not found")

    job_id = _reg.create(
        project_id,
        extra={"kind": "supplement", "report_id": body.report_id},
    )
    thread = threading.Thread(
        target=_run_supplement,
        args=(job_id, project_id, body, report_item),
        daemon=True,
        name=f"diag-supplement-{job_id}",
    )
    thread.start()
    return {"job_id": job_id}


@router.get("/{project_id}/supplements")
def list_supplements(project_id: str) -> Dict[str, Any]:
    _assert_project(project_id)
    history = _load_json(_supplement_history_path(project_id), [])
    if not isinstance(history, list):
        return {"supplements": []}
    items = [x for x in history if isinstance(x, dict) and str(x.get("dataset_id", "")).strip()]
    items.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
    return {"supplements": items}


@router.get("/{project_id}/supplements/{dataset_id}")
def get_supplement(
    project_id: str,
    dataset_id: str,
    limit: int = 100,
) -> Dict[str, Any]:
    _assert_project(project_id)
    history = _load_json(_supplement_history_path(project_id), [])
    if not isinstance(history, list):
        raise HTTPException(status_code=404, detail="Supplement not found")
    for item in history:
        if isinstance(item, dict) and str(item.get("dataset_id", "")) == dataset_id:
            data_path = Path(str(item.get("data_file", "")))
            if not _is_within(data_path, _supplement_root(project_id)):
                raise HTTPException(status_code=400, detail="data_file outside allowed root")
            if not data_path.exists():
                raise HTTPException(status_code=404, detail="data_file missing on disk")
            all_rows = _load_json(data_path, [])
            if not isinstance(all_rows, list):
                all_rows = []
            preview = all_rows[: max(0, int(limit))]
            return {
                "summary": item,
                "preview": preview,
                "total": len(all_rows),
            }
    raise HTTPException(status_code=404, detail="Supplement not found")


@router.delete("/{project_id}/supplements/{dataset_id}")
def delete_supplement(project_id: str, dataset_id: str) -> Dict[str, Any]:
    _assert_project(project_id)
    history = _load_json(_supplement_history_path(project_id), [])
    if not isinstance(history, list):
        history = []
    remained: List[Dict[str, Any]] = []
    deleted = False
    for item in history:
        if isinstance(item, dict) and str(item.get("dataset_id", "")) == dataset_id and not deleted:
            deleted = True
            path = Path(str(item.get("data_file", "")))
            if _is_within(path, _supplement_root(project_id)) and path.exists():
                try:
                    path.unlink()
                except Exception:
                    pass
            continue
        remained.append(item)
    if not deleted:
        raise HTTPException(status_code=404, detail="Supplement not found")
    _save_json(_supplement_history_path(project_id), remained)
    return {"deleted": True, "dataset_id": dataset_id}


# --------- 4. Merge (synchronous) ---------
class MergeRequest(BaseModel):
    dataset_id: str
    target_total: int = 1000
    diagnostic_ratio: float = 0.35
    mix_with_original: bool = True
    exclude_same_l2: bool = True
    fallback_random_if_insufficient: bool = True
    random_seed: int = 42


@router.post("/{project_id}/merge")
def merge(project_id: str, body: MergeRequest) -> Dict[str, Any]:
    _assert_project(project_id)

    history = _load_json(_supplement_history_path(project_id), [])
    sup_item: Optional[Dict[str, Any]] = None
    if isinstance(history, list):
        for item in history:
            if isinstance(item, dict) and str(item.get("dataset_id", "")) == body.dataset_id:
                sup_item = item
                break
    if not sup_item:
        raise HTTPException(status_code=404, detail="Supplement dataset not found")

    data_path = Path(str(sup_item.get("data_file", "")))
    if not _is_within(data_path, _supplement_root(project_id)) or not data_path.exists():
        raise HTTPException(status_code=400, detail="Supplement data_file missing or outside allowed root")
    diag_rows = _load_json(data_path, [])
    if not isinstance(diag_rows, list):
        diag_rows = []

    state = _load_state(project_id)
    original_rows = list(state.get("finetune_data", []) or [])

    merged_rows, merge_stats = merge_diagnostic_with_original(
        diagnostic_rows=diag_rows,
        original_rows=original_rows,
        target_total=int(body.target_total),
        diagnostic_ratio=float(body.diagnostic_ratio),
        mix_with_original=bool(body.mix_with_original),
        exclude_same_l2=bool(body.exclude_same_l2),
        fallback_random_if_insufficient=bool(body.fallback_random_if_insufficient),
        random_seed=int(body.random_seed),
    )

    state["finetune_data"] = list(merged_rows)
    _save_state(project_id, state)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    merged_file = _supplement_root(project_id) / f"merged_finetune_{ts}.json"
    _save_json(merged_file, list(merged_rows))

    flow_state = _load_json(_flow_state_path(project_id), {})
    if not isinstance(flow_state, dict):
        flow_state = {}
    flow_state.update(
        {
            "merged_ready": True,
            "merged_at": datetime.utcnow().isoformat(),
            "merged_rows": int(len(merged_rows)),
            "merged_file": str(merged_file),
            "source_dataset_id": body.dataset_id,
            "source_report_id": str(sup_item.get("report_id", "")),
        }
    )
    _save_json(_flow_state_path(project_id), flow_state)

    return {
        "merged_file": str(merged_file),
        "merged_count": len(merged_rows),
        "stats": merge_stats,
        "flow_state": flow_state,
    }


# --------- 5. Flow state ---------
@router.get("/{project_id}/flow-state")
def get_flow_state(project_id: str) -> Dict[str, Any]:
    _assert_project(project_id)
    payload = _load_json(_flow_state_path(project_id), {})
    if not isinstance(payload, dict):
        payload = {}
    return {"flow_state": payload}


# --------- 6. Job endpoints (shared) ---------
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
