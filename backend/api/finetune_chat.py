"""Phase 5.5 — Chat with fine-tuned checkpoints (streaming)."""

from __future__ import annotations

import asyncio
import gc
import json
import threading
import time
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ui.utils.project_store import get_project as _get_project
from ui.utils.project_store import project_dir_path as _project_dir

router = APIRouter()


def _assert_project(project_id: str) -> Dict[str, Any]:
    project = _get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _history_path(project_id: str) -> Path:
    return _project_dir(project_id) / "finetune_exports" / "train_history.json"


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


def _load_history(project_id: str) -> List[Dict[str, Any]]:
    rows = _load_json(_history_path(project_id), [])
    data = [x for x in rows if isinstance(x, dict)] if isinstance(rows, list) else []
    data.sort(key=lambda r: int(r.get("started_at") or 0), reverse=True)
    return data


def _safe_path(path_text: str) -> Path:
    return Path(str(path_text or "")).expanduser().resolve()


def _pick_output_target(output_dir: Path, target_path: str) -> Path:
    if str(target_path or "").strip():
        return _safe_path(target_path)
    return _safe_path(str(output_dir))


def _checkpoint_entries(output_dir: Path) -> List[Dict[str, str]]:
    if not output_dir.exists() or not output_dir.is_dir():
        return []
    rows: List[Tuple[int, str, str]] = []
    for p in output_dir.iterdir():
        if not p.is_dir():
            continue
        name = p.name
        if not name.startswith("checkpoint-"):
            continue
        step = 0
        try:
            step = int(name.split("-", 1)[1])
        except Exception:
            step = 0
        rows.append((step, name, str(p.resolve())))
    rows.sort(key=lambda x: x[0], reverse=True)
    return [{"name": x[1], "path": x[2]} for x in rows]


def _human_time(unix_ts: int) -> str:
    if unix_ts <= 0:
        return ""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(unix_ts))


def _row_to_chat_candidate(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    session_id = str(row.get("session_id", "")).strip()
    if not session_id:
        return None
    output_dir = _safe_path(str(row.get("output_dir", "")))
    if not output_dir.exists():
        return None
    status = str(row.get("status", "") or "")
    finetuning_type = str(row.get("finetuning_type", "lora") or "lora").lower()
    started_at = int(row.get("started_at") or 0)
    base_model_path = str(row.get("model_path", "")).strip()
    model_tag = str(row.get("model_tag", "")).strip() or Path(base_model_path).name or "model"
    dataset_name = str(row.get("dataset_name", "")).strip() or "dataset"
    checkpoints = _checkpoint_entries(output_dir)
    label = f"{dataset_name} -> {model_tag} ({_human_time(started_at)})".strip()
    return {
        "session_id": session_id,
        "status": status,
        "started_at": started_at,
        "started_at_human": _human_time(started_at),
        "dataset_name": dataset_name,
        "model_tag": model_tag,
        "base_model_path": base_model_path,
        "finetuning_type": finetuning_type,
        "output_dir": str(output_dir),
        "default_target_path": str(output_dir),
        "checkpoints": checkpoints,
        "label": label,
    }


def _find_history_row(project_id: str, session_id: str) -> Dict[str, Any]:
    for row in _load_history(project_id):
        if str(row.get("session_id", "")) == str(session_id):
            return row
    raise HTTPException(status_code=404, detail=f"Training session not found: {session_id}")


def _resolve_load_target(project_id: str, session_id: str, target_path: str) -> Dict[str, Any]:
    row = _find_history_row(project_id, session_id)
    output_dir = _safe_path(str(row.get("output_dir", "")))
    project_root = _safe_path(str(_project_dir(project_id)))
    if not _is_within(output_dir, project_root):
        raise HTTPException(status_code=400, detail="output_dir outside project root")
    target = _pick_output_target(output_dir, target_path)
    if not _is_within(target, output_dir):
        raise HTTPException(status_code=400, detail="target_path must be output_dir or one of its checkpoints")
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"target_path not found: {target}")
    return {
        "row": row,
        "output_dir": output_dir,
        "target": target,
        "finetuning_type": str(row.get("finetuning_type", "lora") or "lora").lower(),
        "base_model_path": str(row.get("model_path", "")).strip(),
    }


def _build_prompt(messages: List[Dict[str, str]]) -> str:
    lines: List[str] = []
    for m in messages:
        role = str(m.get("role", "user")).strip().lower()
        content = str(m.get("content", "")).strip()
        if not content:
            continue
        if role == "system":
            lines.append(f"[System]\n{content}")
        elif role == "assistant":
            lines.append(f"[Assistant]\n{content}")
        else:
            lines.append(f"[User]\n{content}")
    lines.append("[Assistant]\n")
    return "\n\n".join(lines)


def _import_inference_deps() -> Tuple[Any, Any, Any, Any, Any, Any, Any]:
    try:
        import torch  # type: ignore
        from peft import PeftModel  # type: ignore
        from transformers import (  # type: ignore
            AutoModelForCausalLM,
            AutoTokenizer,
            StoppingCriteria,
            StoppingCriteriaList,
            TextIteratorStreamer,
        )

        return (
            torch,
            AutoTokenizer,
            AutoModelForCausalLM,
            TextIteratorStreamer,
            PeftModel,
            StoppingCriteria,
            StoppingCriteriaList,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Inference dependencies unavailable (torch/transformers/peft): {exc}",
        )


def _pick_dtype(torch_mod: Any) -> Any:
    if getattr(torch_mod.cuda, "is_available", lambda: False)():
        if getattr(torch_mod.cuda, "is_bf16_supported", lambda: False)():
            return torch_mod.bfloat16
        return torch_mod.float16
    return torch_mod.float32


def _model_signature(project_id: str, session_id: str, target: Path, base_model: str, finetune_type: str) -> str:
    return "|".join([project_id, session_id, str(target.resolve()), base_model, finetune_type])


_MODEL_STATE: Dict[str, Dict[str, Any]] = {}
_MODEL_STATE_LOCK = threading.Lock()


def _drop_project_model(project_id: str) -> bool:
    with _MODEL_STATE_LOCK:
        state = _MODEL_STATE.pop(project_id, None)
    if not state:
        return False
    try:
        model = state.get("model")
        tokenizer = state.get("tokenizer")
        del model
        del tokenizer
    except Exception:
        pass
    try:
        gc.collect()
    except Exception:
        pass
    try:
        import torch  # type: ignore

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass
    return True


def _load_model(project_id: str, session_id: str, target_path: str) -> Dict[str, Any]:
    payload = _resolve_load_target(project_id, session_id, target_path)
    row = payload["row"]
    target: Path = payload["target"]
    finetune_type = payload["finetuning_type"]
    base_model_path = payload["base_model_path"]

    if finetune_type in {"lora", "qlora"} and not base_model_path:
        raise HTTPException(status_code=400, detail="Missing base model path in history row")

    signature = _model_signature(
        project_id,
        session_id,
        target,
        base_model_path,
        finetune_type,
    )
    with _MODEL_STATE_LOCK:
        existing = _MODEL_STATE.get(project_id)
        if existing and str(existing.get("signature", "")) == signature:
            return {
                "already_loaded": True,
                "signature": signature,
                "session_id": session_id,
                "target_path": str(target),
                "finetuning_type": finetune_type,
            }
    _drop_project_model(project_id)

    torch_mod, AutoTokenizer, AutoModelForCausalLM, _, PeftModel, _, _ = _import_inference_deps()
    dtype = _pick_dtype(torch_mod)
    trust_remote_code = True

    if finetune_type in {"lora", "qlora"}:
        tokenizer = AutoTokenizer.from_pretrained(base_model_path, trust_remote_code=trust_remote_code)
        base_model = AutoModelForCausalLM.from_pretrained(
            base_model_path,
            torch_dtype=dtype,
            device_map="auto",
            trust_remote_code=trust_remote_code,
        )
        model = PeftModel.from_pretrained(base_model, str(target))
    else:
        tokenizer = AutoTokenizer.from_pretrained(str(target), trust_remote_code=trust_remote_code)
        model = AutoModelForCausalLM.from_pretrained(
            str(target),
            torch_dtype=dtype,
            device_map="auto",
            trust_remote_code=trust_remote_code,
        )

    if getattr(tokenizer, "pad_token_id", None) is None and getattr(tokenizer, "eos_token_id", None) is not None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    model.eval()
    lock = threading.Lock()
    with _MODEL_STATE_LOCK:
        _MODEL_STATE[project_id] = {
            "signature": signature,
            "session_id": session_id,
            "target_path": str(target),
            "finetuning_type": finetune_type,
            "base_model_path": base_model_path,
            "model": model,
            "tokenizer": tokenizer,
            "generate_lock": lock,
            "loaded_at": int(time.time()),
            "device": str(getattr(model, "device", "auto")),
            "dtype": str(dtype),
            "model_tag": str(row.get("model_tag", "")),
            "dataset_name": str(row.get("dataset_name", "")),
        }
    return {
        "already_loaded": False,
        "signature": signature,
        "session_id": session_id,
        "target_path": str(target),
        "finetuning_type": finetune_type,
    }


class ChatMessage(BaseModel):
    role: str = Field(default="user")
    content: str = Field(default="")


class LoadModelRequest(BaseModel):
    session_id: str
    target_path: str = ""


class ChatRequest(BaseModel):
    session_id: str
    target_path: str = ""
    messages: List[ChatMessage] = Field(default_factory=list)
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 50
    max_new_tokens: int = 512
    repetition_penalty: float = 1.0
    max_history_turns: int = 24
    max_context_chars: int = 24000


@router.get("/{project_id}/models")
def list_models(project_id: str) -> Dict[str, Any]:
    _assert_project(project_id)
    rows = _load_history(project_id)
    items: List[Dict[str, Any]] = []
    with _MODEL_STATE_LOCK:
        loaded_sig = str((_MODEL_STATE.get(project_id) or {}).get("signature", ""))
    for row in rows:
        if str(row.get("status", "")) != "finished":
            continue
        item = _row_to_chat_candidate(row)
        if not item:
            continue
        sig = _model_signature(
            project_id,
            item["session_id"],
            Path(item["default_target_path"]),
            item["base_model_path"],
            item["finetuning_type"],
        )
        item["is_loaded_default"] = loaded_sig == sig
        items.append(item)
    return {"items": items}


@router.post("/{project_id}/load")
def load_model(project_id: str, body: LoadModelRequest) -> Dict[str, Any]:
    _assert_project(project_id)
    result = _load_model(project_id, body.session_id, body.target_path)
    return {"ok": True, **result}


@router.post("/{project_id}/unload")
def unload_model(project_id: str) -> Dict[str, Any]:
    _assert_project(project_id)
    released = _drop_project_model(project_id)
    return {"ok": True, "released": released}


def _normalize_messages(messages: List[ChatMessage]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for m in messages:
        content = str(m.content or "").strip()
        if not content:
            continue
        role = str(m.role or "user").strip().lower()
        if role not in {"system", "user", "assistant"}:
            role = "user"
        rows.append({"role": role, "content": content})
    return rows


def _truncate_messages(
    rows: List[Dict[str, str]],
    max_history_turns: int,
    max_context_chars: int,
) -> Tuple[List[Dict[str, str]], int]:
    if not rows:
        return rows, 0

    max_history_turns = max(2, min(200, int(max_history_turns)))
    max_context_chars = max(400, min(200_000, int(max_context_chars)))

    system_rows = [x for x in rows if x.get("role") == "system"]
    non_system = [x for x in rows if x.get("role") != "system"]

    # Keep only latest turns (each turn can be user/assistant message pair in practice).
    if len(non_system) > max_history_turns:
        non_system = non_system[-max_history_turns:]

    kept = ([system_rows[-1]] if system_rows else []) + non_system
    total_chars = sum(len(str(x.get("content", ""))) for x in kept)
    dropped = max(0, len(rows) - len(kept))

    # Char-budget pass: drop from the oldest non-system first.
    while total_chars > max_context_chars:
        idx = -1
        for i, msg in enumerate(kept):
            if msg.get("role") != "system":
                idx = i
                break
        if idx < 0:
            break
        total_chars -= len(str(kept[idx].get("content", "")))
        kept.pop(idx)
        dropped += 1
    return kept, dropped


async def _stream_chat(project_id: str, body: ChatRequest) -> AsyncIterator[bytes]:
    if not body.messages:
        raise HTTPException(status_code=400, detail="messages is required")
    _load_model(project_id, body.session_id, body.target_path)

    with _MODEL_STATE_LOCK:
        state = _MODEL_STATE.get(project_id)
    if not state:
        raise HTTPException(status_code=500, detail="Model is not loaded")

    model = state.get("model")
    tokenizer = state.get("tokenizer")
    lock = state.get("generate_lock")
    if model is None or tokenizer is None or lock is None:
        raise HTTPException(status_code=500, detail="Invalid loaded model state")

    torch_mod, _, _, TextIteratorStreamer, _, StoppingCriteria, StoppingCriteriaList = _import_inference_deps()
    msgs_raw = _normalize_messages(body.messages)
    msgs, dropped_count = _truncate_messages(
        msgs_raw,
        max_history_turns=body.max_history_turns,
        max_context_chars=body.max_context_chars,
    )
    if not msgs:
        raise HTTPException(status_code=400, detail="messages has no valid content")

    try:
        prompt = tokenizer.apply_chat_template(
            msgs,
            tokenize=False,
            add_generation_prompt=True,
        )
    except Exception:
        prompt = _build_prompt(msgs)

    inputs = tokenizer(prompt, return_tensors="pt")
    model_device = getattr(model, "device", None)
    if model_device is not None:
        try:
            inputs = {k: v.to(model_device) for k, v in inputs.items()}
        except Exception:
            pass

    temperature = max(0.0, min(2.0, float(body.temperature)))
    top_p = max(0.01, min(1.0, float(body.top_p)))
    top_k = max(0, int(body.top_k))
    max_new_tokens = max(1, min(4096, int(body.max_new_tokens)))
    repetition_penalty = max(0.8, min(2.0, float(body.repetition_penalty)))
    do_sample = temperature > 1e-5

    streamer = TextIteratorStreamer(
        tokenizer,
        skip_prompt=True,
        skip_special_tokens=True,
    )
    stop_event = threading.Event()

    class _StopCriteria(StoppingCriteria):
        def __call__(self, input_ids: Any, scores: Any, **kwargs: Any) -> bool:
            return stop_event.is_set()

    gen_kwargs: Dict[str, Any] = {
        **inputs,
        "max_new_tokens": max_new_tokens,
        "repetition_penalty": repetition_penalty,
        "streamer": streamer,
        "stopping_criteria": StoppingCriteriaList([_StopCriteria()]),
    }
    if do_sample:
        gen_kwargs.update(
            {
                "do_sample": True,
                "temperature": temperature,
                "top_p": top_p,
            }
        )
        if top_k > 0:
            gen_kwargs["top_k"] = top_k
    else:
        gen_kwargs["do_sample"] = False

    error_box: Dict[str, str] = {}

    def _runner() -> None:
        with lock:
            try:
                model.generate(**gen_kwargs)
            except Exception as exc:
                error_box["error"] = str(exc)

    with _MODEL_STATE_LOCK:
        current_state = _MODEL_STATE.get(project_id) or {}
        current_state["active_stop_event"] = stop_event
        _MODEL_STATE[project_id] = current_state

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()

    try:
        yield b": connected\n\n"
        if dropped_count > 0:
            payload = json.dumps({"dropped_messages": dropped_count}, ensure_ascii=False)
            yield f"event: meta\ndata: {payload}\n\n".encode("utf-8")
        while True:
            if error_box.get("error"):
                msg = json.dumps({"error": error_box["error"]}, ensure_ascii=False)
                yield f"event: error\ndata: {msg}\n\n".encode("utf-8")
                return
            try:
                piece = next(streamer)
                if piece:
                    payload = json.dumps({"token": piece}, ensure_ascii=False)
                    yield f"data: {payload}\n\n".encode("utf-8")
                await asyncio.sleep(0)
            except StopIteration:
                break
            except Exception as exc:
                payload = json.dumps({"error": str(exc)}, ensure_ascii=False)
                yield f"event: error\ndata: {payload}\n\n".encode("utf-8")
                return

        thread.join(timeout=0.2)
        if error_box.get("error"):
            msg = json.dumps({"error": error_box["error"]}, ensure_ascii=False)
            yield f"event: error\ndata: {msg}\n\n".encode("utf-8")
            return
        stopped = stop_event.is_set()
        yield f"event: end\ndata: {'stopped' if stopped else 'done'}\n\n".encode("utf-8")
    finally:
        with _MODEL_STATE_LOCK:
            state2 = _MODEL_STATE.get(project_id)
            if state2 is not None:
                state2.pop("active_stop_event", None)


@router.post("/{project_id}/chat/stop")
def stop_chat(project_id: str) -> Dict[str, Any]:
    _assert_project(project_id)
    stopped = False
    with _MODEL_STATE_LOCK:
        state = _MODEL_STATE.get(project_id) or {}
        event_obj = state.get("active_stop_event")
        if event_obj is not None:
            try:
                event_obj.set()
                stopped = True
            except Exception:
                stopped = False
    return {"ok": True, "stopped": stopped}


@router.post("/{project_id}/chat/stream")
async def chat_stream(project_id: str, body: ChatRequest) -> StreamingResponse:
    _assert_project(project_id)
    return StreamingResponse(
        _stream_chat(project_id, body),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
