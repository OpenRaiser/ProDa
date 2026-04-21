from __future__ import annotations

import json
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from backend.lib.jobs import JobRegistry
from proda.extractor import extract_knowledge_core
from ui.utils.document_loader import (
    chunk_text as _chunk_text,
    extract_json_paths,
    read_uploaded_file,
)
from ui.utils.project_store import (
    get_project as _get_project,
    load_project_state as _load_state,
    project_dir_path,
    save_project_state as _save_state,
)

router = APIRouter()
_reg = JobRegistry()


# -----------------------------
# File I/O helpers
# -----------------------------
class _FileHandle:
    """Mimic Streamlit's UploadedFile interface for read_uploaded_file."""

    def __init__(self, name: str, data: bytes) -> None:
        self.name = name
        self._data = data

    def getvalue(self) -> bytes:
        return self._data


def _uploads_dir(project_id: str) -> Path:
    d = project_dir_path(project_id) / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _assert_project(project_id: str) -> None:
    if not _get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")


# -----------------------------
# Upload
# -----------------------------
@router.post("/{project_id}/upload")
async def upload(project_id: str, files: List[UploadFile] = File(...)) -> Dict[str, Any]:
    _assert_project(project_id)
    dst = _uploads_dir(project_id)
    saved: List[Dict[str, Any]] = []
    for f in files:
        raw = await f.read()
        file_id = uuid.uuid4().hex[:12]
        safe_name = Path(f.filename or "upload").name
        target = dst / f"{file_id}__{safe_name}"
        target.write_bytes(raw)
        saved.append(
            {
                "file_id": file_id,
                "filename": safe_name,
                "size": len(raw),
                "ext": target.suffix.lower().lstrip("."),
                "stored_at": datetime.utcnow().isoformat(),
            }
        )
    return {"files": saved}


@router.get("/{project_id}/uploads")
def list_uploads(project_id: str) -> Dict[str, Any]:
    _assert_project(project_id)
    d = _uploads_dir(project_id)
    # Collect with mtime first, then sort by upload time (oldest first for
    # deterministic chronological display).
    entries: List[tuple] = []
    for p in d.iterdir():
        if not p.is_file() or "__" not in p.name:
            continue
        try:
            entries.append((p.stat().st_mtime, p))
        except OSError:
            continue
    entries.sort(key=lambda t: t[0])
    out: List[Dict[str, Any]] = []
    for mtime, p in entries:
        file_id, _, filename = p.name.partition("__")
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        out.append(
            {
                "file_id": file_id,
                "filename": filename,
                "size": size,
                "ext": p.suffix.lower().lstrip("."),
                "stored_at": datetime.utcfromtimestamp(mtime).isoformat(),
            }
        )
    return {"files": out}


@router.delete("/{project_id}/uploads/{file_id}")
def delete_upload(project_id: str, file_id: str) -> Dict[str, Any]:
    _assert_project(project_id)
    d = _uploads_dir(project_id)
    hit = False
    for p in d.iterdir():
        if p.is_file() and p.name.startswith(f"{file_id}__"):
            try:
                p.unlink()
                hit = True
            except OSError:
                pass
    if not hit:
        raise HTTPException(status_code=404, detail="Upload not found")
    return {"deleted": True}


def _find_upload(project_id: str, file_id: str) -> Path:
    d = _uploads_dir(project_id)
    for p in d.iterdir():
        if p.is_file() and p.name.startswith(f"{file_id}__"):
            return p
    raise HTTPException(status_code=404, detail=f"File {file_id} not found")


# -----------------------------
# JSON field inspection
# -----------------------------
class InspectJsonRequest(BaseModel):
    file_id: str


@router.post("/{project_id}/inspect-json")
def inspect_json(project_id: str, body: InspectJsonRequest) -> Dict[str, Any]:
    _assert_project(project_id)
    path = _find_upload(project_id, body.file_id)
    if path.suffix.lower() != ".json":
        raise HTTPException(status_code=400, detail="Not a JSON file")
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")
    paths = extract_json_paths(data)
    return {"paths": paths}


# -----------------------------
# Start job
# -----------------------------
class LlmCtx(BaseModel):
    provider: str
    model: str
    api_key: str
    api_base: str = ""


class StartExtractionRequest(BaseModel):
    file_ids: List[str]
    json_fields: List[str] = []
    chunk_size: int = 10000
    chunk_overlap: int = 800
    processing_mode: str = "auto"  # auto | merge | per_chunk
    merge_threshold: int = 16000
    parallel_chunks: bool = True
    max_workers: int = 4
    llm: LlmCtx


def _merge_cores(cores: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Port of the per-chunk merge logic from ui/pages/1_Data_Processing.py."""
    all_l1: List[Dict[str, Any]] = []
    all_l2: List[Dict[str, Any]] = []
    all_l3: List[Dict[str, Any]] = []
    total_chars = 0
    for core in cores:
        all_l1.extend(core.get("l1_concepts", []))
        all_l2.extend(core.get("l2_statements", []))
        all_l3.extend(core.get("l3_chains", []))
        total_chars += int((core.get("statistics") or {}).get("text_length", 0))

    def dedupe(items, key_fn):
        seen = set()
        out = []
        for item in items:
            key = key_fn(item)
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    all_l3 = dedupe(all_l3, lambda x: tuple(x.get("steps", [])))
    for i, row in enumerate(all_l3, start=1):
        row["chain_id"] = f"chain-{i:03d}"

    valid_ids = {row["chain_id"] for row in all_l3}
    all_l2 = dedupe(
        all_l2,
        lambda x: (
            str(x.get("subject", "")).lower(),
            str(x.get("predicate", "")).lower(),
            str(x.get("object", "")).lower(),
        ),
    )
    for i, row in enumerate(all_l2, start=1):
        if row.get("parent_chain_id") not in valid_ids:
            row["parent_chain_id"] = next(iter(valid_ids), "chain-001")
        row["statement_id"] = f"stmt-{i:03d}"

    all_l1 = dedupe(all_l1, lambda x: str(x.get("term", "")).lower())
    for i, row in enumerate(all_l1, start=1):
        row["concept_id"] = f"concept-{i:03d}"

    return {
        "l1_concepts": all_l1,
        "l2_statements": all_l2,
        "l3_chains": all_l3,
        "statistics": {
            "total_chains": len(all_l3),
            "total_statements": len(all_l2),
            "total_concepts": len(all_l1),
            "text_length": total_chars,
        },
    }


def _run_extraction(job_id: str, project_id: str, req: StartExtractionRequest) -> None:
    cancel_event = _reg.cancel_event(job_id)

    def canceled() -> bool:
        return cancel_event.is_set() if cancel_event else False

    try:
        _reg.update(job_id, status="running", message="Reading input files...", progress=2)

        texts: List[str] = []
        for fid in req.file_ids:
            if canceled():
                raise RuntimeError("Cancelled")
            path = _find_upload(project_id, fid)
            data = path.read_bytes()
            handle = _FileHandle(path.name.split("__", 1)[-1], data)
            content = read_uploaded_file(handle, req.json_fields)
            if content.strip():
                texts.append(content)
        merged_text = "\n\n".join(texts)
        if not merged_text.strip():
            raise RuntimeError("No text extracted from uploads")

        chunks = _chunk_text(
            merged_text,
            chunk_size=int(req.chunk_size),
            overlap=int(req.chunk_overlap),
        )
        effective_mode = req.processing_mode
        if effective_mode == "auto":
            effective_mode = (
                "merge"
                if len(merged_text) < int(req.merge_threshold) or len(chunks) <= 1
                else "per_chunk"
            )

        _reg.update(
            job_id,
            effective_mode=effective_mode,
            total=len(chunks),
            done=0,
            message=f"Mode: {effective_mode} · chunks: {len(chunks)}",
            progress=5,
        )

        llm = req.llm

        if effective_mode == "merge":
            if canceled():
                raise RuntimeError("Cancelled")
            core = extract_knowledge_core(
                text=merged_text,
                provider=llm.provider,
                model=llm.model,
                api_key=llm.api_key,
                api_base=llm.api_base,
            )
            if canceled():
                raise RuntimeError("Cancelled")
            core.setdefault("statistics", {})
            core["statistics"]["num_chunks"] = len(chunks)
            core["statistics"]["processing_mode"] = "merge"
            _persist_core(project_id, core)
            _reg.update(
                job_id,
                status="done",
                progress=100,
                done=len(chunks),
                message="Extraction complete",
                result=core,
            )
            return

        # per_chunk
        cores: List[Dict[str, Any]] = []
        total = max(1, len(chunks))

        if req.parallel_chunks and total > 1 and int(req.max_workers) > 1:
            results: Dict[int, Dict[str, Any]] = {}
            with ThreadPoolExecutor(max_workers=int(req.max_workers)) as ex:
                futures = {
                    ex.submit(
                        extract_knowledge_core,
                        chunk,
                        llm.provider,
                        llm.model,
                        llm.api_key,
                        llm.api_base,
                    ): i
                    for i, chunk in enumerate(chunks)
                }
                done_count = 0
                for fut in as_completed(futures):
                    if canceled():
                        for f in futures:
                            f.cancel()
                        raise RuntimeError("Cancelled")
                    idx = futures[fut]
                    try:
                        results[idx] = fut.result()
                    except Exception as exc:
                        raise RuntimeError(f"Chunk {idx + 1}/{total} failed: {exc}") from exc
                    done_count += 1
                    _reg.update(
                        job_id,
                        done=done_count,
                        progress=int(5 + 90 * done_count / total),
                        message=f"Extracting chunks: {done_count}/{total}",
                    )
            cores = [results[i] for i in range(total)]
        else:
            for idx, chunk in enumerate(chunks, start=1):
                if canceled():
                    raise RuntimeError("Cancelled")
                cores.append(
                    extract_knowledge_core(
                        text=chunk,
                        provider=llm.provider,
                        model=llm.model,
                        api_key=llm.api_key,
                        api_base=llm.api_base,
                    )
                )
                _reg.update(
                    job_id,
                    done=idx,
                    progress=int(5 + 90 * idx / total),
                    message=f"Extracting chunks: {idx}/{total}",
                )

        merged_core = _merge_cores(cores)
        merged_core.setdefault("statistics", {})
        merged_core["statistics"]["num_chunks"] = len(chunks)
        merged_core["statistics"]["processing_mode"] = "per_chunk"
        _persist_core(project_id, merged_core)
        _reg.update(
            job_id,
            status="done",
            progress=100,
            message="Extraction complete",
            result=merged_core,
        )
    except RuntimeError as exc:
        if str(exc) == "Cancelled":
            _reg.update(job_id, status="cancelled", message="Job cancelled by user")
        else:
            _reg.update(
                job_id,
                status="error",
                error=str(exc),
                message=f"Error: {exc}",
            )
    except Exception as exc:  # noqa: BLE001
        _reg.update(
            job_id,
            status="error",
            error=f"{exc}\n{traceback.format_exc()}",
            message=f"Error: {exc}",
        )


def _persist_core(project_id: str, core: Dict[str, Any]) -> None:
    state = _load_state(project_id)
    state["knowledge_core"] = core
    _save_state(project_id, state)


@router.post("/{project_id}/start")
def start_job(project_id: str, body: StartExtractionRequest) -> Dict[str, Any]:
    _assert_project(project_id)
    if not body.file_ids:
        raise HTTPException(status_code=400, detail="No files selected")
    if not body.llm.api_key:
        raise HTTPException(status_code=400, detail="LLM api_key is required")

    job_id = _reg.create(
        project_id,
        extra={"effective_mode": body.processing_mode},
    )
    thread = threading.Thread(
        target=_run_extraction,
        args=(job_id, project_id, body),
        daemon=True,
        name=f"extract-{job_id}",
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
