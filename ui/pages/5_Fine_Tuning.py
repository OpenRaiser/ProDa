from __future__ import annotations

import json
import html
import os
import re
import signal
import socket
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ui.components.top_bar import render_top_bar  # noqa: E402
from ui.utils.i18n_helper import init_i18n, t  # noqa: E402
from ui.utils.project_store import project_dir_path  # noqa: E402
from ui.utils.session_state import SessionStateManager  # noqa: E402
from ui.utils.ui_helpers import enforce_active_project, render_workflow_sidebar  # noqa: E402


st.set_page_config(page_title="ProDA", page_icon="📘", layout="wide")

MODEL_ROOT = project_root / "Model"


def _list_local_models(root: Path) -> List[str]:
    if not root.exists():
        return []
    results: List[str] = []
    for p in root.rglob("*"):
        if p.is_dir() and any((p / x).exists() for x in ["config.json", "tokenizer.json", "tokenizer_config.json"]):
            results.append(str(p))
    # remove nested duplicates: keep shorter path first
    results = sorted(set(results), key=lambda x: len(x))
    filtered: List[str] = []
    for path in results:
        if not any(path.startswith(parent + "/") for parent in filtered):
            filtered.append(path)
    return filtered


def _format_choice_options(options: Any) -> str:
    def _strip_label(text: str) -> str:
        return re.sub(r"^\s*[A-Da-d][\.\):\s-]+", "", text.strip())

    if isinstance(options, dict):
        lines = [f"{k}. {_strip_label(str(v))}" for k, v in sorted(options.items())]
        return "\n".join(lines)
    if isinstance(options, list):
        lines = []
        for i, opt in enumerate(options):
            lines.append(f"{chr(65 + i)}. {_strip_label(str(opt))}")
        return "\n".join(lines)
    return ""


def _question_has_options(question: str) -> bool:
    patterns = [
        r"(?m)^\s*A[\.\):\s-]+",
        r"(?m)^\s*B[\.\):\s-]+",
        r"(?m)^\s*C[\.\):\s-]+",
        r"(?m)^\s*D[\.\):\s-]+",
    ]
    return all(re.search(p, question) for p in patterns)


def _extract_choice_answer_explanation(answer: str, explanation: str) -> Tuple[str, str]:
    text = answer.strip()
    # pull letters from "Answer: A,B" style if needed
    m = re.search(r"([A-D](?:\s*,\s*[A-D])*)", text.upper())
    letters = m.group(1).replace(" ", "") if m else ""
    if not letters:
        letters = text.replace(" ", "").upper()
    if "EXPLANATION:" in text.upper():
        parts = re.split(r"(?i)explanation\s*:\s*", text, maxsplit=1)
        if len(parts) == 2:
            explanation = parts[1].strip() or explanation
            if not re.search(r"[A-D]", letters):
                lm = re.search(r"([A-D](?:\s*,\s*[A-D])*)", parts[0].upper())
                if lm:
                    letters = lm.group(1).replace(" ", "")
    letters = ",".join([x for x in letters.split(",") if x in {"A", "B", "C", "D"}])
    return letters or "A", explanation.strip()


def _extract_tf_answer_explanation(answer: str, explanation: str) -> Tuple[str, str]:
    text = answer.strip()
    lower = text.lower()
    if re.search(r"\bfalse\b", lower):
        label = "B"
    elif re.search(r"\btrue\b", lower):
        label = "A"
    elif re.search(r"\bjudgment\s*:\s*b\b", lower):
        label = "B"
    elif re.search(r"\bjudgment\s*:\s*a\b", lower):
        label = "A"
    elif text.strip().upper() in {"A", "B"}:
        label = text.strip().upper()
    else:
        label = "A"

    if "REASONING:" in text.upper():
        parts = re.split(r"(?i)reasoning\s*:\s*", text, maxsplit=1)
        if len(parts) == 2:
            explanation = parts[1].strip() or explanation
    elif "EXPLANATION:" in text.upper():
        parts = re.split(r"(?i)explanation\s*:\s*", text, maxsplit=1)
        if len(parts) == 2:
            explanation = parts[1].strip() or explanation
    return label, explanation.strip()


def _build_item_pair(item: Dict[str, Any]) -> Tuple[str, str]:
    qtype = str(item.get("question_type", "qa")).lower()
    question = str(item.get("question", "")).strip()
    answer = str(item.get("answer", "")).strip()
    explanation = str(item.get("explanation", "")).strip()
    options = item.get("options", [])

    if qtype in {"single_choice", "multiple_choice"}:
        options_block = _format_choice_options(options)
        if _question_has_options(question) or not options_block:
            human = question
        else:
            human = f"{question}\n\n{options_block}"

        letters, exp = _extract_choice_answer_explanation(answer, explanation)
        gpt = letters
        if exp:
            gpt += f"\n\n{exp}"
        return human.strip(), gpt.strip()

    if qtype == "true_false":
        human = question
        if not _question_has_options(human):
            human = f"{human}\n\nA. True\nB. False"

        label, exp = _extract_tf_answer_explanation(answer, explanation)
        gpt = label
        if exp:
            gpt += f"\n\n{exp}"
        return human.strip(), gpt.strip()

    # QA / open ended
    human = question
    gpt = answer
    return human.strip(), gpt.strip()


def convert_to_sharegpt(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in rows:
        human, gpt = _build_item_pair(item)
        if not human or not gpt:
            continue
        out.append(
            {
                "conversations": [
                    {"from": "human", "value": human},
                    {"from": "gpt", "value": gpt},
                ]
            }
        )
    return out


def _sharegpt_preview_rows(rows: List[Dict[str, Any]], limit: int = 20) -> List[Dict[str, str]]:
    preview: List[Dict[str, str]] = []
    for item in rows[:limit]:
        conversations = item.get("conversations", [])
        human = ""
        gpt = ""
        if isinstance(conversations, list):
            for turn in conversations:
                if not isinstance(turn, dict):
                    continue
                role = str(turn.get("from", "")).strip().lower()
                text = str(turn.get("value", "")).strip()
                if role == "human" and not human:
                    human = text
                elif role == "gpt" and not gpt:
                    gpt = text
        preview.append({"human": human, "gpt": gpt})
    return preview


def dataset_info_payload(dataset_name: str, data_file_name: str) -> Dict[str, Any]:
    return {
        dataset_name: {
            "file_name": data_file_name,
            "formatting": "sharegpt",
            "columns": {"messages": "conversations"},
        }
    }


def _default_llamafactory_path() -> Path:
    candidates = [
        project_root / "LLaMA-Factory",
        Path("/mnt/petrelfs/tancheng/work_dir/panck/OpenDataBench-pck/LLaMA-Factory"),
    ]
    for c in candidates:
        if (c / "src" / "train.py").exists():
            return c
    return candidates[0]


def _is_sharegpt_rows(rows: List[Dict[str, Any]]) -> bool:
    if not rows:
        return False
    first = rows[0]
    if not isinstance(first, dict):
        return False
    conv = first.get("conversations")
    if not isinstance(conv, list):
        return False
    for turn in conv:
        if not isinstance(turn, dict):
            return False
        if "from" not in turn or "value" not in turn:
            return False
    return True


def _is_finetune_rows(rows: List[Dict[str, Any]]) -> bool:
    if not rows:
        return False
    if _is_sharegpt_rows(rows):
        return True
    first = rows[0]
    if not isinstance(first, dict):
        return False
    # Canonical finetune rows used by this project.
    if {"question", "answer"}.issubset(set(first.keys())):
        return True
    # Some generated rows rely on question_type/options/explanation structure.
    if "question_type" in first and ("question" in first or "answer" in first):
        return True
    return False


def _discover_finetune_datasets(project_id: str, session_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    seen_names: set[str] = set()

    def _add_entry(name: str, source: str, rows: List[Dict[str, Any]], path: str = "") -> None:
        if not name:
            return
        safe_name = name
        idx = 2
        while safe_name in seen_names:
            safe_name = f"{name} ({idx})"
            idx += 1
        seen_names.add(safe_name)
        entries.append(
            {
                "name": safe_name,
                "source": source,
                "path": path,
                "rows": rows,
                "row_count": len(rows),
                "is_sharegpt": _is_sharegpt_rows(rows),
            }
        )

    if isinstance(session_rows, list) and session_rows:
        _add_entry("当前会话数据", "session", [x for x in session_rows if isinstance(x, dict)])

    project_dir = project_dir_path(project_id)
    file_patterns = [
        project_dir / "diagnosis" / "supplements" / "*.json",
        project_dir / "finetune_exports" / "*.json",
    ]
    skip_names = {
        "dataset_info.json",
        "active_train_job.json",
        "train_history.json",
        "history.json",
    }
    for pattern in file_patterns:
        for f in sorted(pattern.parent.glob(pattern.name), reverse=True):
            if not f.is_file():
                continue
            if f.name in skip_names:
                continue
            data = _load_json(f, [])
            if not isinstance(data, list):
                continue
            rows = [x for x in data if isinstance(x, dict)]
            if not rows:
                continue
            if not _is_finetune_rows(rows):
                continue
            _add_entry(f.stem, "file", rows, str(f))
    return entries


def _prepend_env_path(env: Dict[str, str], key: str, value: str) -> None:
    if not value:
        return
    sep = ";" if os.name == "nt" else ":"
    existing = env.get(key, "")
    parts = [p for p in existing.split(sep) if p]
    if value in parts:
        return
    env[key] = value if not existing else f"{value}{sep}{existing}"


def _detect_cuda_home() -> str:
    candidates: List[str] = []
    for k in ["CUDA_HOME", "CUDA_PATH"]:
        v = os.environ.get(k, "").strip()
        if v:
            candidates.append(v)

    nvcc_bin = shutil.which("nvcc")
    if nvcc_bin:
        try:
            candidates.append(str(Path(nvcc_bin).resolve().parent.parent))
        except Exception:
            pass

    candidates.extend(
        [
            "/usr/local/cuda",
            "/usr/local/cuda-12.4",
            "/usr/local/cuda-12.1",
            str(Path.home() / "cuda-12.4"),
            str(Path.home() / "cuda"),
        ]
    )
    seen: set[str] = set()
    for raw in candidates:
        p = Path(raw).expanduser()
        ps = str(p)
        if not ps or ps in seen:
            continue
        seen.add(ps)
        # Must have nvcc; lib64 alone can be a non-CUDA directory (e.g., conda root).
        if (p / "bin" / "nvcc").exists():
            return ps
    return ""


def _pick_master_port(preferred: int = 29601) -> int:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", preferred))
            return preferred
    except Exception:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            port = int(s.getsockname()[1])
            return port if port > 0 else preferred
    except Exception:
        return preferred


def _prepare_cluster_env(base_env: Dict[str, str], nproc_per_node: int) -> Tuple[Dict[str, str], Dict[str, Any]]:
    env = dict(base_env)
    cuda_home = _detect_cuda_home()
    if cuda_home:
        env["CUDA_HOME"] = cuda_home
        env["CUDA_PATH"] = cuda_home
        _prepend_env_path(env, "PATH", str(Path(cuda_home) / "bin"))
        _prepend_env_path(env, "LD_LIBRARY_PATH", str(Path(cuda_home) / "lib64"))
    master_port = _pick_master_port(29601)
    env["MASTER_PORT"] = str(master_port)
    env["NPROC_PER_NODE"] = str(int(max(1, nproc_per_node)))
    runtime = {
        "nproc_per_node": int(max(1, nproc_per_node)),
        "master_port": int(master_port),
        "cuda_home": cuda_home,
        "cuda_visible_devices": env.get("CUDA_VISIBLE_DEVICES", "").strip(),
    }
    return env, runtime


def _infer_template(model_path: str) -> str:
    name = model_path.lower()
    if "qwen" in name:
        return "qwen"
    if "deepseek" in name:
        return "deepseek"
    if "gemma" in name:
        return "gemma"
    if "mistral" in name:
        return "mistral"
    if "phi" in name:
        return "phi"
    return "llama3"


def _build_train_yaml(
    model_path: str,
    dataset_name: str,
    output_dir: str,
    template_name: str,
    finetuning_type: str,
    lora_rank: int,
    lora_alpha: int,
    lora_dropout: float,
    learning_rate: float,
    warmup_ratio: float,
    num_train_epochs: float,
    per_device_train_batch_size: int,
    gradient_accumulation_steps: int,
    cutoff_len: int,
    max_samples: int,
    logging_steps: int,
    save_steps: int,
) -> str:
    lines = [
        "### model",
        f"model_name_or_path: {model_path.replace(os.sep, '/')}",
        "trust_remote_code: true",
        "",
        "### method",
        "stage: sft",
        "do_train: true",
        f"finetuning_type: {finetuning_type}",
    ]
    if finetuning_type in {"lora", "qlora"}:
        lines.append(f"lora_rank: {lora_rank}")
        lines.append(f"lora_alpha: {lora_alpha}")
        lines.append(f"lora_dropout: {lora_dropout}")
        lines.append("lora_target: all")
    if finetuning_type == "qlora":
        lines.append("quantization_bit: 4")
    lines.extend(
        [
            "",
            "### dataset",
            f"dataset: {dataset_name}",
            f"template: {template_name}",
            f"cutoff_len: {cutoff_len}",
            f"max_samples: {max_samples}",
            "overwrite_cache: true",
            "preprocessing_num_workers: 8",
            "",
            "### output",
            f"output_dir: {output_dir.replace(os.sep, '/')}",
            f"logging_steps: {logging_steps}",
            f"save_steps: {save_steps}",
            "plot_loss: true",
            "overwrite_output_dir: true",
            "save_only_model: false",
            "report_to: none",
            "",
            "### train",
            f"per_device_train_batch_size: {per_device_train_batch_size}",
            f"gradient_accumulation_steps: {gradient_accumulation_steps}",
            f"learning_rate: {learning_rate}",
            f"num_train_epochs: {num_train_epochs}",
            "lr_scheduler_type: cosine",
            f"warmup_ratio: {warmup_ratio}",
            "bf16: true",
            "ddp_timeout: 180000000",
            "do_eval: false",
            # Keep quoted to avoid YAML bool coercion: bare `no` -> False.
            'eval_strategy: "no"',
        ]
    )
    return "\n".join(lines) + "\n"


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _update_dataset_info(dataset_info_path: Path, payload: Dict[str, Any]) -> None:
    current = _load_json(dataset_info_path, {})
    if not isinstance(current, dict):
        current = {}
    current.update(payload)
    dataset_info_path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_tail(path: Path, max_lines: int = 200) -> str:
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return "\n".join(lines[-max_lines:])


def _render_scrollable_log_block(label: str, content: str, height: int, storage_key: str) -> None:
    safe_label = html.escape(label)
    safe_content = html.escape(content)
    safe_key = re.sub(r"[^a-zA-Z0-9_.-]", "_", storage_key)
    component_html = f"""
<div style="font-family: sans-serif; margin-bottom: 6px;">{safe_label}</div>
<div id="logbox" style="height:{int(height)}px; overflow-y:auto; border:1px solid #ddd; border-radius:6px; padding:8px; background:#0f1116;">
  <pre style="margin:0; white-space:pre-wrap; word-break:break-word; color:#e6e6e6; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size:12px;">{safe_content}</pre>
</div>
<script>
(() => {{
  const box = document.getElementById("logbox");
  const key = "proda_log_scroll_{safe_key}";
  const saved = window.localStorage.getItem(key);
  if (saved !== null) {{
    const v = parseInt(saved, 10);
    if (!Number.isNaN(v)) box.scrollTop = v;
  }}
  box.addEventListener("scroll", () => {{
    window.localStorage.setItem(key, String(box.scrollTop));
  }});
}})();
</script>
"""
    components.html(component_html, height=int(height) + 40, scrolling=False)


def _job_state_path(project_id: str) -> Path:
    return project_dir_path(project_id) / "finetune_exports" / "active_train_job.json"


def _history_path(project_id: str) -> Path:
    return project_dir_path(project_id) / "finetune_exports" / "train_history.json"


def _flow_state_path(project_id: str) -> Path:
    return project_dir_path(project_id) / "workflow" / "second_round_flow.json"


def _load_flow_state(project_id: str) -> Dict[str, Any]:
    payload = _load_json(_flow_state_path(project_id), {})
    return payload if isinstance(payload, dict) else {}


def _save_flow_state(project_id: str, payload: Dict[str, Any]) -> None:
    path = _flow_state_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _save_job_state(project_id: str, payload: Dict[str, Any]) -> None:
    path = _job_state_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_job_state(project_id: str) -> Dict[str, Any]:
    return _load_json(_job_state_path(project_id), {})


def _clear_job_state(project_id: str) -> None:
    path = _job_state_path(project_id)
    if path.exists():
        path.unlink()


def _load_history(project_id: str) -> List[Dict[str, Any]]:
    payload = _load_json(_history_path(project_id), [])
    return payload if isinstance(payload, list) else []


def _save_history(project_id: str, rows: List[Dict[str, Any]]) -> None:
    path = _history_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


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


def _delete_log_files_for_sessions(
    project_id: str,
    history_by_session: Dict[str, Dict[str, Any]],
    session_ids: List[str],
    active_log_path: str,
    is_running: bool,
) -> Tuple[int, int, int]:
    deleted_count = 0
    missing_count = 0
    skipped_count = 0
    for sid in session_ids:
        h = history_by_session.get(str(sid))
        if not h:
            continue
        lp = Path(str(h.get("log_path", "")))
        if not str(lp).strip():
            continue
        if is_running and str(lp) == str(active_log_path):
            skipped_count += 1
            continue
        if lp.exists():
            try:
                lp.unlink()
                deleted_count += 1
            except Exception:
                skipped_count += 1
                continue
        else:
            missing_count += 1
        _update_history(
            project_id,
            str(sid),
            {
                "log_path": "",
                "log_deleted": True,
            },
        )
    return deleted_count, missing_count, skipped_count


def _is_pid_running(pid: Optional[int]) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        # Linux: treat zombie as not running.
        status_path = Path(f"/proc/{pid}/status")
        if status_path.exists():
            txt = status_path.read_text(encoding="utf-8", errors="ignore")
            if "State:\tZ" in txt or "State:\tX" in txt:
                return False
        return True
    except Exception:
        return False


def _terminate_pid(pid: Optional[int]) -> None:
    if not pid or pid <= 0:
        return
    try:
        os.killpg(pid, signal.SIGTERM)
        try:
            # best effort wait by polling
            for _ in range(10):
                if not _is_pid_running(pid):
                    break
                time.sleep(0.5)
        except Exception:
            pass
        if _is_pid_running(pid):
            os.killpg(pid, signal.SIGKILL)
    except Exception:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass


def _extract_training_metrics(log_text: str, max_points: int = 1200) -> pd.DataFrame:
    lines = log_text.splitlines()
    loss_re = re.compile(r"(?:'|\")?(?:loss|train_loss)(?:'|\")?\s*[:=]\s*([0-9]*\.?[0-9]+(?:e[-+]?\d+)?)", re.I)
    lr_re = re.compile(r"(?:'|\")?(?:learning_rate|lr)(?:'|\")?\s*[:=]\s*([0-9]*\.?[0-9]+(?:e[-+]?\d+)?)", re.I)
    step_re = re.compile(r"(?:'|\")?(?:step|global_step)(?:'|\")?\s*[:=]\s*([0-9]+)", re.I)

    points: List[Dict[str, float]] = []
    seq_idx = 0
    for line in lines:
        m_loss = loss_re.search(line)
        m_lr = lr_re.search(line)
        if not m_loss and not m_lr:
            continue
        seq_idx += 1
        m_step = step_re.search(line)
        step_val = int(m_step.group(1)) if m_step else seq_idx
        row: Dict[str, float] = {"step": float(step_val), "idx": float(seq_idx)}
        if m_loss:
            try:
                row["loss"] = float(m_loss.group(1))
            except Exception:
                pass
        if m_lr:
            try:
                row["lr"] = float(m_lr.group(1))
            except Exception:
                pass
        if len(row) > 1:
            points.append(row)

    if len(points) > max_points:
        points = points[-max_points:]
    if not points:
        return pd.DataFrame(columns=["idx", "step", "loss", "lr"])
    return pd.DataFrame(points)


def _extract_training_metrics_from_jsonl(path: Path, max_points: int = 4000) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["idx", "step", "loss", "lr", "total_steps"])
    rows: List[Dict[str, float]] = []
    idx = 0
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        cur = obj.get("current_steps")
        total = obj.get("total_steps")
        loss = obj.get("loss")
        lr = obj.get("lr")
        if cur is None:
            continue
        idx += 1
        row: Dict[str, float] = {"idx": float(idx), "step": float(cur)}
        if isinstance(total, (int, float)):
            row["total_steps"] = float(total)
        if isinstance(loss, (int, float)):
            row["loss"] = float(loss)
        if isinstance(lr, (int, float)):
            row["lr"] = float(lr)
        # keep step records even if the final line has no loss/lr
        rows.append(row)
    if len(rows) > max_points:
        rows = rows[-max_points:]
    if not rows:
        return pd.DataFrame(columns=["idx", "step", "loss", "lr", "total_steps"])
    return pd.DataFrame(rows)


def _looks_like_training_success(output_dir: Path, log_text: str) -> bool:
    if output_dir.exists():
        expected = [
            output_dir / "trainer_state.json",
            output_dir / "training_args.bin",
        ]
        if any(p.exists() for p in expected):
            return True
        if any(p.name.startswith("checkpoint-") for p in output_dir.glob("*")):
            return True
    success_marks = ["train_runtime", "Training completed", "Saving model checkpoint"]
    return any(x.lower() in log_text.lower() for x in success_marks)


def _looks_like_training_finished(log_text: str) -> bool:
    markers = [
        "train_runtime",
        "Training completed",
        "***** train metrics *****",
    ]
    low = log_text.lower()
    return any(m.lower() in low for m in markers)


def _jsonl_reaches_end(path: Path) -> bool:
    if not path.exists():
        return False
    last_obj: Dict[str, Any] = {}
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            last_obj = obj
    if not last_obj:
        return False
    cur = last_obj.get("current_steps")
    total = last_obj.get("total_steps")
    if isinstance(cur, (int, float)) and isinstance(total, (int, float)) and total > 0:
        return float(cur) >= float(total)
    pct = last_obj.get("percentage")
    if isinstance(pct, (int, float)) and float(pct) >= 100.0:
        return True
    return False


def main() -> None:
    init_i18n()
    render_top_bar()
    render_workflow_sidebar()
    enforce_active_project()

    st.title(t("fine_tuning.title", default="Fine-Tuning Setup"))
    st.caption(t("fine_tuning.desc", default="Convert finetune data to ShareGPT and prepare training artifacts."))
    current_project_id = SessionStateManager.get_current_project_id()
    flow_state = _load_flow_state(current_project_id)
    if bool(flow_state.get("merged_ready", False)):
        st.info(
            t(
                "fine_tuning.flow_merged_ready",
                default="二轮数据已就绪：{rows} 条（{ts}）。建议在本页完成二轮微调后前往 Step6 评测。",
                rows=int(flow_state.get("merged_rows", 0) or 0),
                ts=str(flow_state.get("merged_at", ""))[:19].replace("T", " "),
            )
        )

    session_rows = SessionStateManager.get_finetune_data()
    dataset_entries = _discover_finetune_datasets(current_project_id, session_rows)
    if not dataset_entries:
        st.warning(t("fine_tuning.no_data", default="No finetune data found. Please generate data in Step3 first."))
        if st.button(t("fine_tuning.go_step3", default="Go to Step3"), type="primary"):
            st.switch_page("pages/3_Finetune_Generation.py")
        return

    selected_dataset_idx = st.selectbox(
        t("fine_tuning.pick_dataset", default="选择训练数据集"),
        options=list(range(len(dataset_entries))),
        format_func=lambda i: str(dataset_entries[i].get("name", "")),
        key=f"step5_pick_dataset_{current_project_id}",
    )
    selected_dataset = dataset_entries[int(selected_dataset_idx)]
    finetune_rows = list(selected_dataset.get("rows", []) or [])
    is_selected_sharegpt = bool(selected_dataset.get("is_sharegpt", False))

    st.info(
        t("fine_tuning.loaded", default="Loaded {n} finetune records.").format(n=len(finetune_rows))
        + f" | {t('fine_tuning.active_dataset', default='当前数据集')}: {selected_dataset.get('name', '')}"
    )
    nav_cols = st.columns(2)
    with nav_cols[0]:
        if st.button(t("fine_tuning.back_step3", default="Back to Step3"), use_container_width=True):
            st.switch_page("pages/3_Finetune_Generation.py")
    with nav_cols[1]:
        if st.button(t("fine_tuning.go_step6", default="Go to Step6"), use_container_width=True):
            st.switch_page("pages/7_OpenCompass_Evaluation.py")
    last_model_dir = str(flow_state.get("last_trained_model_dir", "")).strip()
    if last_model_dir:
        st.caption(
            t(
                "fine_tuning.flow_latest_model",
                default="最近一次训练产物目录：{path}",
                path=last_model_dir,
            )
        )

    st.markdown("---")
    model_paths = _list_local_models(MODEL_ROOT)
    model_map = {Path(p).name: p for p in model_paths}
    model_names = sorted(model_map.keys())
    selected_model = st.selectbox(
        t("fine_tuning.select_model", default="Select base model"),
        model_names if model_names else [t("fine_tuning.no_model_found", default="No model found")],
        disabled=not bool(model_names),
    )
    selected_model_path = model_map.get(selected_model, "")

    st.markdown("---")
    st.subheader(t("fine_tuning.sharegpt_section", default="ShareGPT Conversion"))
    default_dataset_name = str(selected_dataset.get("name", "proda_sft")).strip() or "proda_sft"
    dataset_name = st.text_input(t("fine_tuning.dataset_name", default="Dataset name"), default_dataset_name)
    sharegpt = finetune_rows if is_selected_sharegpt else convert_to_sharegpt(finetune_rows)
    if not sharegpt:
        st.warning(t("fine_tuning.sharegpt_empty", default="所选数据集无法转换为可用 ShareGPT 样本，请切换数据集。"))
        return
    st.success(t("fine_tuning.converted", default="Converted {n} ShareGPT records.").format(n=len(sharegpt)))
    st.dataframe(_sharegpt_preview_rows(sharegpt, limit=min(20, len(sharegpt))), use_container_width=True, height=360)

    export_dir = project_dir_path(current_project_id) / "finetune_exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    sharegpt_name = f"{dataset_name}.json"
    sharegpt_path = export_dir / sharegpt_name
    dataset_info = dataset_info_payload(dataset_name, sharegpt_name)
    dataset_info_path = export_dir / "dataset_info.json"

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button(t("fine_tuning.save_local", default="Save to project"), type="primary", use_container_width=True):
            sharegpt_path.write_text(json.dumps(sharegpt, ensure_ascii=False, indent=2), encoding="utf-8")
            dataset_info_path.write_text(json.dumps(dataset_info, ensure_ascii=False, indent=2), encoding="utf-8")
            st.success(
                t("fine_tuning.saved_paths", default="Saved:\n- {p1}\n- {p2}").format(
                    p1=str(sharegpt_path), p2=str(dataset_info_path)
                )
            )
    with col_b:
        st.download_button(
            t("fine_tuning.download_sharegpt", default="Download ShareGPT JSON"),
            data=json.dumps(sharegpt, ensure_ascii=False, indent=2),
            file_name=sharegpt_name,
            mime="application/json",
            use_container_width=True,
        )
    st.download_button(
        t("fine_tuning.download_dataset_info", default="Download dataset_info.json"),
        data=json.dumps(dataset_info, ensure_ascii=False, indent=2),
        file_name="dataset_info.json",
        mime="application/json",
        use_container_width=True,
    )

    st.markdown("---")
    st.subheader(t("fine_tuning.train_section", default="Step 3 · Compile / Train"))

    llamafactory_path = _default_llamafactory_path()
    lf_ok = (llamafactory_path / "src" / "train.py").exists()
    if lf_ok:
        st.success(t("fine_tuning.llamafactory_ok", default="LLaMA-Factory detected."))
    else:
        st.error(
            t(
                "fine_tuning.llamafactory_missing",
                default="LLaMA-Factory not found at this path (missing src/train.py).",
            )
        )

    if selected_model_path:
        template_name = st.text_input(
            t("fine_tuning.template", default="Template"),
            value=_infer_template(selected_model_path),
        )
    else:
        template_name = st.text_input(t("fine_tuning.template", default="Template"), value="llama3")

    c1, c2, c3 = st.columns(3)
    with c1:
        finetuning_type = st.selectbox(
            t("fine_tuning.finetuning_type", default="Finetuning type"),
            ["lora", "qlora", "full"],
            index=0,
        )
        learning_rate = st.number_input(t("fine_tuning.learning_rate", default="Learning rate"), value=1e-4, format="%.6f")
        warmup_ratio = st.number_input(
            t("fine_tuning.warmup_ratio", default="Warmup ratio"),
            min_value=0.0,
            max_value=0.5,
            value=0.1,
            step=0.01,
            format="%.2f",
        )
        num_train_epochs = st.number_input(t("fine_tuning.epochs", default="Epochs"), value=3.0, step=0.5)
    with c2:
        per_device_train_batch_size = st.number_input(
            t("fine_tuning.batch_size", default="Per-device batch size"),
            min_value=1,
            max_value=64,
            value=1,
            step=1,
        )
        gradient_accumulation_steps = st.number_input(
            t("fine_tuning.grad_accum", default="Gradient accumulation"),
            min_value=1,
            max_value=128,
            value=8,
            step=1,
        )
        cutoff_len = st.number_input(t("fine_tuning.cutoff_len", default="Cutoff length"), min_value=256, max_value=16384, value=2048, step=128)
    with c3:
        max_samples_cap = max(1, len(sharegpt))
        max_samples = st.number_input(
            t("fine_tuning.max_samples", default="Max samples"),
            min_value=1,
            max_value=max_samples_cap,
            value=min(5000, max_samples_cap),
            step=1,
        )
        logging_steps = st.number_input(t("fine_tuning.logging_steps", default="Logging steps"), min_value=1, max_value=5000, value=10, step=1)
        save_steps = st.number_input(t("fine_tuning.save_steps", default="Save steps"), min_value=1, max_value=50000, value=100, step=1)
        nproc_per_node = int(
            st.number_input(
                t("fine_tuning.nproc_per_node", default="GPUs for training (nproc_per_node)"),
                min_value=1,
                max_value=32,
                value=1,
                step=1,
            )
        )
    lora_rank = int(
        st.number_input(
            t("fine_tuning.lora_rank", default="LoRA rank"),
            min_value=1,
            max_value=256,
            value=16,
            step=1,
            disabled=finetuning_type == "full",
        )
    )
    lora_alpha = int(
        st.number_input(
            t("fine_tuning.lora_alpha", default="LoRA alpha"),
            min_value=1,
            max_value=1024,
            value=32,
            step=1,
            disabled=finetuning_type == "full",
        )
    )
    lora_dropout = float(
        st.number_input(
            t("fine_tuning.lora_dropout", default="LoRA dropout"),
            min_value=0.0,
            max_value=0.5,
            value=0.05,
            step=0.01,
            format="%.2f",
            disabled=finetuning_type == "full",
        )
    )

    st.caption(
        t(
            "fine_tuning.cluster_auto_note",
            default="Cluster env is auto-configured on start (CUDA_HOME/PATH/LD_LIBRARY_PATH/MASTER_PORT).",
        )
    )

    model_tag = st.text_input(t("fine_tuning.model_tag", default="Output model tag"), "v1")
    output_dir = project_dir_path(current_project_id) / "model_outputs" / model_tag
    st.caption(t("fine_tuning.output_dir", default="Output dir: {p}").format(p=str(output_dir)))

    job_state = _load_job_state(current_project_id)
    running_pid = int(job_state.get("pid", 0) or 0)
    is_running = _is_pid_running(running_pid)

    start_col, stop_col, refresh_col = st.columns(3)
    with start_col:
        start_clicked = st.button(
            t("fine_tuning.start_training", default="Start Training"),
            type="primary",
            disabled=is_running or (not lf_ok) or (not model_paths),
            use_container_width=True,
        )
    with stop_col:
        stop_clicked = st.button(
            t("fine_tuning.stop_training", default="Stop Training"),
            disabled=not is_running,
            use_container_width=True,
        )
    with refresh_col:
        auto_refresh = st.checkbox(t("fine_tuning.auto_refresh", default="Auto refresh logs"), value=True)

    if stop_clicked and is_running:
        _terminate_pid(running_pid)
        session_id = str(job_state.get("session_id", ""))
        if session_id:
            _update_history(
                current_project_id,
                session_id,
                {
                    "status": "stopped",
                    "ended_at": int(time.time()),
                },
            )
        _clear_job_state(current_project_id)
        st.warning(t("fine_tuning.stopped", default="Training stopped."))
        is_running = False

    if start_clicked:
        lf_data_dir = llamafactory_path / "data"
        lf_data_dir.mkdir(parents=True, exist_ok=True)

        # Save in project export
        sharegpt_path.write_text(json.dumps(sharegpt, ensure_ascii=False, indent=2), encoding="utf-8")
        dataset_info_path.write_text(json.dumps(dataset_info, ensure_ascii=False, indent=2), encoding="utf-8")

        # Copy training data into LLaMA-Factory data dir and update dataset_info
        lf_sharegpt = lf_data_dir / sharegpt_name
        shutil.copy2(sharegpt_path, lf_sharegpt)
        lf_dataset_info = lf_data_dir / "dataset_info.json"
        _update_dataset_info(lf_dataset_info, dataset_info)

        # Build yaml
        output_dir.mkdir(parents=True, exist_ok=True)
        yaml_text = _build_train_yaml(
            model_path=selected_model_path,
            dataset_name=dataset_name,
            output_dir=str(output_dir),
            template_name=template_name,
            finetuning_type=finetuning_type,
            lora_rank=lora_rank,
            lora_alpha=lora_alpha,
            lora_dropout=lora_dropout,
            learning_rate=float(learning_rate),
            warmup_ratio=float(warmup_ratio),
            num_train_epochs=float(num_train_epochs),
            per_device_train_batch_size=int(per_device_train_batch_size),
            gradient_accumulation_steps=int(gradient_accumulation_steps),
            cutoff_len=int(cutoff_len),
            max_samples=int(max_samples),
            logging_steps=int(logging_steps),
            save_steps=int(save_steps),
        )
        cfg_dir = project_dir_path(current_project_id) / "finetune_exports" / "configs"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        cfg_path = cfg_dir / f"{dataset_name}_{model_tag}.yaml"
        cfg_path.write_text(yaml_text, encoding="utf-8")

        log_dir = project_dir_path(current_project_id) / "finetune_exports" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{dataset_name}_{model_tag}_{int(time.time())}.log"

        # Build runtime env and launch train process
        base_env = os.environ.copy()
        base_env["PYTHONUNBUFFERED"] = "1"
        env, runtime_meta = _prepare_cluster_env(base_env, int(nproc_per_node))
        master_port = int(runtime_meta.get("master_port", 29601))

        # Launch train process
        cmd: List[str]
        if nproc_per_node > 1:
            if shutil.which("torchrun"):
                cmd = [
                    "torchrun",
                    f"--nproc_per_node={int(nproc_per_node)}",
                    f"--master_port={int(master_port)}",
                    "src/train.py",
                    str(cfg_path),
                ]
            else:
                cmd = [
                    sys.executable,
                    "-m",
                    "torch.distributed.run",
                    f"--nproc_per_node={int(nproc_per_node)}",
                    f"--master_port={int(master_port)}",
                    "src/train.py",
                    str(cfg_path),
                ]
        else:
            cmd = ["llamafactory-cli", "train", str(cfg_path)]
            if shutil.which("llamafactory-cli") is None:
                cmd = [sys.executable, "src/train.py", str(cfg_path)]
        try:
            with open(log_path, "w", encoding="utf-8") as logf:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(llamafactory_path),
                    stdout=logf,
                    stderr=subprocess.STDOUT,
                    env=env,
                    start_new_session=True,
                )
        except Exception as exc:
            st.error(t("fine_tuning.launch_failed", default="Failed to launch training: {err}").format(err=str(exc)))
            return
        session_id = str(time.time_ns())
        _save_job_state(
            current_project_id,
            {
                "session_id": session_id,
                "pid": int(proc.pid),
                "log_path": str(log_path),
                "cfg_path": str(cfg_path),
                "output_dir": str(output_dir),
                "dataset_name": dataset_name,
                "started_at": int(time.time()),
            },
        )
        _append_history(
            current_project_id,
            {
                "session_id": session_id,
                "status": "running",
                "pid": int(proc.pid),
                "started_at": int(time.time()),
                "ended_at": None,
                "dataset_name": dataset_name,
                "model_path": selected_model_path,
                "finetuning_type": finetuning_type,
                "lora_rank": int(lora_rank),
                "lora_alpha": int(lora_alpha),
                "lora_dropout": float(lora_dropout),
                "learning_rate": float(learning_rate),
                "warmup_ratio": float(warmup_ratio),
                "epochs": float(num_train_epochs),
                "batch_size": int(per_device_train_batch_size),
                "grad_accum": int(gradient_accumulation_steps),
                "max_samples": int(max_samples),
                "nproc_per_node": int(runtime_meta.get("nproc_per_node", nproc_per_node)),
                "master_port": int(runtime_meta.get("master_port", master_port)),
                "cuda_home": str(runtime_meta.get("cuda_home", "")),
                "cuda_visible_devices": str(runtime_meta.get("cuda_visible_devices", "")),
                "cfg_path": str(cfg_path),
                "log_path": str(log_path),
                "output_dir": str(output_dir),
            },
        )
        flow_state = _load_flow_state(current_project_id)
        flow_state.update(
            {
                "last_training_started_at": datetime.now().isoformat(),
                "last_training_output_dir": str(output_dir),
                "last_training_dataset_name": str(dataset_name),
                "last_training_base_model": str(selected_model_path),
                "last_training_type": str(finetuning_type),
            }
        )
        _save_flow_state(current_project_id, flow_state)
        st.success(
            t(
                "fine_tuning.training_started",
                default="Training started. PID={pid}",
            ).format(pid=proc.pid)
        )
        st.caption(
            t(
                "fine_tuning.cluster_runtime_info",
                default="Runtime env: CUDA_HOME={cuda_home}, MASTER_PORT={master_port}, NPROC_PER_NODE={nproc}",
            ).format(
                cuda_home=str(runtime_meta.get("cuda_home") or "auto-not-found"),
                master_port=str(runtime_meta.get("master_port")),
                nproc=str(runtime_meta.get("nproc_per_node")),
            )
        )

    # Log panel
    job_state = _load_job_state(current_project_id)
    log_path_value = str(job_state.get("log_path", ""))
    cfg_path_value = str(job_state.get("cfg_path", ""))
    out_path_value = str(job_state.get("output_dir", ""))
    running_pid = int(job_state.get("pid", 0) or 0)
    is_running = _is_pid_running(running_pid)
    if cfg_path_value:
        st.caption(t("fine_tuning.cfg_path", default="Config: {p}").format(p=cfg_path_value))
    if out_path_value:
        st.caption(t("fine_tuning.out_path", default="Model output: {p}").format(p=out_path_value))
    if running_pid:
        st.caption(t("fine_tuning.pid", default="PID: {pid}").format(pid=running_pid))

    if log_path_value:
        log_path = Path(log_path_value)
        trainer_log_jsonl = Path(out_path_value) / "trainer_log.jsonl" if out_path_value else Path()
        tail_lines = st.slider(t("fine_tuning.log_lines", default="Log lines"), 50, 2000, 300, 50)
        logs = _read_tail(log_path, tail_lines)
        if log_path.exists():
            full_logs = log_path.read_text(encoding="utf-8", errors="ignore")
        else:
            full_logs = ""
        _render_scrollable_log_block(
            t("fine_tuning.log_scroll", default="Training logs (scrollable)"),
            logs if logs else t("fine_tuning.log_waiting", default="Waiting for logs..."),
            height=420,
            storage_key=f"active_{current_project_id}",
        )

        metric_df = _extract_training_metrics_from_jsonl(trainer_log_jsonl, max_points=4000)
        if metric_df.empty:
            metric_df = _extract_training_metrics(full_logs, max_points=4000)
        if not metric_df.empty:
            c_loss, c_lr = st.columns(2)
            with c_loss:
                if "loss" in metric_df.columns and metric_df["loss"].notna().any():
                    latest_loss = float(metric_df["loss"].dropna().iloc[-1])
                    st.metric(t("fine_tuning.latest_loss", default="Latest loss"), f"{latest_loss:.6f}")
            with c_lr:
                if "lr" in metric_df.columns and metric_df["lr"].notna().any():
                    latest_lr = float(metric_df["lr"].dropna().iloc[-1])
                    st.metric(t("fine_tuning.latest_lr", default="Latest lr"), f"{latest_lr:.8f}")

            if "loss" in metric_df.columns and metric_df["loss"].notna().any():
                st.markdown(t("fine_tuning.loss_curve", default="Loss Curve"))
                st.line_chart(metric_df.set_index("idx")[["loss"]])
            if "lr" in metric_df.columns and metric_df["lr"].notna().any():
                st.markdown(t("fine_tuning.lr_curve", default="Learning Rate Curve"))
                st.line_chart(metric_df.set_index("idx")[["lr"]])

        # In some cluster cases parent process lingers after logs already reached terminal markers.
        if is_running and (_looks_like_training_finished(full_logs) or _jsonl_reaches_end(trainer_log_jsonl)):
            is_running = False

        if is_running:
            st.info(t("fine_tuning.running_status", default="Training is running..."))
            if auto_refresh:
                time.sleep(2)
                st.rerun()
        else:
            session_id = str(job_state.get("session_id", ""))
            if session_id:
                outcome = "stopped_or_failed"
                if _looks_like_training_success(Path(out_path_value), logs):
                    outcome = "finished"
                    flow_state = _load_flow_state(current_project_id)
                    flow_state.update(
                        {
                            "last_trained_model_dir": str(out_path_value),
                            "last_training_finished_at": datetime.now().isoformat(),
                            "last_training_outcome": "finished",
                        }
                    )
                    _save_flow_state(current_project_id, flow_state)
                else:
                    flow_state = _load_flow_state(current_project_id)
                    flow_state.update(
                        {
                            "last_training_finished_at": datetime.now().isoformat(),
                            "last_training_outcome": "stopped_or_failed",
                        }
                    )
                    _save_flow_state(current_project_id, flow_state)
                _update_history(
                    current_project_id,
                    session_id,
                    {
                        "status": outcome,
                        "ended_at": int(time.time()),
                    },
                )
                _clear_job_state(current_project_id)
            st.success(t("fine_tuning.train_done_or_stopped", default="No running training process detected."))

    st.markdown("---")
    st.subheader(t("fine_tuning.history_title", default="Training Session History"))
    history = _load_history(current_project_id)
    if not history:
        st.info(t("fine_tuning.history_empty", default="No training sessions yet."))
    else:
        history_sorted = sorted(history, key=lambda x: int(x.get("started_at") or 0), reverse=True)
        history_by_session = {str(h.get("session_id")): h for h in history_sorted}
        rows = []
        for h in history_sorted:
            started = int(h.get("started_at") or 0)
            ended = int(h.get("ended_at") or 0) if h.get("ended_at") else 0
            rows.append(
                {
                    "session_id": h.get("session_id"),
                    "status": h.get("status"),
                    "dataset": h.get("dataset_name"),
                    "type": h.get("finetuning_type"),
                    "lora_r": h.get("lora_rank"),
                    "lora_a": h.get("lora_alpha"),
                    "lora_d": h.get("lora_dropout"),
                    "lr": h.get("learning_rate"),
                    "warmup_ratio": h.get("warmup_ratio"),
                    "nproc": h.get("nproc_per_node"),
                    "epochs": h.get("epochs"),
                    "started_at": datetime.fromtimestamp(started).strftime("%Y-%m-%d %H:%M:%S") if started else "",
                    "ended_at": datetime.fromtimestamp(ended).strftime("%Y-%m-%d %H:%M:%S") if ended else "",
                    "output_dir": h.get("output_dir"),
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, height=260)

        st.markdown("---")
        st.markdown(t("fine_tuning.log_delete_title", default="Delete training log files"))
        delete_options = [
            {
                "sid": str(h.get("session_id")),
                "label": f"{h.get('session_id')} | {h.get('status', '')} | {h.get('dataset_name', '')}",
            }
            for h in history_sorted
            if str(h.get("log_path", "")).strip()
        ]
        delete_choice = st.multiselect(
            t("fine_tuning.log_delete_pick", default="Select sessions to delete logs"),
            options=[x["sid"] for x in delete_options],
            format_func=lambda sid: next((x["label"] for x in delete_options if x["sid"] == sid), sid),
        )
        if st.button(
            t("fine_tuning.log_delete_btn", default="Delete selected log files"),
            disabled=not delete_choice,
            type="secondary",
        ):
            deleted_count, missing_count, skipped_count = _delete_log_files_for_sessions(
                current_project_id,
                history_by_session,
                [str(x) for x in delete_choice],
                active_log_path=str(log_path_value),
                is_running=is_running,
            )
            st.success(
                t(
                    "fine_tuning.log_delete_done",
                    default="Deleted: {d}, missing: {m}, skipped: {s}",
                ).format(d=deleted_count, m=missing_count, s=skipped_count)
            )
            st.rerun()

        finished_log_session_ids = [
            str(h.get("session_id"))
            for h in history_sorted
            if str(h.get("status", "")).lower() != "running" and str(h.get("log_path", "")).strip()
        ]
        if st.button(
            t("fine_tuning.log_delete_finished_btn", default="Delete all finished-session logs"),
            disabled=not finished_log_session_ids,
            type="secondary",
        ):
            deleted_count, missing_count, skipped_count = _delete_log_files_for_sessions(
                current_project_id,
                history_by_session,
                finished_log_session_ids,
                active_log_path=str(log_path_value),
                is_running=is_running,
            )
            st.success(
                t(
                    "fine_tuning.log_delete_done",
                    default="Deleted: {d}, missing: {m}, skipped: {s}",
                ).format(d=deleted_count, m=missing_count, s=skipped_count)
            )
            st.rerun()

        selected_session = st.selectbox(
            t("fine_tuning.history_pick", default="View session details"),
            [str(h.get("session_id")) for h in history_sorted],
        )
        picked = next((x for x in history_sorted if str(x.get("session_id")) == selected_session), None)
        if picked:
            st.caption(t("fine_tuning.history_cfg", default="Config: {p}").format(p=str(picked.get("cfg_path", ""))))
            st.caption(t("fine_tuning.history_log", default="Log: {p}").format(p=str(picked.get("log_path", ""))))
            log_p = Path(str(picked.get("log_path", "")))
            if log_p.exists():
                _render_scrollable_log_block(
                    t("fine_tuning.log_scroll", default="Training logs (scrollable)"),
                    _read_tail(log_p, 400),
                    height=360,
                    storage_key=f"history_{current_project_id}_{selected_session}",
                )


if __name__ == "__main__":
    main()
