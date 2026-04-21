"""
ProDA Evaluator — OpenCompass integration layer.

Responsibilities:
  1. Generate OpenCompass config (.py) from benchmark JSON data + model configs
  2. Launch opencompass (subprocess) and stream stdout
  3. Parse summary CSV/TXT produced by OpenCompass
  4. Post-process prediction files (normalize option letters)
  5. Build visualization-ready result structures

Adapted from:
  - OpenDataBench-pck/opendatabench/integrations/opencompass.py
  - opencompass/opencompass/configs/ENevalLocalQwenSFTPck.py
  - opencompass/opencompass/configs/ENevalOpenAIAPIBench.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

OPTION_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# ──────────────────────────────────────────────────────────────
# Config generation
# ──────────────────────────────────────────────────────────────

PROMPT_MCQ = """\
Please answer the following multiple-answer question. There may be 1-4 correct options.
Output ONLY the option letters separated by commas (e.g., "A" or "A,B" or "A,B,C").
Do NOT add any explanation.

Important:
- Output format: comma-separated letters like "A" or "A,B"
- No spaces (use "A,B" not "A, B")
- Output letters only; if multiple, sort alphabetically

Question: {question}
A. {A}
B. {B}
C. {C}
D. {D}
Answer:"""

PROMPT_SIMPLE = "{question}\n\nAnswer:"


def _json_to_jsonl(json_path: Path, cache_dir: Path) -> Path:
    """Convert a JSON list file → JSONL, flattening options dict."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = cache_dir / json_path.with_suffix(".jsonl").name

    if jsonl_path.exists() and jsonl_path.stat().st_mtime >= json_path.stat().st_mtime:
        return jsonl_path

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(f"Benchmark JSON must be a list: {json_path}")

    with open(jsonl_path, "w", encoding="utf-8") as f:
        for item in data:
            if isinstance(item, dict):
                opts = item.get("options")
                if isinstance(opts, dict):
                    for k in ["A", "B", "C", "D"]:
                        if k in opts and k not in item:
                            item[k] = opts[k]
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    return jsonl_path


def generate_opencompass_config(
    benchmark_json: Path,
    models: List[Dict[str, Any]],
    work_dir: Path,
    opencompass_dir: Path,
    max_samples: Optional[int] = None,
    dataset_abbr: str = "proda_bench",
) -> Path:
    """
    Generate a complete OpenCompass config .py file.

    Args:
        benchmark_json:  Path to the benchmark JSON (list of MCQ items)
        models:          List of model dicts (see ModelConfig schema below)
        work_dir:        Output dir for this evaluation run
        opencompass_dir: Root of the opencompass installation
        max_samples:     Limit dataset size (None = all)
        dataset_abbr:    Short name for this benchmark

    Model dict keys (API model):
        abbr, path, api_key, api_base, max_out_len=50, temperature=0.0,
        query_per_second=4, num_procs=2

    Model dict keys (local HuggingFace):
        abbr, path, peft_path (optional), max_out_len=15, batch_size=8,
        num_gpus=1, model_type="HuggingFacewithChatTemplate"

    Returns:
        Path to the generated .py config file.
    """
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. Convert benchmark to JSONL ──────────────────────────
    jsonl_cache = work_dir / "_jsonl_cache"
    jsonl_path = _json_to_jsonl(benchmark_json, jsonl_cache)
    jsonl_abs = str(jsonl_path.resolve())

    test_range_line = (
        f"                test_range='[0:{max_samples}]'," if max_samples else ""
    )

    # ── 2. Build dataset block ─────────────────────────────────
    dataset_block = f"""
datasets = [
    dict(
        abbr='{dataset_abbr}',
        type=CustomDataset,
        path='{jsonl_abs}',
        local_mode=True,
        reader_cfg=dict(
            input_columns=['question', 'A', 'B', 'C', 'D'],
            output_column='answer',{test_range_line}
        ),
        infer_cfg=dict(
            prompt_template=dict(
                type='PromptTemplate',
                template=dict(
                    round=[
                        dict(
                            role='HUMAN',
                            prompt=(
                                'Please answer the following multiple-answer question. '
                                'There may be 1-4 correct options.\\n'
                                'Output ONLY the option letters separated by commas '
                                '(e.g., "A" or "A,B" or "A,B,C,D"). No explanation.\\n\\n'
                                'Question: {{question}}\\n'
                                'A. {{A}}\\nB. {{B}}\\nC. {{C}}\\nD. {{D}}\\n'
                                'Answer:'
                            ),
                        )
                    ]
                ),
            ),
            retriever=dict(type='ZeroRetriever'),
            inferencer=dict(type='GenInferencer'),
        ),
        eval_cfg=dict(
            evaluator=dict(type=AccEvaluator),
            pred_postprocessor=dict(type='parse_multi_choice_answer'),
        ),
    ),
]
"""

    # ── 3. Build models block ──────────────────────────────────
    models_lines: List[str] = ["models = ["]
    for m in models:
        if m.get("is_local", False):
            _append_local_model(models_lines, m)
        else:
            _append_api_model(models_lines, m)
    models_lines.append("]")
    models_block = "\n".join(models_lines)

    # ── 4. Full config content ─────────────────────────────────
    oc_dir_abs = str(Path(opencompass_dir).resolve())
    config_content = f"""\
# Auto-generated by ProDA Studio
# Generated at: {datetime.now().isoformat()}
import os
os.environ.setdefault('MKL_SERVICE_FORCE_INTEL', '1')
del os

import sys
_oc_path = {repr(oc_dir_abs)}
if _oc_path not in sys.path:
    sys.path.insert(0, _oc_path)
del sys

from opencompass.datasets import CustomDataset
from opencompass.models import HuggingFacewithChatTemplate, OpenAISDK
from opencompass.openicl.icl_evaluator import AccEvaluator

{dataset_block}

{models_block}

work_dir = {repr(str((work_dir / 'runs').resolve()))}

__all__ = ['datasets', 'models']
"""

    config_path = work_dir / f"{dataset_abbr}_config.py"
    config_path.write_text(config_content, encoding="utf-8")
    return config_path


def _append_api_model(lines: List[str], m: Dict[str, Any]) -> None:
    """Append OpenAI-compatible API model dict to lines list."""
    abbr = m.get("abbr", "api_model")
    path = m.get("path", m.get("model", "gpt-4o-mini"))
    api_key = m.get("api_key", "ENV")
    api_base = str(m.get("api_base", "https://api.openai.com/v1")).rstrip("/")
    if not api_base:
        api_base = "https://api.openai.com/v1"
    max_out = m.get("max_out_len", 50)
    temp = m.get("temperature", 0.0)
    qps = m.get("query_per_second", 4)
    num_procs = m.get("num_procs", 2)

    lines += [
        "    dict(",
        f"        type=OpenAISDK,",
        f"        abbr={repr(abbr)},",
        f"        path={repr(path)},",
        f"        key={repr(api_key)},",
        f"        tokenizer_path='gpt-4',",
        f"        openai_api_base={repr(api_base)},",
        f"        meta_template=dict(round=[",
        f"            dict(role='HUMAN', api_role='HUMAN'),",
        f"            dict(role='BOT', api_role='BOT', generate=True),",
        f"        ]),",
        f"        query_per_second={qps},",
        f"        retry=3,",
        f"        temperature={temp},",
        f"        max_out_len={max_out},",
        f"        max_seq_len=8192,",
        f"        batch_size=16,",
        f"        run_cfg=dict(num_gpus=0, num_procs={num_procs}),",
        "    ),",
    ]


def _append_local_model(lines: List[str], m: Dict[str, Any]) -> None:
    """Append local HuggingFace model dict to lines list."""
    abbr = m.get("abbr", "local_model")
    path = str(m.get("path", "")).strip()
    peft = str(m.get("peft_path", "")).strip()

    # If user mistakenly sets LoRA adapter dir as model path, try to auto-fix:
    #   path <- adapter_config.base_model_name_or_path, peft_path <- original path
    path_obj = Path(path).expanduser() if path else None
    if path_obj and path_obj.is_dir() and (path_obj / "adapter_config.json").exists() and not (path_obj / "config.json").exists():
        if not peft:
            peft = str(path_obj)
        try:
            adapter_cfg = json.loads((path_obj / "adapter_config.json").read_text(encoding="utf-8"))
            base_path = str(adapter_cfg.get("base_model_name_or_path", "")).strip()
            if base_path:
                base_obj = Path(base_path).expanduser()
                if base_obj.exists():
                    path = str(base_obj)
        except Exception:
            pass

    max_out = m.get("max_out_len", 15)
    batch = m.get("batch_size", 8)
    num_gpus = m.get("num_gpus", 1)
    model_type = m.get("model_type", "HuggingFacewithChatTemplate")

    lines += [
        "    dict(",
        f"        type={model_type},",
        f"        abbr={repr(abbr)},",
        f"        path={repr(path)},",
    ]
    if peft:
        lines.append(f"        peft_path={repr(peft)},")
    lines += [
        "        model_kwargs=dict(device_map='auto', trust_remote_code=True),",
        f"        max_out_len={max_out},",
        f"        batch_size={batch},",
        f"        run_cfg=dict(num_gpus={num_gpus}, num_procs=1),",
        "    ),",
    ]


# ──────────────────────────────────────────────────────────────
# Runner
# ──────────────────────────────────────────────────────────────

def run_opencompass(
    config_path: Path,
    opencompass_dir: Path,
    work_dir: Path,
    python_executable: Optional[str] = None,
) -> Generator[str, None, Dict[str, Any]]:
    """
    Run OpenCompass and yield log lines.

    Yields:
        str lines from stdout/stderr

    Returns (via StopIteration.value):
        dict with keys: success, returncode, stdout, stderr,
                        run_dir, summary_file, summary_data
    """
    config_path = Path(config_path).resolve()
    opencompass_dir = Path(opencompass_dir).resolve()
    work_dir = Path(work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    run_py = opencompass_dir / "run.py"
    if not run_py.exists():
        yield f"❌ run.py not found in {opencompass_dir}\n"
        return {"success": False, "error": f"run.py not found: {run_py}"}

    python = python_executable or sys.executable
    cmd = [python, str(run_py), str(config_path), "--work-dir", str(work_dir)]

    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    pp_entries = [x for x in existing.split(os.pathsep) if x]
    fixed_external = "/mnt/petrelfs/tancheng/work_dir/panck/opencompass"
    if Path(fixed_external).exists() and fixed_external not in pp_entries:
        pp_entries.insert(0, fixed_external)
    candidates = [str(opencompass_dir)]
    sibling_oc = opencompass_dir.parent.parent / "opencompass"
    if sibling_oc.exists() and sibling_oc.is_dir():
        candidates.append(str(sibling_oc.resolve()))
    for c in candidates:
        if c not in pp_entries:
            pp_entries.insert(0, c)
    env["PYTHONPATH"] = os.pathsep.join(pp_entries)

    yield f"▶ Running: {' '.join(cmd)}\n"
    yield f"  cwd: {opencompass_dir}\n\n"

    stdout_acc: List[str] = []
    stderr_acc: List[str] = []

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(opencompass_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in proc.stdout:
            stdout_acc.append(line)
            yield line
        proc.wait()
        returncode = proc.returncode
    except Exception as e:
        yield f"❌ Failed to start process: {e}\n"
        return {"success": False, "error": str(e)}

    # ── Parse results ──────────────────────────────────────────
    run_dir, summary_file, summary_data = _find_summary(work_dir)
    if summary_data is None:
        parsed = _parse_summary_from_stdout("".join(stdout_acc))
        if parsed is not None:
            summary_data = parsed

    success = returncode == 0
    if success:
        yield f"\n✅ OpenCompass finished (returncode={returncode})\n"
    else:
        yield f"\n❌ OpenCompass exited with code {returncode}\n"

    return {
        "success": success,
        "returncode": returncode,
        "stdout": "".join(stdout_acc),
        "stderr": "".join(stderr_acc),
        "run_dir": str(run_dir) if run_dir else None,
        "summary_file": str(summary_file) if summary_file else None,
        "summary_data": summary_data,
    }


def _find_summary(
    work_dir: Path,
) -> Tuple[Optional[Path], Optional[Path], Optional[Any]]:
    """Locate the latest OpenCompass summary file under work_dir."""
    if not work_dir.exists():
        return None, None, None

    all_dirs = [d for d in work_dir.iterdir() if d.is_dir()]
    ts_dirs = [d for d in all_dirs if re.fullmatch(r"\d{8}_\d{6}", d.name or "")]
    run_dirs = sorted(ts_dirs, key=lambda d: d.name, reverse=True)
    if not run_dirs:
        dirs_with_summary = [d for d in all_dirs if (d / "summary").exists()]
        run_dirs = sorted(dirs_with_summary, key=lambda d: d.name, reverse=True)
    if not run_dirs:
        run_dirs = sorted(all_dirs, key=lambda d: d.name, reverse=True)
    if not run_dirs:
        return None, None, None

    run_dir = run_dirs[0]
    summary_dir = run_dir / "summary"
    if not summary_dir.exists():
        return run_dir, None, None

    csvs = sorted(summary_dir.glob("summary_*.csv"), key=lambda f: f.stat().st_mtime, reverse=True)
    txts = sorted(summary_dir.glob("summary_*.txt"), key=lambda f: f.stat().st_mtime, reverse=True)
    files = csvs + txts
    if not files:
        return run_dir, None, None

    summary_file = files[0]
    try:
        if summary_file.suffix == ".csv":
            rows = []
            with open(summary_file, "r", encoding="utf-8") as f:
                import csv
                reader = csv.DictReader(f)
                for row in reader:
                    rows.append(dict(row))
            return run_dir, summary_file, rows
        else:
            return run_dir, summary_file, summary_file.read_text(encoding="utf-8")
    except Exception:
        return run_dir, summary_file, None


def _parse_summary_from_stdout(stdout_text: str) -> Optional[List[Dict[str, Any]]]:
    """Parse markdown summary table from OpenCompass stdout."""
    if not stdout_text:
        return None
    lines = stdout_text.splitlines()
    table_start = -1
    for i, line in enumerate(lines):
        if "|" in line and "dataset" in line.lower() and "metric" in line.lower():
            table_start = i
            break
    if table_start < 0:
        return None

    table_lines: List[str] = []
    for line in lines[table_start:]:
        if "|" not in line:
            if table_lines:
                break
            continue
        table_lines.append(line.strip())
    if len(table_lines) < 3:
        return None

    def _split_row(row: str) -> List[str]:
        return [x.strip() for x in row.strip().strip("|").split("|")]

    headers = _split_row(table_lines[0])
    rows: List[Dict[str, Any]] = []
    for raw in table_lines[2:]:
        if set(raw.replace("|", "").strip()) <= {"-", ":"}:
            continue
        vals = _split_row(raw)
        if len(vals) != len(headers):
            continue
        rows.append(dict(zip(headers, vals)))
    return rows or None


# ──────────────────────────────────────────────────────────────
# Result parsing for visualization
# ──────────────────────────────────────────────────────────────

def parse_results_for_viz(
    summary_data: Any,
    models: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Convert OpenCompass summary CSV rows → chart-ready data.

    Returns:
        {
          "leaderboard": [{"model": str, "accuracy": float, "rank": int}, ...],
          "per_dataset": {model_abbr: {dataset: accuracy}},
          "raw": summary_data,
        }
    """
    if not summary_data or not isinstance(summary_data, list):
        return {"leaderboard": [], "per_dataset": {}, "raw": summary_data}

    model_abbrs = {str(m.get("abbr", "")).strip() for m in models if str(m.get("abbr", "")).strip()}

    leaderboard: List[Dict[str, Any]] = []
    per_dataset: Dict[str, Dict[str, float]] = {}

    for row in summary_data:
        if not isinstance(row, dict):
            continue
        dataset_name = str(row.get("dataset", "")).strip()
        if not dataset_name:
            for k, v in row.items():
                if str(k).strip().lower() in {"", "unnamed: 0", "index"}:
                    dataset_name = str(v).strip()
                    break
        if not dataset_name:
            dataset_name = "unknown_dataset"
        for col, val in row.items():
            col_name = str(col).strip()
            if col_name.lower() in {"dataset", "", "unnamed: 0", "index"}:
                continue
            if model_abbrs and col_name not in model_abbrs:
                # If we know model list, skip aggregate/non-model columns.
                continue
            try:
                acc = float(str(val).replace("%", "").strip())
            except (ValueError, TypeError):
                continue
            per_dataset.setdefault(col_name, {})[dataset_name] = acc

    # Build leaderboard (average accuracy per model)
    for abbr, datasets in per_dataset.items():
        vals = [v for v in datasets.values() if v is not None]
        avg_acc = sum(vals) / len(vals) if vals else 0.0
        leaderboard.append({"model": abbr, "accuracy": avg_acc})

    leaderboard.sort(key=lambda x: x["accuracy"], reverse=True)
    for i, item in enumerate(leaderboard):
        item["rank"] = i + 1

    return {
        "leaderboard": leaderboard,
        "per_dataset": per_dataset,
        "raw": summary_data,
    }


# ──────────────────────────────────────────────────────────────
# Detection helpers
# ──────────────────────────────────────────────────────────────

def find_opencompass_dir(start: Optional[Path] = None) -> Optional[Path]:
    """Search upward from start for an OpenCompass installation."""
    search = Path(start or Path(__file__).parent).resolve()
    for _ in range(10):
        candidate = search / "opencompass"
        if candidate.is_dir() and (candidate / "run.py").exists():
            return candidate
        candidate2 = search / "OpenCompass"
        if candidate2.is_dir() and (candidate2 / "run.py").exists():
            return candidate2
        parent = search.parent
        if parent == search:
            break
        search = parent
    return None


def list_benchmark_jsons(benchmark_dir: Path) -> List[Path]:
    """Return sorted list of JSON benchmark files in a directory."""
    if not benchmark_dir.is_dir():
        return []
    return sorted(benchmark_dir.glob("*.json"))
