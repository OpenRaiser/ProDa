"""Shared helpers for Phase 5 Fine-Tuning (LLaMA-Factory integration)."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.lib import proc as _proc

# Re-exports so existing imports (`from backend.lib.llama_factory import detect_gpus`) keep working.
detect_cuda_home = _proc.detect_cuda_home
detect_gpus = _proc.detect_gpus
detect_torch_version = _proc.detect_torch_version
pick_master_port = _proc.pick_free_port
terminate_pid_tree = _proc.terminate_pid_tree
is_pid_alive = _proc.is_pid_alive


# ---------- Path discovery ----------

def default_llamafactory_path(project_root: Path) -> Path:
    candidates = [
        project_root / "LLaMA-Factory",
        Path("/mnt/petrelfs/tancheng/work_dir/panck/OpenDataBench-pck/LLaMA-Factory"),
    ]
    for c in candidates:
        if (c / "src" / "train.py").exists():
            return c
    return candidates[0]


def llamafactory_path_ok(path: Path) -> bool:
    return (path / "src" / "train.py").exists()


def list_local_models(root: Path) -> List[str]:
    if not root.exists():
        return []
    found: List[str] = []
    for p in root.rglob("*"):
        if p.is_dir() and any(
            (p / x).exists() for x in ["config.json", "tokenizer.json", "tokenizer_config.json"]
        ):
            found.append(str(p))
    # Remove nested duplicates (keep shortest paths first).
    found = sorted(set(found), key=lambda x: len(x))
    filtered: List[str] = []
    for path in found:
        norm = path.replace(os.sep, "/")
        if not any(norm.startswith(p.replace(os.sep, "/") + "/") for p in filtered):
            filtered.append(path)
    return filtered


# ---------- Dataset shape checks ----------

def is_sharegpt_rows(rows: List[Dict[str, Any]]) -> bool:
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


def is_finetune_rows(rows: List[Dict[str, Any]]) -> bool:
    if not rows:
        return False
    if is_sharegpt_rows(rows):
        return True
    first = rows[0]
    if not isinstance(first, dict):
        return False
    if {"question", "answer"}.issubset(set(first.keys())):
        return True
    if "question_type" in first and ("question" in first or "answer" in first):
        return True
    return False


# ---------- ShareGPT conversion ----------

def _strip_label(text: str) -> str:
    return re.sub(r"^\s*[A-Da-d][\.\):\s-]+", "", text.strip())


def _format_choice_options(options: Any) -> str:
    if isinstance(options, dict):
        return "\n".join(f"{k}. {_strip_label(str(v))}" for k, v in sorted(options.items()))
    if isinstance(options, list):
        return "\n".join(f"{chr(65 + i)}. {_strip_label(str(opt))}" for i, opt in enumerate(options))
    return ""


def _question_has_options(question: str) -> bool:
    patterns = [r"(?m)^\s*[A-D][\.\):\s-]+"] * 4
    labels = ["A", "B", "C", "D"]
    return all(re.search(p.replace("[A-D]", lab), question) for p, lab in zip(patterns, labels))


def _extract_choice_answer_explanation(answer: str, explanation: str) -> Tuple[str, str]:
    text = answer.strip()
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
    low = text.lower()
    if re.search(r"\bfalse\b", low):
        label = "B"
    elif re.search(r"\btrue\b", low):
        label = "A"
    elif re.search(r"\bjudgment\s*:\s*b\b", low):
        label = "B"
    elif re.search(r"\bjudgment\s*:\s*a\b", low):
        label = "A"
    elif text.upper() in {"A", "B"}:
        label = text.upper()
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
        human = question if (_question_has_options(question) or not options_block) else f"{question}\n\n{options_block}"
        letters, exp = _extract_choice_answer_explanation(answer, explanation)
        gpt = letters + (f"\n\n{exp}" if exp else "")
        return human.strip(), gpt.strip()
    if qtype == "true_false":
        human = question
        if not _question_has_options(human):
            human = f"{human}\n\nA. True\nB. False"
        label, exp = _extract_tf_answer_explanation(answer, explanation)
        gpt = label + (f"\n\n{exp}" if exp else "")
        return human.strip(), gpt.strip()
    return question, answer


def convert_to_sharegpt(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
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


# ---------- Dataset discovery ----------

def _load_json_safe(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def discover_datasets(
    project_dir: Path,
    session_rows: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    seen_names: set[str] = set()

    def _add(name: str, source: str, rows: List[Dict[str, Any]], path: str = "") -> None:
        if not name:
            return
        safe = name
        idx = 2
        while safe in seen_names:
            safe = f"{name} ({idx})"
            idx += 1
        seen_names.add(safe)
        entries.append(
            {
                "name": safe,
                "source": source,
                "path": path,
                "row_count": len(rows),
                "is_sharegpt": is_sharegpt_rows(rows),
            }
        )

    session_rows = session_rows or []
    if session_rows:
        _add("current-session-data", "session", [x for x in session_rows if isinstance(x, dict)])

    skip_names = {"dataset_info.json", "active_train_job.json", "train_history.json", "history.json"}
    patterns = [
        project_dir / "diagnosis" / "supplements",
        project_dir / "finetune_exports",
    ]
    for parent in patterns:
        if not parent.exists():
            continue
        files = sorted(parent.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for f in files:
            if not f.is_file() or f.name in skip_names:
                continue
            data = _load_json_safe(f, [])
            if not isinstance(data, list):
                continue
            rows = [x for x in data if isinstance(x, dict)]
            if not rows or not is_finetune_rows(rows):
                continue
            _add(f.stem, "file", rows, str(f))
    return entries


# ---------- CUDA / env ----------

def prepare_env(base_env: Dict[str, str], nproc_per_node: int) -> Tuple[Dict[str, str], Dict[str, Any]]:
    env = dict(base_env)
    env["PYTHONUNBUFFERED"] = "1"
    # Force UTF-8 on Windows so child stdout doesn't crash on unicode.
    env["PYTHONIOENCODING"] = "utf-8"
    cuda_home = _proc.detect_cuda_home()
    if cuda_home:
        env["CUDA_HOME"] = cuda_home
        env["CUDA_PATH"] = cuda_home
        _proc._prepend_env_path(env, "PATH", str(Path(cuda_home) / "bin"))
        _proc._prepend_env_path(env, "LD_LIBRARY_PATH", str(Path(cuda_home) / "lib64"))
    master_port = _proc.pick_free_port(29601)
    env["MASTER_PORT"] = str(master_port)
    env["NPROC_PER_NODE"] = str(int(max(1, nproc_per_node)))
    runtime = {
        "nproc_per_node": int(max(1, nproc_per_node)),
        "master_port": int(master_port),
        "cuda_home": cuda_home,
        "cuda_visible_devices": env.get("CUDA_VISIBLE_DEVICES", "").strip(),
    }
    return env, runtime


def infer_template(model_path: str) -> str:
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


# ---------- YAML builder ----------

def build_train_yaml(cfg: Dict[str, Any]) -> str:
    """Given a config dict, produce the LLaMA-Factory training YAML.

    Expected keys:
      model_path, dataset_name, output_dir, template, finetuning_type,
      lora_rank, lora_alpha, lora_dropout,
      learning_rate, warmup_ratio, num_train_epochs,
      per_device_train_batch_size, gradient_accumulation_steps,
      cutoff_len, max_samples, logging_steps, save_steps
    """
    model_path = str(cfg["model_path"]).replace(os.sep, "/")
    output_dir = str(cfg["output_dir"]).replace(os.sep, "/")
    ft_type = str(cfg["finetuning_type"])
    lines = [
        "### model",
        f"model_name_or_path: {model_path}",
        "trust_remote_code: true",
        "",
        "### method",
        "stage: sft",
        "do_train: true",
        f"finetuning_type: {ft_type}",
    ]
    if ft_type in {"lora", "qlora"}:
        lines.append(f"lora_rank: {int(cfg['lora_rank'])}")
        lines.append(f"lora_alpha: {int(cfg['lora_alpha'])}")
        lines.append(f"lora_dropout: {float(cfg['lora_dropout'])}")
        lines.append("lora_target: all")
    if ft_type == "qlora":
        lines.append("quantization_bit: 4")
    lines.extend(
        [
            "",
            "### dataset",
            f"dataset: {cfg['dataset_name']}",
            f"template: {cfg['template']}",
            f"cutoff_len: {int(cfg['cutoff_len'])}",
            f"max_samples: {int(cfg['max_samples'])}",
            "overwrite_cache: true",
            "preprocessing_num_workers: 8",
            "",
            "### output",
            f"output_dir: {output_dir}",
            f"logging_steps: {int(cfg['logging_steps'])}",
            f"save_steps: {int(cfg['save_steps'])}",
            "plot_loss: true",
            "overwrite_output_dir: true",
            "save_only_model: false",
            "report_to: none",
            "",
            "### train",
            f"per_device_train_batch_size: {int(cfg['per_device_train_batch_size'])}",
            f"gradient_accumulation_steps: {int(cfg['gradient_accumulation_steps'])}",
            f"learning_rate: {float(cfg['learning_rate'])}",
            f"num_train_epochs: {float(cfg['num_train_epochs'])}",
            "lr_scheduler_type: cosine",
            f"warmup_ratio: {float(cfg['warmup_ratio'])}",
            "bf16: true",
            "ddp_timeout: 180000000",
            "do_eval: false",
            'eval_strategy: "no"',
        ]
    )
    return "\n".join(lines) + "\n"


# ---------- Metrics parsing ----------

_LOSS_RE = re.compile(
    r"(?:'|\")?(?:loss|train_loss)(?:'|\")?\s*[:=]\s*([0-9]*\.?[0-9]+(?:e[-+]?\d+)?)",
    re.I,
)
_LR_RE = re.compile(
    r"(?:'|\")?(?:learning_rate|lr)(?:'|\")?\s*[:=]\s*([0-9]*\.?[0-9]+(?:e[-+]?\d+)?)",
    re.I,
)
_STEP_RE = re.compile(r"(?:'|\")?(?:step|global_step)(?:'|\")?\s*[:=]\s*([0-9]+)", re.I)


def parse_metrics_jsonl(path: Path, max_points: int = 4000) -> List[Dict[str, float]]:
    if not path.exists():
        return []
    out: List[Dict[str, float]] = []
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
        lr = obj.get("lr") or obj.get("learning_rate")
        if cur is None and loss is None and lr is None:
            continue
        idx += 1
        row: Dict[str, float] = {"idx": float(idx)}
        if cur is not None:
            try:
                row["step"] = float(cur)
            except Exception:
                pass
        if total is not None:
            try:
                row["total_steps"] = float(total)
            except Exception:
                pass
        if loss is not None:
            try:
                row["loss"] = float(loss)
            except Exception:
                pass
        if lr is not None:
            try:
                row["lr"] = float(lr)
            except Exception:
                pass
        if "step" not in row:
            row["step"] = float(idx)
        out.append(row)
    if len(out) > max_points:
        out = out[-max_points:]
    return out


def parse_metrics_stdout(log_text: str, max_points: int = 4000) -> List[Dict[str, float]]:
    points: List[Dict[str, float]] = []
    idx = 0
    for line in log_text.splitlines():
        m_loss = _LOSS_RE.search(line)
        m_lr = _LR_RE.search(line)
        if not m_loss and not m_lr:
            continue
        idx += 1
        m_step = _STEP_RE.search(line)
        step_val = int(m_step.group(1)) if m_step else idx
        row: Dict[str, float] = {"idx": float(idx), "step": float(step_val)}
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
        if len(row) > 2:
            points.append(row)
    if len(points) > max_points:
        points = points[-max_points:]
    return points


# ---------- Finish detection ----------

_SUCCESS_MARKS = ("train_runtime", "Training completed", "Saving model checkpoint")
_FINISH_MARKS = ("train_runtime", "Training completed", "***** train metrics *****")


def looks_like_training_finished(log_text: str) -> bool:
    low = log_text.lower()
    return any(m.lower() in low for m in _FINISH_MARKS)


def looks_like_training_success(output_dir: Path, log_text: str) -> bool:
    if output_dir.exists():
        if (output_dir / "trainer_state.json").exists() or (output_dir / "training_args.bin").exists():
            return True
        if any(p.name.startswith("checkpoint-") for p in output_dir.glob("*")):
            return True
    return any(x.lower() in log_text.lower() for x in _SUCCESS_MARKS)


def jsonl_reaches_end(path: Path) -> bool:
    if not path.exists():
        return False
    last: Dict[str, Any] = {}
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            last = obj
    if not last:
        return False
    cur = last.get("current_steps")
    total = last.get("total_steps")
    try:
        return cur is not None and total is not None and int(cur) >= int(total) > 0
    except Exception:
        return False


# ---------- Output tree ----------

def list_output_tree(output_dir: Path) -> List[Dict[str, Any]]:
    if not output_dir.exists():
        return []
    entries: List[Dict[str, Any]] = []
    for p in sorted(output_dir.iterdir(), key=lambda x: x.name):
        kind = "dir" if p.is_dir() else "file"
        size = 0
        if p.is_file():
            try:
                size = p.stat().st_size
            except Exception:
                size = 0
        entry: Dict[str, Any] = {
            "name": p.name,
            "kind": kind,
            "size": size,
        }
        if p.is_dir() and p.name.startswith("checkpoint-"):
            try:
                entry["step"] = int(p.name.split("-", 1)[1])
            except Exception:
                pass
        entries.append(entry)
    return entries


# ---------- Log tail helpers ----------

def read_tail(path: Path, max_lines: int = 500) -> str:
    if not path.exists():
        return ""
    try:
        data = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    lines = data.splitlines()
    return "\n".join(lines[-max_lines:])


def read_tail_from_offset(path: Path, offset: int, max_bytes: int = 200_000) -> Tuple[str, int]:
    """Read bytes starting from `offset`; return (text, new_offset). Tolerant of truncation."""
    if not path.exists():
        return "", offset
    try:
        size = path.stat().st_size
    except Exception:
        return "", offset
    if offset > size:
        offset = 0  # file truncated / rotated
    read_len = min(max_bytes, max(0, size - offset))
    if read_len <= 0:
        return "", offset
    with path.open("rb") as f:
        f.seek(offset)
        raw = f.read(read_len)
    new_offset = offset + len(raw)
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        text = ""
    return text, new_offset


# ---------- Settings persistence ----------

def settings_path() -> Path:
    return Path.home() / ".proda_config.json"


def load_settings() -> Dict[str, Any]:
    p = settings_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_settings(payload: Dict[str, Any]) -> None:
    settings_path().write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def effective_llamafactory_path(project_root: Path) -> Path:
    override = str((load_settings() or {}).get("llamafactory_path", "")).strip()
    if override:
        p = Path(override).expanduser()
        if llamafactory_path_ok(p):
            return p
    return default_llamafactory_path(project_root)


# ---------- CLI command resolution ----------

def resolve_train_cmd(
    python_exe: str,
    cfg_path: str,
    nproc_per_node: int,
    master_port: int,
) -> List[str]:
    if nproc_per_node > 1:
        if shutil.which("torchrun"):
            return [
                "torchrun",
                f"--nproc_per_node={int(nproc_per_node)}",
                f"--master_port={int(master_port)}",
                "src/train.py",
                str(cfg_path),
            ]
        return [
            python_exe,
            "-m",
            "torch.distributed.run",
            f"--nproc_per_node={int(nproc_per_node)}",
            f"--master_port={int(master_port)}",
            "src/train.py",
            str(cfg_path),
        ]
    if shutil.which("llamafactory-cli"):
        return ["llamafactory-cli", "train", str(cfg_path)]
    return [python_exe, "src/train.py", str(cfg_path)]


def is_probably_running_llamafactory(pid: int) -> bool:
    """Tighter liveness check: must be running AND look like our training command."""
    return _proc.is_cmdline_match(
        pid,
        ("train.py", "llamafactory-cli", "torch.distributed", "torchrun"),
    )
