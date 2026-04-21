from __future__ import annotations

import json
import html
import re
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from proda.evaluator import (  # noqa: E402
    find_opencompass_dir,
    generate_opencompass_config,
    parse_results_for_viz,
    run_opencompass,
)
from ui.components.opencompass_visualizer import (  # noqa: E402
    render_comparison_tab,
    render_leaderboard_tab,
    render_quick_insights,
    render_visualization_tab,
)
from ui.components.opencompass_test_panel import render_opencompass_test_panel  # noqa: E402
from ui.components.top_bar import render_top_bar, selected_model_context  # noqa: E402
from ui.utils.i18n_helper import init_i18n, t  # noqa: E402
from ui.utils.project_store import project_dir_path  # noqa: E402
from ui.utils.session_state import SessionStateManager  # noqa: E402
from ui.utils.ui_helpers import enforce_active_project, render_workflow_sidebar  # noqa: E402


st.set_page_config(page_title="ProDA", page_icon="📘", layout="wide")


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


def _eval_root(project_id: str) -> Path:
    return project_dir_path(project_id) / "evaluations" / "opencompass"


def _history_path(project_id: str) -> Path:
    return _eval_root(project_id) / "history.json"


def _flow_state_path(project_id: str) -> Path:
    return project_dir_path(project_id) / "workflow" / "second_round_flow.json"


def _load_flow_state(project_id: str) -> Dict[str, Any]:
    payload = _load_json(_flow_state_path(project_id), {})
    return payload if isinstance(payload, dict) else {}


def _bg_state_key(project_id: str) -> str:
    return f"oc_eval_bg_{project_id}"


def _models_key(project_id: str) -> str:
    return f"oc_eval_models_{project_id}"


def _mode_key(project_id: str) -> str:
    return f"oc_eval_model_mode_{project_id}"


def _init_bg_state(project_id: str) -> Dict[str, Any]:
    key = _bg_state_key(project_id)
    if key not in st.session_state:
        st.session_state[key] = {
            "running": False,
            "thread": None,
            "logs": [],
            "result": None,
            "error": "",
        }
    return st.session_state[key]


def _list_local_model_candidates(project_id: str) -> List[str]:
    candidates: List[str] = []
    p_root = project_dir_path(project_id)
    for root in [p_root / "model_outputs", project_root / "Model"]:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if p.is_dir() and any((p / x).exists() for x in ["config.json", "tokenizer.json", "tokenizer_config.json"]):
                candidates.append(str(p))
    uniq = sorted(set(candidates), key=lambda x: (len(x), x))
    cleaned: List[str] = []
    for path in uniq:
        if not any(path.startswith(parent + "/") for parent in cleaned):
            cleaned.append(path)
    return cleaned


def _list_peft_candidates(project_id: str) -> List[str]:
    candidates: List[str] = []
    p_root = project_dir_path(project_id)
    root = p_root / "model_outputs"
    if root.exists():
        for p in root.rglob("adapter_config.json"):
            if p.is_file():
                candidates.append(str(p.parent))
    return sorted(set(candidates), key=lambda x: (len(x), x))


def _path_option_label(raw_path: str) -> str:
    text = str(raw_path or "").strip()
    if not text:
        return "-"
    p = Path(text)
    name = p.name.strip() or text
    parent = p.parent.name.strip()
    if parent and parent not in {".", "/"}:
        return f"{name} ({parent})"
    return name


def _default_models(project_id: str) -> List[Dict[str, Any]]:
    # No placeholder models by default.
    return []


def _empty_model_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "enabled",
            "is_local",
            "abbr",
            "path",
            "peft_path",
            "api_key",
            "api_base",
            "temperature",
            "max_out_len",
            "query_per_second",
            "num_procs",
            "batch_size",
            "num_gpus",
        ]
    )


def _normalize_models(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        out.append(
            {
                "enabled": bool(r.get("enabled", True)),
                "is_local": bool(r.get("is_local", False)),
                "abbr": str(r.get("abbr", "")).strip(),
                "path": str(r.get("path", "")).strip(),
                "peft_path": str(r.get("peft_path", "")).strip(),
                "api_key": str(r.get("api_key", "")).strip(),
                "api_base": str(r.get("api_base", "")).strip(),
                "temperature": float(r.get("temperature", 0.0) or 0.0),
                "max_out_len": int(r.get("max_out_len", 50) or 50),
                "query_per_second": int(r.get("query_per_second", 4) or 4),
                "num_procs": int(r.get("num_procs", 1) or 1),
                "batch_size": int(r.get("batch_size", 8) or 8),
                "num_gpus": int(r.get("num_gpus", 1) or 1),
            }
        )
    return out


def _append_model(project_id: str, model: Dict[str, Any]) -> None:
    mkey = _models_key(project_id)
    rows = _normalize_models(st.session_state.get(mkey, []))
    rows.append(model)
    st.session_state[mkey] = rows


def _remove_model_by_abbr(project_id: str, abbr: str) -> bool:
    mkey = _models_key(project_id)
    rows = _normalize_models(st.session_state.get(mkey, []))
    before = len(rows)
    rows = [x for x in rows if str(x.get("abbr", "")).strip() != str(abbr).strip()]
    st.session_state[mkey] = rows
    return len(rows) < before


def _infer_base_model_from_peft(peft_path: str) -> str:
    raw = str(peft_path or "").strip()
    if not raw:
        return ""
    p = Path(raw).expanduser()
    if not p.exists() or not p.is_dir():
        return ""
    cfg = p / "adapter_config.json"
    if not cfg.exists():
        return ""
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except Exception:
        return ""
    base = str(data.get("base_model_name_or_path", "")).strip()
    if not base:
        return ""
    base_path = Path(base).expanduser()
    if base_path.exists():
        return str(base_path)
    return base


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
  const key = "proda_oc_log_scroll_{safe_key}";
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


def _validate_enabled_models(models: List[Dict[str, Any]]) -> Optional[str]:
    for m in models:
        if not m.get("is_local"):
            continue
        path = Path(str(m.get("path", "")).strip()).expanduser()
        peft = Path(str(m.get("peft_path", "")).strip()).expanduser() if str(m.get("peft_path", "")).strip() else None
        if not path.exists():
            return f"{m.get('abbr', '')}: local path not found: {path}"
        has_config = (path / "config.json").exists()
        has_adapter = (path / "adapter_config.json").exists()
        if has_adapter and not has_config and peft is None:
            return (
                f"{m.get('abbr', '')}: selected path looks like a LoRA adapter directory. "
                "Please set base model in `path` and adapter in `peft_path`."
            )
    return None


def _consume_runner(gen, logs: List[str]) -> Dict[str, Any]:
    while True:
        try:
            line = next(gen)
            logs.append(str(line))
        except StopIteration as stop:
            return stop.value if isinstance(stop.value, dict) else {}
        except Exception as exc:
            logs.append(f"\n[RunnerError] {exc}\n")
            return {"success": False, "error": str(exc)}


def _render_viz(viz: Dict[str, Any]) -> None:
    raw = viz.get("raw")
    if isinstance(raw, dict) and raw.get("ERROR"):
        st.error(str(raw.get("ERROR")))
        return

    render_quick_insights(viz)
    st.markdown("---")
    tab1, tab2, tab3 = st.tabs(
        [
            t("opencompass_eval.tab_visualization", default="可视化"),
            t("opencompass_eval.tab_comparison", default="对比表"),
            t("opencompass_eval.tab_leaderboard", default="排行榜"),
        ]
    )
    with tab1:
        render_visualization_tab(viz)
    with tab2:
        render_comparison_tab(viz)
    with tab3:
        render_leaderboard_tab(viz)


def _append_history(project_id: str, entry: Dict[str, Any]) -> None:
    history_path = _history_path(project_id)
    history = _load_json(history_path, [])
    if not isinstance(history, list):
        history = []
    history.append(entry)
    _save_json(history_path, history)


def _load_history(project_id: str) -> List[Dict[str, Any]]:
    history = _load_json(_history_path(project_id), [])
    if not isinstance(history, list):
        return []
    rows: List[Dict[str, Any]] = []
    for item in history:
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _is_path_within(path: Path, root: Path) -> bool:
    try:
        p = path.resolve()
        r = root.resolve()
        return p == r or r in p.parents
    except Exception:
        return False


def _resolve_result_file(project_id: str, row: Dict[str, Any]) -> Path:
    run_id = str(row.get("run_id", "")).strip()
    result_path_raw = str(row.get("result_file", "")).strip()
    if result_path_raw:
        p = Path(result_path_raw).expanduser()
        if not p.is_absolute():
            p = _eval_root(project_id) / p
        if p.exists():
            return p
    return _eval_root(project_id) / "runs" / run_id / "evaluation_result.json"


def _delete_run_history(project_id: str, run_id: str) -> bool:
    rid = str(run_id).strip()
    if not rid:
        return False
    history_path = _history_path(project_id)
    history = _load_history(project_id)
    target = next((x for x in history if str(x.get("run_id", "")).strip() == rid), None)
    if target is None:
        return False

    eval_root = _eval_root(project_id)
    result_file = _resolve_result_file(project_id, target)
    payload = _load_json(result_file, {}) if result_file.exists() else {}
    benchmark_raw = str(payload.get("benchmark_json", "")).strip() if isinstance(payload, dict) else ""
    benchmark_json = Path(benchmark_raw).expanduser() if benchmark_raw else None

    run_dir = eval_root / "runs" / rid
    if run_dir.exists() and _is_path_within(run_dir, eval_root):
        shutil.rmtree(run_dir, ignore_errors=True)

    if isinstance(benchmark_json, Path) and benchmark_json.exists() and _is_path_within(benchmark_json, eval_root):
        benchmark_json.unlink(missing_ok=True)

    remained = [x for x in history if str(x.get("run_id", "")).strip() != rid]
    _save_json(history_path, remained)
    return True


def _render_history_manager(project_id: str, bg: Dict[str, Any]) -> None:
    st.markdown("---")
    st.markdown(f"### {t('opencompass_eval.history_title', default='评测历史记录')}")
    rows = sorted(_load_history(project_id), key=lambda x: str(x.get("created_at", "")), reverse=True)
    if not rows:
        st.info(t("opencompass_eval.history_empty", default="暂无历史评测记录。"))
        return

    run_ids = [str(x.get("run_id", "")).strip() for x in rows if str(x.get("run_id", "")).strip()]
    if not run_ids:
        st.info(t("opencompass_eval.history_empty", default="暂无历史评测记录。"))
        return
    row_map = {str(x.get("run_id", "")).strip(): x for x in rows}

    def _fmt_run_id(rid: str) -> str:
        row = row_map.get(rid, {})
        created = str(row.get("created_at", "")).replace("T", " ")[:19]
        status = "✅" if bool(row.get("success", False)) else "❌"
        models = ",".join([str(x) for x in (row.get("models") or []) if str(x).strip()])
        models = models[:60] + "..." if len(models) > 60 else models
        return f"{status} {rid} | {created or '-'} | {models or '-'}"

    c_pick, c_del = st.columns([4, 1])
    with c_pick:
        selected_run = st.selectbox(
            t("opencompass_eval.history_pick", default="选择评测记录"),
            options=run_ids,
            format_func=_fmt_run_id,
            key=f"oc_history_pick_{project_id}",
        )
    with c_del:
        if st.button(
            t("opencompass_eval.history_delete_btn", default="删除该记录"),
            use_container_width=True,
            key=f"oc_history_delete_{project_id}",
        ):
            ok = _delete_run_history(project_id, selected_run)
            if ok:
                if isinstance(bg.get("result"), dict) and str(bg["result"].get("run_id", "")).strip() == selected_run:
                    bg["result"] = None
                st.success(t("opencompass_eval.history_deleted", default="已删除评测记录：{run_id}", run_id=selected_run))
                st.rerun()
            st.warning(t("opencompass_eval.history_delete_missing", default="未找到该评测记录，可能已被删除。"))

    selected_row = row_map.get(selected_run, {})
    result_file = _resolve_result_file(project_id, selected_row)
    st.caption(t("opencompass_eval.history_result_file", default="结果文件：{path}", path=str(result_file)))
    if not result_file.exists():
        st.warning(t("opencompass_eval.history_result_missing", default="该记录的结果文件不存在（可能已被手动删除）。"))
        return

    payload = _load_json(result_file, {})
    if not isinstance(payload, dict):
        st.warning(t("opencompass_eval.history_result_invalid", default="结果文件格式无效，无法展示。"))
        return
    _render_viz(payload.get("viz", {}))
    st.markdown("---")
    render_opencompass_test_panel(payload, key_prefix=f"step6_hist_test_{project_id}_{selected_run}")
    with st.expander(t("opencompass_eval.raw_summary", default="原始 summary 数据"), expanded=False):
        raw_summary = (payload.get("result") or {}).get("summary_data")
        if isinstance(raw_summary, (dict, list)):
            st.json(raw_summary)
        else:
            st.code(str(raw_summary or ""), language="json")


def main() -> None:
    init_i18n()
    render_top_bar()
    render_workflow_sidebar()
    enforce_active_project()

    st.title(t("workflow.step6", default="Step 6 · OpenCompass 评测"))
    st.caption(t("opencompass_eval.desc", default="对 Benchmark 运行 OpenCompass，支持 API 模型与本地微调模型，并展示排行榜与分数据集指标。"))

    project_id = SessionStateManager.get_current_project_id()
    bg = _init_bg_state(project_id)

    nav1, nav2 = st.columns(2)
    with nav1:
        if st.button(t("opencompass_eval.back_step2", default="返回 Step2 Benchmark"), use_container_width=True):
            st.switch_page("pages/2_Benchmark_Generation.py")
    with nav2:
        if st.button(t("opencompass_eval.go_step7", default="查看 Step7 结果总览"), use_container_width=True):
            st.switch_page("pages/8_Results.py")

    st.markdown("---")
    oc_default = project_root.parent / "opencompass"
    if not (oc_default / "run.py").exists():
        oc_default = find_opencompass_dir(project_root) or (project_root / "opencompass")
    opencompass_dir = oc_default.expanduser()
    python_executable = sys.executable
    st.caption(
        t(
            "opencompass_eval.runtime_hint",
            default="运行环境：OpenCompass={oc_dir} | Python={py}",
            oc_dir=str(opencompass_dir),
            py=python_executable,
        )
    )
    if not (opencompass_dir / "run.py").exists():
        st.warning(t("opencompass_eval.runpy_missing", default="未找到 `run.py`，请确认 OpenCompass 路径。"))

    st.markdown(f"### {t('opencompass_eval.benchmark_input', default='Benchmark 输入')}")
    source = st.radio(
        t("opencompass_eval.source", default="数据来源"),
        options=[
            t("opencompass_eval.source_step2", default="当前项目 Step2 结果"),
            t("opencompass_eval.source_file", default="指定 JSON 文件"),
        ],
        horizontal=True,
    )
    benchmark_rows = SessionStateManager.get_benchmark_mcq()
    benchmark_json_path: Optional[Path] = None
    if source == t("opencompass_eval.source_step2", default="当前项目 Step2 结果"):
        st.info(t("opencompass_eval.cached_benchmark_count", default="当前项目已缓存 Benchmark 条数：{count}", count=len(benchmark_rows)))
    else:
        user_benchmark = st.text_input(t("opencompass_eval.benchmark_json_path", default="Benchmark JSON 路径"), value="")
        if user_benchmark.strip():
            benchmark_json_path = Path(user_benchmark.strip()).expanduser()

    c3, c4 = st.columns(2)
    with c3:
        dataset_abbr = st.text_input(t("opencompass_eval.dataset_abbr", default="dataset_abbr"), value="proda_bench")
    with c4:
        max_samples = int(
            st.number_input(
                t("opencompass_eval.max_samples", default="最大样本数（0=全部）"),
                min_value=0,
                max_value=1000000,
                value=0,
                step=100,
            )
        )

    st.markdown(f"### {t('opencompass_eval.models', default='模型列表')}")
    st.caption(
        t(
            "opencompass_eval.model_caption",
            default="配置说明：`is_local=False` 表示 API 模型（需填 `api_key/api_base/path`）；`is_local=True` 表示本地模型（`path` 填本地模型目录，可选 `peft_path`）。",
        )
    )
    mkey = _models_key(project_id)
    mode_key = _mode_key(project_id)
    if mkey not in st.session_state:
        st.session_state[mkey] = []
    if mode_key not in st.session_state:
        st.session_state[mode_key] = "local"
    flow_state = _load_flow_state(project_id)
    latest_model_dir = str(flow_state.get("last_trained_model_dir", "")).strip()
    latest_base_model = str(flow_state.get("last_training_base_model", "")).strip()
    if latest_model_dir:
        st.caption(
            t(
                "opencompass_eval.flow_latest_model_hint",
                default="检测到 Step5 最新训练产物：{path}",
                path=latest_model_dir,
            )
        )
        if st.button(
            t("opencompass_eval.flow_add_latest_btn", default="一键加入最新二轮模型"),
            use_container_width=True,
            key=f"oc_add_latest_round2_{project_id}",
        ):
            latest_path = Path(latest_model_dir).expanduser()
            if not latest_path.exists():
                st.warning(t("opencompass_eval.flow_latest_missing", default="最新训练产物目录不存在，请先在 Step5 完成训练。"))
            else:
                rows = _normalize_models(st.session_state.get(mkey, []))
                if any(
                    bool(x.get("is_local", False))
                    and (
                        str(x.get("peft_path", "")).strip() == str(latest_path)
                        or str(x.get("path", "")).strip() == str(latest_path)
                    )
                    for x in rows
                ):
                    st.info(t("opencompass_eval.flow_latest_exists", default="该二轮模型已在评测列表中。"))
                else:
                    has_config = (latest_path / "config.json").exists()
                    has_adapter = (latest_path / "adapter_config.json").exists()
                    abbr = f"round2_{latest_path.name}"
                    if any(str(x.get("abbr", "")).strip() == abbr for x in rows):
                        abbr = f"{abbr}_{datetime.now().strftime('%H%M%S')}"
                    if has_adapter and (not has_config) and latest_base_model:
                        model_row = {
                            "enabled": True,
                            "is_local": True,
                            "abbr": abbr,
                            "path": latest_base_model,
                            "peft_path": str(latest_path),
                            "api_key": "",
                            "api_base": "",
                            "temperature": 0.0,
                            "max_out_len": 15,
                            "query_per_second": 4,
                            "num_procs": 1,
                            "batch_size": 8,
                            "num_gpus": 1,
                        }
                    else:
                        model_row = {
                            "enabled": True,
                            "is_local": True,
                            "abbr": abbr,
                            "path": str(latest_path),
                            "peft_path": "",
                            "api_key": "",
                            "api_base": "",
                            "temperature": 0.0,
                            "max_out_len": 15,
                            "query_per_second": 4,
                            "num_procs": 1,
                            "batch_size": 8,
                            "num_gpus": 1,
                        }
                    _append_model(project_id, model_row)
                    st.success(t("opencompass_eval.flow_latest_added", default="已将最新二轮模型加入评测列表。"))
                    st.rerun()

    switch_a, switch_b = st.columns(2)
    with switch_a:
        if st.button(t("opencompass_eval.switch_local", default="配置本地微调模型"), use_container_width=True):
            st.session_state[mode_key] = "local"
    with switch_b:
        if st.button(t("opencompass_eval.switch_api", default="配置 API 模型"), use_container_width=True):
            st.session_state[mode_key] = "api"

    current_mode = st.session_state.get(mode_key, "local")
    local_candidates = _list_local_model_candidates(project_id)

    if current_mode == "local":
        st.markdown(f"#### {t('opencompass_eval.local_form', default='本地模型配置')}")
        c_l1, c_l2 = st.columns(2)
        inferred_base_key = f"oc_local_inferred_base_{project_id}"
        local_path_key = f"oc_local_path_{project_id}"
        local_peft_key = f"oc_local_peft_{project_id}"
        if inferred_base_key not in st.session_state:
            st.session_state[inferred_base_key] = ""
        peft_candidates = _list_peft_candidates(project_id)
        if local_path_key not in st.session_state:
            st.session_state[local_path_key] = ""
        if local_peft_key not in st.session_state:
            st.session_state[local_peft_key] = ""
        with c_l1:
            local_path = st.selectbox(
                t("opencompass_eval.local_path", default="本地模型路径"),
                options=[""] + local_candidates,
                index=0,
                key=local_path_key,
                format_func=_path_option_label,
            )
            local_abbr = st.text_input(
                t("opencompass_eval.local_abbr", default="模型简称（abbr）"),
                value=(f"local_{Path(local_path).name}" if local_path else "local_model"),
                key=f"oc_local_abbr_{project_id}",
            )
            local_peft = st.selectbox(
                t("opencompass_eval.local_peft", default="PEFT/LoRA 路径（可选）"),
                options=[""] + peft_candidates,
                index=0,
                key=local_peft_key,
                format_func=_path_option_label,
            )
            if st.button(
                t("opencompass_eval.autofill_local_btn", default="自动检测并填充最新本地模型/LoRA"),
                use_container_width=True,
                key=f"oc_autofill_local_{project_id}",
            ):
                if local_candidates:
                    st.session_state[local_path_key] = local_candidates[-1]
                if peft_candidates:
                    st.session_state[local_peft_key] = peft_candidates[-1]
                    inferred = _infer_base_model_from_peft(peft_candidates[-1])
                    if inferred:
                        st.session_state[inferred_base_key] = inferred
                st.rerun()
            if st.button(
                t("opencompass_eval.autofill_base_btn", default="从 LoRA 路径自动补全 Base 模型"),
                use_container_width=True,
                key=f"oc_autofill_base_{project_id}",
            ):
                inferred = _infer_base_model_from_peft(local_peft)
                if inferred:
                    st.session_state[inferred_base_key] = inferred
                    st.success(
                        t(
                            "opencompass_eval.autofill_base_ok",
                            default="已自动识别 Base 模型路径：{path}",
                            path=_path_option_label(inferred),
                        )
                    )
                else:
                    st.warning(t("opencompass_eval.autofill_base_fail", default="未能从该 LoRA 路径识别 Base 模型，请检查 adapter_config.json。"))
            inferred_base = str(st.session_state.get(inferred_base_key, "")).strip()
            if inferred_base:
                st.caption(
                    t(
                        "opencompass_eval.autofill_base_preview",
                        default="自动识别到 Base 模型：{path}",
                        path=_path_option_label(inferred_base),
                    )
                )
        with c_l2:
            local_max_out = int(st.number_input(t("opencompass_eval.local_max_out", default="max_out_len"), 1, 2048, 15, key=f"oc_local_max_out_{project_id}"))
            local_batch = int(st.number_input(t("opencompass_eval.local_batch", default="batch_size"), 1, 512, 8, key=f"oc_local_batch_{project_id}"))
            local_gpus = int(st.number_input(t("opencompass_eval.local_gpus", default="num_gpus"), 1, 64, 1, key=f"oc_local_gpus_{project_id}"))
            local_enabled = st.checkbox(t("opencompass_eval.model_enabled", default="启用该模型"), value=True, key=f"oc_local_enabled_{project_id}")
        if st.button(t("opencompass_eval.add_local", default="添加本地模型到列表"), type="primary", use_container_width=True):
            local_path_final = str(local_path).strip()
            if not local_path_final:
                local_path_final = str(st.session_state.get(inferred_base_key, "")).strip()
            if local_peft.strip() and (not local_path_final):
                inferred = _infer_base_model_from_peft(local_peft)
                if inferred:
                    local_path_final = inferred
            if not local_path_final:
                st.warning(t("opencompass_eval.local_path_missing", default="请先选择本地模型路径。"))
            else:
                _append_model(
                    project_id,
                    {
                        "enabled": bool(local_enabled),
                        "is_local": True,
                        "abbr": str(local_abbr).strip(),
                        "path": local_path_final,
                        "peft_path": str(local_peft).strip(),
                        "api_key": "",
                        "api_base": "",
                        "temperature": 0.0,
                        "max_out_len": int(local_max_out),
                        "query_per_second": 4,
                        "num_procs": 1,
                        "batch_size": int(local_batch),
                        "num_gpus": int(local_gpus),
                    },
                )
                st.success(t("opencompass_eval.model_added", default="模型已添加到下方列表。"))
                st.rerun()
    else:
        st.markdown(f"#### {t('opencompass_eval.api_form', default='API 模型配置')}")
        model_ctx = selected_model_context() or {}
        c_a1, c_a2 = st.columns(2)
        with c_a1:
            api_abbr = st.text_input(t("opencompass_eval.api_abbr", default="模型简称（abbr）"), value="api_model", key=f"oc_api_abbr_{project_id}")
            api_path = st.text_input(
                t("opencompass_eval.api_model_name", default="API 模型名（path）"),
                value=str(model_ctx.get("model", "")),
                key=f"oc_api_path_{project_id}",
            )
            api_key = st.text_input(
                t("opencompass_eval.api_key", default="API Key"),
                value=str(model_ctx.get("api_key", "")),
                type="password",
                key=f"oc_api_key_{project_id}",
            )
            api_base = st.text_input(
                t("opencompass_eval.api_base", default="API Base"),
                value=str(model_ctx.get("api_base", "")),
                key=f"oc_api_base_{project_id}",
            )
        with c_a2:
            api_temp = float(st.number_input(t("opencompass_eval.api_temp", default="temperature"), 0.0, 2.0, 0.0, step=0.1, key=f"oc_api_temp_{project_id}"))
            api_max_out = int(st.number_input(t("opencompass_eval.api_max_out", default="max_out_len"), 1, 4096, 50, key=f"oc_api_max_out_{project_id}"))
            api_qps = int(st.number_input(t("opencompass_eval.api_qps", default="query_per_second"), 1, 200, 4, key=f"oc_api_qps_{project_id}"))
            api_num_procs = int(st.number_input(t("opencompass_eval.api_num_procs", default="num_procs"), 1, 128, 2, key=f"oc_api_num_procs_{project_id}"))
            api_enabled = st.checkbox(t("opencompass_eval.model_enabled", default="启用该模型"), value=True, key=f"oc_api_enabled_{project_id}")
        if st.button(t("opencompass_eval.add_api", default="添加 API 模型到列表"), type="primary", use_container_width=True):
            if not api_path.strip():
                st.warning(t("opencompass_eval.api_model_missing", default="请填写 API 模型名。"))
            else:
                _append_model(
                    project_id,
                    {
                        "enabled": bool(api_enabled),
                        "is_local": False,
                        "abbr": str(api_abbr).strip(),
                        "path": str(api_path).strip(),
                        "peft_path": "",
                        "api_key": str(api_key).strip(),
                        "api_base": str(api_base).strip(),
                        "temperature": float(api_temp),
                        "max_out_len": int(api_max_out),
                        "query_per_second": int(api_qps),
                        "num_procs": int(api_num_procs),
                        "batch_size": 16,
                        "num_gpus": 0,
                    },
                )
                st.success(t("opencompass_eval.model_added", default="模型已添加到下方列表。"))
                st.rerun()

    st.markdown(f"#### {t('opencompass_eval.model_table', default='当前评测模型列表')}")
    model_rows = st.session_state.get(mkey, [])
    model_df = pd.DataFrame(model_rows) if model_rows else _empty_model_df()
    edited_df = st.data_editor(
        model_df,
        use_container_width=True,
        num_rows="dynamic",
        height=280,
        key=f"oc_model_editor_{project_id}",
    )

    save_models_col, reset_models_col, clear_models_col = st.columns(3)
    with save_models_col:
        if st.button(t("opencompass_eval.save_models", default="保存模型配置"), use_container_width=True):
            st.session_state[mkey] = _normalize_models(edited_df.to_dict(orient="records"))
            st.success(t("opencompass_eval.saved_models", default="模型配置已保存。"))
    with reset_models_col:
        if st.button(t("opencompass_eval.reset_models", default="重置为默认模型"), use_container_width=True):
            st.session_state[mkey] = _default_models(project_id)
            st.rerun()
    with clear_models_col:
        if st.button(t("opencompass_eval.clear_models", default="清空模型列表"), use_container_width=True):
            st.session_state[mkey] = []
            st.rerun()

    rows_after_edit = _normalize_models(st.session_state.get(mkey, []))
    abbr_options = [str(x.get("abbr", "")).strip() for x in rows_after_edit if str(x.get("abbr", "")).strip()]
    if abbr_options:
        del_col_1, del_col_2 = st.columns([3, 1])
        with del_col_1:
            delete_target = st.selectbox(
                t("opencompass_eval.delete_model_pick", default="选择要删除的模型"),
                options=abbr_options,
                key=f"oc_delete_model_pick_{project_id}",
            )
        with del_col_2:
            if st.button(t("opencompass_eval.delete_model_btn", default="删除该模型"), use_container_width=True):
                ok = _remove_model_by_abbr(project_id, delete_target)
                if ok:
                    st.success(t("opencompass_eval.model_deleted", default="已删除模型：{abbr}", abbr=delete_target))
                    st.rerun()
                st.warning(t("opencompass_eval.model_delete_missing", default="未找到对应模型，可能已被删除。"))

    run_col, stop_col = st.columns(2)
    with run_col:
        start_clicked = st.button(
            t("opencompass_eval.start_eval", default="启动 OpenCompass 评测"),
            type="primary",
            use_container_width=True,
            disabled=bool(bg.get("running")),
        )
    with stop_col:
        st.button(
            t("opencompass_eval.running_hint", default="评测运行中（暂不支持中断）"),
            use_container_width=True,
            disabled=True,
        )

    if start_clicked and not bg.get("running"):
        models = _normalize_models(st.session_state.get(mkey, []))
        enabled_models = [x for x in models if x.get("enabled") and x.get("abbr") and x.get("path")]
        if not enabled_models:
            st.warning(t("opencompass_eval.need_model", default="请至少启用一个模型，并填写 abbr/path。"))
            return
        invalid_msg = _validate_enabled_models(enabled_models)
        if invalid_msg:
            st.warning(invalid_msg)
            return

        if source == t("opencompass_eval.source_step2", default="当前项目 Step2 结果"):
            if not benchmark_rows:
                st.warning(t("opencompass_eval.need_benchmark", default="当前项目没有 Benchmark 数据，请先在 Step2 生成。"))
                return
            run_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
            input_dir = _eval_root(project_id) / "inputs"
            input_dir.mkdir(parents=True, exist_ok=True)
            benchmark_json_path = input_dir / f"benchmark_{run_tag}.json"
            _save_json(benchmark_json_path, benchmark_rows)
        else:
            if benchmark_json_path is None or not benchmark_json_path.exists():
                st.warning(t("opencompass_eval.benchmark_missing", default="指定的 Benchmark JSON 文件不存在。"))
                return

        if not (opencompass_dir / "run.py").exists():
            st.warning(t("opencompass_eval.invalid_opencompass_dir", default="OpenCompass 路径无效（缺少 run.py）。"))
            return

        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = _eval_root(project_id) / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        bg.update({"running": True, "logs": [], "result": None, "error": ""})

        def _worker() -> None:
            try:
                config_path = generate_opencompass_config(
                    benchmark_json=benchmark_json_path,
                    models=enabled_models,
                    work_dir=run_dir,
                    opencompass_dir=opencompass_dir,
                    max_samples=max_samples if max_samples > 0 else None,
                    dataset_abbr=dataset_abbr,
                )
                bg["logs"].append(f"[INFO] config generated: {config_path}\n")
                gen = run_opencompass(
                    config_path=config_path,
                    opencompass_dir=opencompass_dir,
                    work_dir=run_dir,
                    python_executable=python_executable.strip() or None,
                )
                raw_result = _consume_runner(gen, bg["logs"])
                viz = parse_results_for_viz(raw_result.get("summary_data"), enabled_models)
                final_payload = {
                    "run_id": run_id,
                    "created_at": datetime.now().isoformat(),
                    "config_path": str(config_path),
                    "benchmark_json": str(benchmark_json_path),
                    "opencompass_dir": str(opencompass_dir),
                    "models": enabled_models,
                    "result": raw_result,
                    "viz": viz,
                }
                _save_json(run_dir / "evaluation_result.json", final_payload)
                _append_history(
                    project_id,
                    {
                        "run_id": run_id,
                        "created_at": final_payload["created_at"],
                        "success": bool(raw_result.get("success")),
                        "summary_file": raw_result.get("summary_file"),
                        "result_file": str(run_dir / "evaluation_result.json"),
                        "models": [m.get("abbr", "") for m in enabled_models],
                    },
                )
                bg["result"] = final_payload
            except Exception as exc:
                bg["error"] = str(exc)
            finally:
                bg["running"] = False

        th = threading.Thread(target=_worker, daemon=True)
        bg["thread"] = th
        th.start()
        st.rerun()

    if bg.get("running"):
        st.info(t("opencompass_eval.running", default="OpenCompass 评测运行中..."))
        tail = "".join(bg.get("logs", [])[-500:])
        _render_scrollable_log_block(
            t("opencompass_eval.log", default="运行日志"),
            tail,
            height=360,
            storage_key=f"running_{project_id}",
        )
        time.sleep(2)
        st.rerun()
    else:
        if bg.get("error"):
            st.error(t("opencompass_eval.failed", default="评测失败：{err}", err=bg["error"]))
            if bg.get("logs"):
                _render_scrollable_log_block(
                    t("opencompass_eval.log_before_error", default="错误前日志"),
                    "".join(bg["logs"][-500:]),
                    height=320,
                    storage_key=f"error_{project_id}",
                )
            bg["error"] = ""
        elif bg.get("result") is not None:
            payload = bg.get("result") or {}
            result = payload.get("result", {})
            st.success(t("opencompass_eval.done", default="评测完成，returncode={code}", code=result.get("returncode")))
            _render_viz(payload.get("viz", {}))
            with st.expander(t("opencompass_eval.log", default="运行日志"), expanded=False):
                _render_scrollable_log_block(
                    t("opencompass_eval.opencompass_output", default="OpenCompass 输出"),
                    "".join(bg.get("logs", [])[-800:]),
                    height=360,
                    storage_key=f"done_{project_id}",
                )
            with st.expander(t("opencompass_eval.raw_summary", default="原始 summary 数据"), expanded=False):
                raw_summary = result.get("summary_data")
                if isinstance(raw_summary, (dict, list)):
                    st.json(raw_summary)
                else:
                    st.code(str(raw_summary or ""), language="json")
        _render_history_manager(project_id, bg)


if __name__ == "__main__":
    main()
