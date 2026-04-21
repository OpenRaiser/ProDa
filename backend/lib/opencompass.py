"""Shared helpers for Phase 6 OpenCompass evaluation."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.lib import proc as _proc
from backend.lib.llama_factory import load_settings, save_settings, settings_path  # noqa: F401

# We reuse proda.evaluator for config generation + summary parsing so the
# Streamlit version and the Web IDE version stay behaviourally identical.
from proda import evaluator as _ev


# ---------- Path discovery ----------

def default_opencompass_path(project_root: Path) -> Path:
    candidates = [
        project_root / "opencompass",
        project_root.parent / "opencompass",
        Path("/mnt/petrelfs/tancheng/work_dir/panck/opencompass"),
    ]
    for c in candidates:
        if (c / "run.py").exists():
            return c
    return candidates[0]


def opencompass_path_ok(path: Path) -> bool:
    return (path / "run.py").exists()


def effective_opencompass_path(project_root: Path) -> Path:
    settings = load_settings()
    override = str((settings or {}).get("opencompass_path", "")).strip()
    if override:
        p = Path(override).expanduser()
        if opencompass_path_ok(p):
            return p
    return default_opencompass_path(project_root)


def find_opencompass_dir(start: Optional[Path] = None) -> Optional[Path]:
    return _ev.find_opencompass_dir(start)


# ---------- Liveness ----------

def is_probably_running_opencompass(pid: int) -> bool:
    return _proc.is_cmdline_match(
        pid,
        ("run.py", "opencompass"),
    )


# ---------- Peft / model output discovery ----------

def list_peft_candidates(project_dir: Path) -> List[Dict[str, Any]]:
    """Scan `{project_dir}/model_outputs/**/adapter_config.json` for LoRA adapters."""
    root = project_dir / "model_outputs"
    if not root.exists():
        return []
    seen: List[str] = []
    out: List[Dict[str, Any]] = []
    for cfg in sorted(root.rglob("adapter_config.json"), key=lambda p: str(p)):
        adapter_dir = cfg.parent
        key = str(adapter_dir)
        if key in seen:
            continue
        seen.append(key)
        # Try to pull the base model from adapter_config.json for a better hint.
        base_model = ""
        try:
            cfg_data = json.loads(cfg.read_text(encoding="utf-8"))
            base_model = str(
                cfg_data.get("base_model_name_or_path") or cfg_data.get("base_model") or ""
            )
        except Exception:
            pass
        out.append(
            {
                "adapter_path": str(adapter_dir),
                "base_model": base_model,
                "name": adapter_dir.name,
                "relative": str(adapter_dir.relative_to(root)) if adapter_dir.is_relative_to(root) else str(adapter_dir),
            }
        )
    return out


# ---------- Benchmarks ----------

def list_benchmark_uploads(project_dir: Path) -> List[Dict[str, Any]]:
    root = project_dir / "evaluations" / "opencompass" / "inputs"
    if not root.exists():
        return []
    out: List[Dict[str, Any]] = []
    for f in sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        if not f.is_file():
            continue
        rows: List[Dict[str, Any]] = []
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, list):
                rows = [r for r in data if isinstance(r, dict)]
        except Exception:
            continue
        if not rows:
            continue
        out.append(
            {
                "path": str(f),
                "name": f.stem,
                "row_count": len(rows),
                "mtime": f.stat().st_mtime,
            }
        )
    return out


# ---------- Model normalization ----------

REQUIRED_MODEL_FIELDS = {"abbr"}


def normalize_model(m: Dict[str, Any]) -> Dict[str, Any]:
    m = dict(m or {})
    m.setdefault("enabled", True)
    m.setdefault("is_local", True)
    m["abbr"] = str(m.get("abbr", "")).strip()
    m["path"] = str(m.get("path", "")).strip()
    m["peft_path"] = str(m.get("peft_path", "")).strip()
    m["api_key"] = str(m.get("api_key", "")).strip()
    m["api_base"] = str(m.get("api_base", "")).strip()
    m["temperature"] = float(m.get("temperature", 0.0) or 0.0)
    m["max_out_len"] = int(m.get("max_out_len") or (15 if m["is_local"] else 50))
    m["query_per_second"] = int(m.get("query_per_second") or 4)
    m["num_procs"] = int(m.get("num_procs") or 4)
    m["batch_size"] = int(m.get("batch_size") or 1)
    m["num_gpus"] = int(m.get("num_gpus") or (1 if m["is_local"] else 0))
    # If user pointed `path` at a LoRA adapter, swap to base model + peft_path.
    if m["is_local"] and m["path"] and not m["peft_path"]:
        adapter_cfg = Path(m["path"]) / "adapter_config.json"
        if adapter_cfg.exists():
            try:
                ac = json.loads(adapter_cfg.read_text(encoding="utf-8"))
                base = str(ac.get("base_model_name_or_path") or "").strip()
                if base:
                    m["peft_path"] = m["path"]
                    m["path"] = base
            except Exception:
                pass
    return m


def validate_models(models: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    errors: List[str] = []
    normalized: List[Dict[str, Any]] = []
    abbrs: set[str] = set()
    for i, raw in enumerate(models or []):
        m = normalize_model(raw)
        if not m["enabled"]:
            continue
        if not m["abbr"]:
            errors.append(f"model[{i}]: abbr is required")
            continue
        if m["abbr"] in abbrs:
            errors.append(f"model[{i}]: duplicate abbr '{m['abbr']}'")
            continue
        abbrs.add(m["abbr"])
        if m["is_local"]:
            if not m["path"]:
                errors.append(f"model[{i}] ({m['abbr']}): local model requires path")
                continue
        else:
            if not m["path"]:
                errors.append(f"model[{i}] ({m['abbr']}): API model requires path (model id)")
                continue
            if not m["api_key"]:
                errors.append(f"model[{i}] ({m['abbr']}): API model requires api_key")
                continue
        normalized.append(m)
    return normalized, errors


# ---------- Run command resolution ----------

def resolve_eval_cmd(python_exe: str, cfg_path: str, work_dir: str) -> List[str]:
    # OpenCompass is launched via its own run.py; there is no installed CLI we can rely on.
    return [python_exe, "run.py", str(cfg_path), "--work-dir", str(work_dir)]


def build_eval_env(base_env: Dict[str, str], opencompass_dir: Path) -> Dict[str, str]:
    env = dict(base_env)
    env["PYTHONUNBUFFERED"] = "1"
    # Ensure the child process writes UTF-8 to the captured log file even on
    # Windows where the default code page (GBK/CP936) would otherwise drop
    # Unicode characters common in ML output (✓, ❌, ▶, training metrics …).
    env["PYTHONIOENCODING"] = "utf-8"
    existing = env.get("PYTHONPATH", "")
    pp_entries = [x for x in existing.split(os.pathsep) if x]
    # Primary: the OpenCompass repo itself must be importable.
    if str(opencompass_dir) not in pp_entries:
        pp_entries.insert(0, str(opencompass_dir))
    # Some fleet setups have a sibling opencompass clone one level up.
    sibling = opencompass_dir.parent.parent / "opencompass"
    if sibling.exists() and sibling.is_dir() and str(sibling.resolve()) not in pp_entries:
        pp_entries.insert(0, str(sibling.resolve()))
    env["PYTHONPATH"] = os.pathsep.join(pp_entries)
    return env


# ---------- Config generation (wraps evaluator.generate_opencompass_config) ----------

def generate_eval_config(
    benchmark_json: Path,
    models: List[Dict[str, Any]],
    work_dir: Path,
    opencompass_dir: Path,
    max_samples: Optional[int] = None,
    dataset_abbr: str = "proda_bench",
) -> Path:
    return _ev.generate_opencompass_config(
        benchmark_json=benchmark_json,
        models=models,
        work_dir=work_dir,
        opencompass_dir=opencompass_dir,
        max_samples=max_samples,
        dataset_abbr=dataset_abbr,
    )


# ---------- Result extraction ----------

def find_summary(work_dir: Path) -> Tuple[Optional[Path], Optional[Path], Optional[Any]]:
    return _ev._find_summary(work_dir)


def parse_for_viz(summary_data: Any, models: List[Dict[str, Any]]) -> Dict[str, Any]:
    return _ev.parse_results_for_viz(summary_data=summary_data, models=models)


# ---------- Sample-level extraction ----------

def _load_json_safe(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def collect_samples(
    run_dir: Path,
    benchmark_rows: List[Dict[str, Any]],
    models: List[Dict[str, Any]],
    dataset_abbr: str = "proda_bench",
) -> List[Dict[str, Any]]:
    """Build per-sample × per-model drill-down rows.

    Looks for `{run_dir}/results/{model_abbr}/{dataset_abbr}.json` that OpenCompass
    writes, extracts its `details` dict (indexed by sample id), merges with original
    benchmark row, and returns flat list of
    `{model, idx, question, options, gold, prediction, pass, subject, question_type, knowledge_node, sample_id}`.
    """
    out: List[Dict[str, Any]] = []
    if not run_dir or not Path(run_dir).exists():
        return out

    run_dir = Path(run_dir)
    results_dir = run_dir / "results"
    for m in models:
        if not m.get("enabled", True):
            continue
        abbr = str(m.get("abbr", "")).strip()
        if not abbr:
            continue
        candidate = results_dir / abbr / f"{dataset_abbr}.json"
        if not candidate.exists():
            # OpenCompass sometimes nests the abbr inside nested model_abbr folders;
            # scan one level deeper as a best-effort fallback.
            nested = list((results_dir / abbr).glob(f"**/{dataset_abbr}.json"))
            if not nested:
                continue
            candidate = nested[0]
        data = _load_json_safe(candidate, {})
        if not isinstance(data, dict):
            continue
        details = data.get("details") or {}
        if not isinstance(details, dict):
            continue
        for key_raw, entry in details.items():
            try:
                idx = int(key_raw)
            except Exception:
                try:
                    idx = int(str(key_raw).lstrip("0") or "0")
                except Exception:
                    continue
            if not isinstance(entry, dict):
                continue
            row = benchmark_rows[idx] if 0 <= idx < len(benchmark_rows) else {}
            prediction = str(entry.get("pred") or entry.get("prediction") or "")
            gold = str(entry.get("gold") or entry.get("answers") or row.get("answer") or "")
            is_correct = entry.get("correct")
            if is_correct is None:
                # Best-effort accuracy check
                norm = lambda s: re.sub(r"[^A-Za-z]", "", str(s or "")).upper()
                is_correct = bool(prediction and norm(prediction) == norm(gold))
            out.append(
                {
                    "model": abbr,
                    "idx": idx,
                    "sample_id": str(row.get("sample_id") or idx),
                    "question": str(row.get("question", "")),
                    "options": row.get("options") or {},
                    "gold": gold,
                    "prediction": prediction,
                    "pass": bool(is_correct),
                    "subject": str(row.get("domain_context") or row.get("subject") or ""),
                    "process_name": str(row.get("process_name", "")),
                    "question_type": str(row.get("question_type", "")),
                    "knowledge_node": str(
                        row.get("knowledge_node") or row.get("chain_id") or ""
                    ),
                    "explanation": str(row.get("explanation", "")),
                }
            )
    # Stable ordering: by model → by idx
    out.sort(key=lambda x: (str(x.get("model", "")), int(x.get("idx", 0))))
    return out
