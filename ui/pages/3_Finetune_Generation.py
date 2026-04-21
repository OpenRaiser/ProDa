from __future__ import annotations

import json
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from proda.diagnosis import generate_diagnostic_report  # noqa: E402
from proda.diagnosis_supplement import (  # noqa: E402
    generate_diagnostic_training_data,
    merge_diagnostic_with_original,
)
from proda.finetune_generator import generate_finetune_data  # noqa: E402
from ui.components.top_bar import render_top_bar, selected_model_context  # noqa: E402
from ui.utils.i18n_helper import init_i18n, t  # noqa: E402
from ui.utils.project_store import project_dir_path  # noqa: E402
from ui.utils.session_state import SessionStateManager  # noqa: E402
from ui.utils.ui_helpers import enforce_active_project, render_workflow_sidebar  # noqa: E402


st.set_page_config(page_title="ProDA", page_icon="📘", layout="wide")


def _bg_state_key(project_id: str) -> str:
    return f"finetune_bg_{project_id}"


def _init_bg_state(project_id: str) -> dict:
    key = _bg_state_key(project_id)
    if key not in st.session_state:
        st.session_state[key] = {
            "running": False,
            "thread": None,
            "cancel_event": None,
            "progress_done": 0,
            "progress_total": 1,
            "result": None,
            "stats": None,
            "error": "",
        }
    return st.session_state[key]


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _opencompass_history_path(project_id: str) -> Path:
    return project_dir_path(project_id) / "evaluations" / "opencompass" / "history.json"


def _diagnosis_root(project_id: str) -> Path:
    return project_dir_path(project_id) / "diagnosis"


def _diagnosis_history_path(project_id: str) -> Path:
    return _diagnosis_root(project_id) / "history.json"


def _load_opencompass_history(project_id: str) -> List[Dict[str, Any]]:
    rows = _load_json(_opencompass_history_path(project_id), [])
    if not isinstance(rows, list):
        return []
    return [x for x in rows if isinstance(x, dict)]


def _load_diagnosis_history(project_id: str) -> List[Dict[str, Any]]:
    rows = _load_json(_diagnosis_history_path(project_id), [])
    if not isinstance(rows, list):
        return []
    return [x for x in rows if isinstance(x, dict)]


def _summarize_generated_types(rows: List[Dict[str, Any]]) -> Dict[str, int]:
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


def _editor_safe_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    safe_rows: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out: Dict[str, Any] = {}
        for k, v in row.items():
            if isinstance(v, (dict, list)):
                out[k] = json.dumps(v, ensure_ascii=False)
            else:
                out[k] = v
        safe_rows.append(out)
    return safe_rows


def _try_parse_json_string(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    s = value.strip()
    if not s:
        return value
    if not ((s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]"))):
        return value
    try:
        return json.loads(s)
    except Exception:
        return value


def _append_diagnosis_history(project_id: str, row: Dict[str, Any]) -> None:
    rows = _load_diagnosis_history(project_id)
    rows.append(row)
    _save_diagnosis_history(project_id, rows)


def _save_diagnosis_history(project_id: str, rows: List[Dict[str, Any]]) -> None:
    path = _diagnosis_history_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_path_within(path: Path, root: Path) -> bool:
    try:
        p = path.resolve()
        r = root.resolve()
        return p == r or r in p.parents
    except Exception:
        return False


def _delete_diagnosis_report(project_id: str, report_file: str) -> bool:
    target = str(report_file).strip()
    if not target:
        return False
    rows = _load_diagnosis_history(project_id)
    remained: List[Dict[str, Any]] = []
    deleted = False
    for item in rows:
        if not isinstance(item, dict):
            continue
        cur = str(item.get("report_file", "")).strip()
        if cur == target and not deleted:
            deleted = True
            p = Path(cur).expanduser()
            if p.exists() and _is_path_within(p, _diagnosis_root(project_id)):
                p.unlink(missing_ok=True)
            continue
        remained.append(item)
    if not deleted:
        return False
    _save_diagnosis_history(project_id, remained)
    return True


def _supplement_root(project_id: str) -> Path:
    return _diagnosis_root(project_id) / "supplements"


def _flow_state_path(project_id: str) -> Path:
    return project_dir_path(project_id) / "workflow" / "second_round_flow.json"


def _load_flow_state(project_id: str) -> Dict[str, Any]:
    payload = _load_json(_flow_state_path(project_id), {})
    return payload if isinstance(payload, dict) else {}


def _save_flow_state(project_id: str, payload: Dict[str, Any]) -> None:
    path = _flow_state_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _supplement_history_path(project_id: str) -> Path:
    return _supplement_root(project_id) / "history.json"


def _load_supplement_history(project_id: str) -> List[Dict[str, Any]]:
    rows = _load_json(_supplement_history_path(project_id), [])
    if not isinstance(rows, list):
        return []
    return [x for x in rows if isinstance(x, dict)]


def _save_supplement_history(project_id: str, rows: List[Dict[str, Any]]) -> None:
    path = _supplement_history_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_supplement_history(project_id: str, row: Dict[str, Any]) -> None:
    rows = _load_supplement_history(project_id)
    rows.append(row)
    _save_supplement_history(project_id, rows)


def _delete_supplement_dataset(project_id: str, dataset_id: str) -> bool:
    did = str(dataset_id).strip()
    if not did:
        return False
    rows = _load_supplement_history(project_id)
    remained: List[Dict[str, Any]] = []
    deleted = False
    root = _supplement_root(project_id)
    for item in rows:
        cur_id = str(item.get("dataset_id", "")).strip()
        if cur_id == did and not deleted:
            deleted = True
            p = Path(str(item.get("data_file", "")).strip()).expanduser()
            try:
                if p.exists() and _is_path_within(p, root):
                    p.unlink(missing_ok=True)
            except Exception:
                pass
            continue
        remained.append(item)
    if not deleted:
        return False
    _save_supplement_history(project_id, remained)
    return True


def _render_diagnosis_panel(project_id: str) -> None:
    st.subheader(t("fine_tuning.diagnosis_title", default="OpenCompass 诊断报告（本地模型）"))
    st.caption(
        t(
            "fine_tuning.diagnosis_desc",
            default="选择某次 OpenCompass 评测结果与本地模型，生成诊断报告（格式对齐 Loop 版本），并支持下载。",
        )
    )

    oc_history = _load_opencompass_history(project_id)
    oc_rows = [x for x in oc_history if str(x.get("result_file", "")).strip()]
    oc_rows = sorted(oc_rows, key=lambda x: str(x.get("created_at", "")), reverse=True)
    if not oc_rows:
        st.info(t("fine_tuning.diagnosis_no_opencompass", default="暂无可用的 OpenCompass 评测记录。请先完成 Step6 评测。"))
        return

    run_options = [
        {
            "run_id": str(x.get("run_id", "")),
            "label": f"{str(x.get('run_id', ''))} | {str(x.get('created_at', ''))} | success={bool(x.get('success', False))}",
            "result_file": str(x.get("result_file", "")),
        }
        for x in oc_rows
    ]
    selected_run_id = st.selectbox(
        t("fine_tuning.diagnosis_pick_run", default="选择评测结果"),
        options=[x["run_id"] for x in run_options],
        format_func=lambda rid: next((x["label"] for x in run_options if x["run_id"] == rid), rid),
        key=f"step3_diag_run_{project_id}",
    )
    selected_run = next((x for x in run_options if x["run_id"] == selected_run_id), None)
    eval_payload = _load_json(Path(str((selected_run or {}).get("result_file", ""))), {})
    eval_models = list(eval_payload.get("models", [])) if isinstance(eval_payload, dict) else []
    local_model_abbrs = [
        str(m.get("abbr", "")).strip()
        for m in eval_models
        if isinstance(m, dict) and bool(m.get("enabled", True)) and bool(m.get("is_local", False)) and str(m.get("abbr", "")).strip()
    ]
    if not local_model_abbrs:
        st.warning(t("fine_tuning.diagnosis_no_local_model", default="该评测结果中没有可诊断的本地模型（is_local=True）。"))
    else:
        selected_local_abbr = st.selectbox(
            t("fine_tuning.diagnosis_pick_model", default="选择待诊断模型"),
            options=local_model_abbrs,
            key=f"step3_diag_model_{project_id}",
        )
        diag_ctx = selected_model_context()
        if not diag_ctx:
            st.warning(
                t(
                    "fine_tuning.diagnosis_need_llm",
                    default="请先在顶部选择一个可用的 API 模型作为诊断模型（用于调用诊断 prompt）。",
                )
            )

        d1, d2, d3, d4, d5 = st.columns(5)
        with d1:
            max_diagnose = int(
                st.number_input(
                    t("fine_tuning.diagnosis_max_samples", default="诊断样本上限（0=全部）"),
                    min_value=0,
                    max_value=200000,
                    value=300,
                    step=10,
                    key=f"step3_diag_max_{project_id}",
                )
            )
        with d2:
            max_workers_diag = int(
                st.number_input(
                    t("fine_tuning.diagnosis_workers", default="并发数"),
                    min_value=1,
                    max_value=64,
                    value=8,
                    step=1,
                    key=f"step3_diag_workers_{project_id}",
                )
            )
        with d3:
            diag_temp = float(
                st.number_input(
                    t("fine_tuning.diagnosis_temp", default="温度"),
                    min_value=0.0,
                    max_value=1.5,
                    value=0.2,
                    step=0.1,
                    format="%.2f",
                    key=f"step3_diag_temp_{project_id}",
                )
            )
        with d4:
            diag_tokens = int(
                st.number_input(
                    t("fine_tuning.diagnosis_tokens", default="max_tokens"),
                    min_value=64,
                    max_value=16384,
                    value=1024,
                    step=64,
                    key=f"step3_diag_tokens_{project_id}",
                )
            )
        with d5:
            diag_retries = int(
                st.number_input(
                    t("fine_tuning.diagnosis_retries", default="重试次数"),
                    min_value=0,
                    max_value=10,
                    value=3,
                    step=1,
                    key=f"step3_diag_retries_{project_id}",
                )
            )

        if st.button(
            t("fine_tuning.diagnosis_generate", default="生成诊断报告"),
            type="primary",
            use_container_width=True,
            disabled=not bool(diag_ctx),
            key=f"step3_diag_generate_{project_id}",
        ):
            progress_ph = st.progress(0.0, text=t("fine_tuning.diagnosis_running", default="诊断中..."))

            def _on_progress(done: int, total: int) -> None:
                p = float(done) / float(max(1, total))
                progress_ph.progress(
                    min(1.0, max(0.0, p)),
                    text=t("fine_tuning.diagnosis_progress", default="诊断进度：{done}/{total}", done=done, total=total),
                )

            try:
                report = generate_diagnostic_report(
                    eval_payload=eval_payload,
                    target_model_abbr=selected_local_abbr,
                    provider=str(diag_ctx["provider"]),
                    model=str(diag_ctx["model"]),
                    api_key=str(diag_ctx["api_key"]),
                    api_base=str(diag_ctx["api_base"]),
                    max_diagnose=max_diagnose,
                    max_workers=max_workers_diag,
                    temperature=diag_temp,
                    max_tokens=diag_tokens,
                    retries=diag_retries,
                    progress_callback=_on_progress,
                )
                report_dir = _diagnosis_root(project_id) / "reports"
                report_dir.mkdir(parents=True, exist_ok=True)
                run_id_for_name = str(selected_run_id or "run")
                ts = str(report.get("timestamp", datetime.now().strftime("%Y%m%d_%H%M%S")))
                report_path = report_dir / f"diagnostic_report_{run_id_for_name}_{selected_local_abbr}_{ts}.json"
                report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                _append_diagnosis_history(
                    project_id,
                    {
                        "run_id": run_id_for_name,
                        "model_name": selected_local_abbr,
                        "created_at": datetime.now().isoformat(),
                        "report_file": str(report_path),
                        "accuracy": float(report.get("accuracy", 0.0)),
                        "error_samples_count": int(report.get("error_samples_count", 0)),
                        "diagnosis_model": f"{diag_ctx['provider']}::{diag_ctx['model']}",
                    },
                )
                st.success(t("fine_tuning.diagnosis_done", default="诊断报告已生成。"))
                st.caption(str(report_path))
            except Exception as exc:
                st.error(t("fine_tuning.diagnosis_failed", default="诊断失败：{err}", err=str(exc)))
            finally:
                progress_ph.empty()

    diag_history = _load_diagnosis_history(project_id)
    diag_history = [x for x in diag_history if str(x.get("report_file", "")).strip()]
    diag_history = sorted(diag_history, key=lambda x: str(x.get("created_at", "")), reverse=True)
    if diag_history:
        st.markdown("---")
        st.markdown(t("fine_tuning.diagnosis_history", default="诊断报告历史"))
        c_pick, c_del = st.columns([4, 1])
        with c_pick:
            diag_pick = st.selectbox(
                t("fine_tuning.diagnosis_pick_report", default="选择诊断报告"),
                options=list(range(len(diag_history))),
                format_func=lambda i: f"{diag_history[i].get('created_at', '')} | {diag_history[i].get('run_id', '')} | {diag_history[i].get('model_name', '')}",
                key=f"step3_diag_history_{project_id}",
            )
        diag_item = diag_history[int(diag_pick)]
        with c_del:
            if st.button(
                t("fine_tuning.diagnosis_delete_btn", default="删除报告"),
                use_container_width=True,
                key=f"step3_diag_delete_{project_id}",
            ):
                ok = _delete_diagnosis_report(project_id, str(diag_item.get("report_file", "")))
                if ok:
                    st.success(t("fine_tuning.diagnosis_deleted", default="诊断报告已删除。"))
                    st.rerun()
                st.warning(t("fine_tuning.diagnosis_delete_missing", default="未找到该诊断报告，可能已被删除。"))
        diag_report = _load_json(Path(str(diag_item.get("report_file", ""))), {})
        if isinstance(diag_report, dict) and diag_report:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric(t("fine_tuning.diag_metric_acc", default="准确率"), f"{float(diag_report.get('accuracy', 0.0))*100:.2f}%")
            c2.metric(t("fine_tuning.diag_metric_total", default="总题数"), int(diag_report.get("total_samples", 0)))
            c3.metric(t("fine_tuning.diag_metric_error", default="错误数"), int(diag_report.get("error_samples_count", 0)))
            c4.metric(t("fine_tuning.diag_metric_model", default="诊断对象"), str(diag_report.get("model_name", "")))
            by_issue = (diag_report.get("llm_diagnosis_issue_distribution", {}) or {})
            if by_issue:
                issue_df = pd.DataFrame([{"issue_type": k, "count": v} for k, v in by_issue.items()])
                st.markdown(t("fine_tuning.diag_issue_dist", default="问题类型分布"))
                st.dataframe(issue_df, use_container_width=True, height=180)
            by_subject = (diag_report.get("error_patterns", {}) or {}).get("by_subject", {}) or {}
            if by_subject:
                subject_df = pd.DataFrame(
                    sorted([{"subject": k, "error_count": v} for k, v in by_subject.items()], key=lambda x: x["error_count"], reverse=True)[:20]
                )
                st.markdown(t("fine_tuning.diag_subject_dist", default="学科错误分布（Top20）"))
                st.dataframe(subject_df, use_container_width=True, height=260)
            st.download_button(
                t("fine_tuning.diag_download", default="下载诊断报告 JSON"),
                data=json.dumps(diag_report, ensure_ascii=False, indent=2),
                file_name=Path(str(diag_item.get("report_file", "diagnostic_report.json"))).name,
                mime="application/json",
                use_container_width=True,
                key=f"step3_diag_download_{project_id}",
            )

            st.markdown("---")
            st.markdown(f"### {t('fine_tuning.sup_title', default='诊断补数据生成')}")
            st.caption(
                t(
                    "fine_tuning.sup_desc",
                    default="基于当前诊断报告生成迭代 SFT 数据，支持先预览/删除，确认无误后再合并。",
                )
            )

            g1, g2, g3, g4 = st.columns(4)
            with g1:
                max_error_samples = int(
                    st.number_input(
                        t("fine_tuning.sup_max_error_samples", default="诊断错误样本上限"),
                        min_value=1,
                        max_value=200000,
                        value=300,
                        step=10,
                        key=f"step3_sup_max_err_{project_id}",
                    )
                )
            with g2:
                sup_workers = int(
                    st.number_input(
                        t("fine_tuning.sup_max_workers", default="并发数"),
                        min_value=1,
                        max_value=64,
                        value=6,
                        step=1,
                        key=f"step3_sup_workers_{project_id}",
                    )
                )
            with g3:
                sup_retries = int(
                    st.number_input(
                        t("fine_tuning.sup_retries", default="重试次数"),
                        min_value=0,
                        max_value=10,
                        value=2,
                        step=1,
                        key=f"step3_sup_retries_{project_id}",
                    )
                )
            with g4:
                sup_tokens = int(
                    st.number_input(
                        t("fine_tuning.sup_max_tokens", default="max_tokens"),
                        min_value=256,
                        max_value=8192,
                        value=2048,
                        step=128,
                        key=f"step3_sup_tokens_{project_id}",
                    )
                )

            st.markdown(f"#### {t('fine_tuning.sup_window_title', default='按错误类型窗口配置（每条错误样本）')}")
            cgap_count = int((diag_report.get("llm_diagnosis_issue_distribution", {}) or {}).get("concept_gap", 0))
            cdef_count = int((diag_report.get("llm_diagnosis_issue_distribution", {}) or {}).get("capability_deficit", 0))

            w_h1, w_h2, w_h3 = st.columns(3)
            with w_h1:
                st.markdown(f"**{t('fine_tuning.sup_label_qa', default='QA')}**")
            with w_h2:
                st.markdown(f"**{t('fine_tuning.sup_label_choice', default='Choice')}**")
            with w_h3:
                st.markdown(f"**{t('fine_tuning.sup_label_tf', default='TF')}**")

            st.caption(t("fine_tuning.sup_issue_concept_gap", default="concept_gap"))
            c1, c2, c3 = st.columns(3)
            with c1:
                cg_qa = int(
                    st.number_input(
                        f"{t('fine_tuning.sup_issue_concept_gap', default='concept_gap')} · {t('fine_tuning.sup_label_qa', default='QA')}",
                        0,
                        20,
                        4,
                        1,
                        key=f"step3_sup_cg_qa_{project_id}",
                    )
                )
            with c2:
                cg_choice = int(
                    st.number_input(
                        f"{t('fine_tuning.sup_issue_concept_gap', default='concept_gap')} · {t('fine_tuning.sup_label_choice', default='Choice')}",
                        0,
                        20,
                        2,
                        1,
                        key=f"step3_sup_cg_choice_{project_id}",
                    )
                )
            with c3:
                cg_tf = int(
                    st.number_input(
                        f"{t('fine_tuning.sup_issue_concept_gap', default='concept_gap')} · {t('fine_tuning.sup_label_tf', default='TF')}",
                        0,
                        20,
                        1,
                        1,
                        key=f"step3_sup_cg_tf_{project_id}",
                    )
                )

            st.caption(t("fine_tuning.sup_issue_capability_deficit", default="capability_deficit"))
            d1, d2, d3 = st.columns(3)
            with d1:
                cd_qa = int(
                    st.number_input(
                        f"{t('fine_tuning.sup_issue_capability_deficit', default='capability_deficit')} · {t('fine_tuning.sup_label_qa', default='QA')}",
                        0,
                        20,
                        3,
                        1,
                        key=f"step3_sup_cd_qa_{project_id}",
                    )
                )
            with d2:
                cd_choice = int(
                    st.number_input(
                        f"{t('fine_tuning.sup_issue_capability_deficit', default='capability_deficit')} · {t('fine_tuning.sup_label_choice', default='Choice')}",
                        0,
                        20,
                        3,
                        1,
                        key=f"step3_sup_cd_choice_{project_id}",
                    )
                )
            with d3:
                cd_tf = int(
                    st.number_input(
                        f"{t('fine_tuning.sup_issue_capability_deficit', default='capability_deficit')} · {t('fine_tuning.sup_label_tf', default='TF')}",
                        0,
                        20,
                        1,
                        1,
                        key=f"step3_sup_cd_tf_{project_id}",
                    )
                )

            issue_windows = {
                "concept_gap": {"qa": cg_qa, "choice": cg_choice, "tf": cg_tf},
                "capability_deficit": {"qa": cd_qa, "choice": cd_choice, "tf": cd_tf},
            }
            estimated = cgap_count * (cg_qa + cg_choice + cg_tf) + cdef_count * (cd_qa + cd_choice + cd_tf)
            st.info(
                t(
                    "fine_tuning.sup_estimated_rows",
                    default="预估生成条数（校验前）：{count}",
                    count=estimated,
                )
            )

            gen_ctx = selected_model_context()
            if not gen_ctx:
                st.warning(
                    t(
                        "fine_tuning.sup_need_llm",
                        default="请先在顶部选择可用的 API 模型用于补数据生成。",
                    )
                )
            if st.button(
                t("fine_tuning.sup_generate_btn", default="生成诊断补数据"),
                type="primary",
                use_container_width=True,
                disabled=not bool(gen_ctx),
                key=f"step3_sup_generate_{project_id}",
            ):
                progress_ph = st.progress(0.0, text=t("fine_tuning.sup_generating", default="正在生成诊断补数据..."))

                def _on_sup_progress(done: int, total: int) -> None:
                    p = float(done) / float(max(1, total))
                    progress_ph.progress(
                        min(1.0, max(0.0, p)),
                        text=t("fine_tuning.sup_generating_progress", default="生成任务进度：{done}/{total}", done=done, total=total),
                    )

                try:
                    generated_rows, sup_stats = generate_diagnostic_training_data(
                        diagnostic_report=diag_report,
                        provider=str(gen_ctx["provider"]),
                        model=str(gen_ctx["model"]),
                        api_key=str(gen_ctx["api_key"]),
                        api_base=str(gen_ctx["api_base"]),
                        issue_windows=issue_windows,
                        max_error_samples=max_error_samples,
                        max_workers=sup_workers,
                        max_tokens=sup_tokens,
                        retries=sup_retries,
                        progress_callback=_on_sup_progress,
                    )
                    type_counts = _summarize_generated_types(generated_rows)
                    sup_stats = dict(sup_stats or {})
                    sup_stats["type_counts"] = type_counts
                    ds_id = datetime.now().strftime("%Y%m%d_%H%M%S")
                    ds_root = _supplement_root(project_id)
                    ds_root.mkdir(parents=True, exist_ok=True)
                    ds_file = ds_root / f"diagnostic_sft_{ds_id}.json"
                    ds_file.write_text(json.dumps(generated_rows, ensure_ascii=False, indent=2), encoding="utf-8")
                    _append_supplement_history(
                        project_id,
                        {
                            "dataset_id": ds_id,
                            "created_at": datetime.now().isoformat(),
                            "report_file": str(diag_item.get("report_file", "")),
                            "report_created_at": str(diag_item.get("created_at", "")),
                            "data_file": str(ds_file),
                            "row_count": int(len(generated_rows)),
                            "issue_windows": issue_windows,
                            "stats": sup_stats,
                        },
                    )
                    st.success(
                        t(
                            "fine_tuning.sup_generated_done",
                            default="诊断补数据生成完成：{count} 条。",
                            count=len(generated_rows),
                        )
                    )
                    m_qa, m_choice, m_tf = st.columns(3)
                    with m_qa:
                        st.metric(t("fine_tuning.sup_label_qa", default="问答"), int(type_counts.get("qa", 0)))
                    with m_choice:
                        st.metric(t("fine_tuning.sup_label_choice", default="选择"), int(type_counts.get("choice", 0)))
                    with m_tf:
                        st.metric(t("fine_tuning.sup_label_tf", default="判断"), int(type_counts.get("tf", 0)))
                    st.caption(
                        t(
                            "fine_tuning.sup_generated_stats",
                            default="任务总数 {tasks}，失败任务 {failed}，实际生成 {rows}。",
                            tasks=int((sup_stats or {}).get("tasks_total", 0)),
                            failed=int((sup_stats or {}).get("tasks_failed", 0)),
                            rows=int((sup_stats or {}).get("generated_rows", 0)),
                        )
                    )
                    st.caption(str(ds_file))
                except Exception as exc:
                    st.error(t("fine_tuning.sup_generate_failed", default="生成失败：{err}", err=str(exc)))
                finally:
                    progress_ph.empty()

            sup_history = sorted(_load_supplement_history(project_id), key=lambda x: str(x.get("created_at", "")), reverse=True)
            if sup_history:
                st.markdown("---")
                st.markdown(f"### {t('fine_tuning.sup_history_title', default='已生成的诊断补数据集')}")
                s1, s2 = st.columns([4, 1])
                with s1:
                    sup_pick = st.selectbox(
                        t("fine_tuning.sup_pick_dataset", default="选择补数据集"),
                        options=list(range(len(sup_history))),
                        format_func=lambda i: f"{sup_history[i].get('created_at', '')} | rows={sup_history[i].get('row_count', 0)} | id={sup_history[i].get('dataset_id', '')}",
                        key=f"step3_sup_pick_{project_id}",
                    )
                sup_item = sup_history[int(sup_pick)]
                with s2:
                    if st.button(t("fine_tuning.sup_delete_btn", default="删除数据集"), use_container_width=True, key=f"step3_sup_delete_{project_id}"):
                        ok = _delete_supplement_dataset(project_id, str(sup_item.get("dataset_id", "")))
                        if ok:
                            st.success(t("fine_tuning.sup_deleted", default="数据集已删除。"))
                            st.rerun()
                        st.warning(t("fine_tuning.sup_delete_missing", default="未找到该数据集，可能已被删除。"))

                sup_rows = _load_json(Path(str(sup_item.get("data_file", ""))), [])
                if isinstance(sup_rows, list):
                    s_rows = [x for x in sup_rows if isinstance(x, dict)]
                else:
                    s_rows = []
                qtype_dist: Dict[str, int] = {}
                for row in s_rows:
                    qt = str(row.get("question_type", "unknown"))
                    qtype_dist[qt] = qtype_dist.get(qt, 0) + 1
                st.caption(
                    t("fine_tuning.sup_type_dist_prefix", default="题型分布：")
                    + " "
                    + ", ".join([f"{k}={v}" for k, v in sorted(qtype_dist.items())])
                    if qtype_dist
                    else t("fine_tuning.sup_type_dist_empty", default="题型分布：空")
                )
                preview = pd.DataFrame(
                    [
                        {
                            "issue_type": str(r.get("issue_type", "")),
                            "question_type": str(r.get("question_type", "")),
                            "question": str(r.get("question", "")),
                            "options": json.dumps(r.get("options", {}), ensure_ascii=False) if isinstance(r.get("options", {}), dict) else "",
                            "answer": str(r.get("answer", "")),
                            "explanation": str(r.get("explanation", "")),
                        }
                        for r in s_rows[:200]
                    ]
                )
                st.dataframe(preview, use_container_width=True, height=260)
                st.download_button(
                    t("fine_tuning.sup_download_dataset", default="下载补数据集"),
                    data=json.dumps(s_rows, ensure_ascii=False, indent=2),
                    file_name=Path(str(sup_item.get("data_file", "diagnostic_sft.json"))).name,
                    mime="application/json",
                    use_container_width=True,
                    key=f"step3_sup_download_{project_id}",
                )

                st.markdown(f"### {t('fine_tuning.sup_merge_title', default='合并到 FineTune 数据')}")
                m1, m2, m3 = st.columns(3)
                with m1:
                    mix_with_original = st.checkbox(
                        t("fine_tuning.sup_merge_mix_original", default="与原始数据混合"),
                        value=True,
                        key=f"step3_sup_mix_{project_id}",
                    )
                with m2:
                    target_total = int(
                        st.number_input(
                            t("fine_tuning.sup_merge_target_total", default="合并后目标总量"),
                            min_value=1,
                            max_value=500000,
                            value=max(1000, len(s_rows)),
                            step=100,
                            key=f"step3_sup_target_total_{project_id}",
                        )
                    )
                with m3:
                    diag_ratio = float(
                        st.slider(
                            t("fine_tuning.sup_merge_diag_ratio", default="诊断数据比例"),
                            0.0,
                            1.0,
                            0.35,
                            0.01,
                            key=f"step3_sup_ratio_{project_id}",
                        )
                    )
                m4, m5 = st.columns(2)
                with m4:
                    exclude_same_l2 = st.checkbox(
                        t("fine_tuning.sup_merge_exclude_l2", default="排除与补数据 L2 ID 重叠的原始样本"),
                        value=True,
                        key=f"step3_sup_exclude_l2_{project_id}",
                    )
                with m5:
                    fallback_random = st.checkbox(
                        t("fine_tuning.sup_merge_fallback", default="不足时随机回填"),
                        value=True,
                        key=f"step3_sup_fallback_{project_id}",
                    )
                random_seed = int(
                    st.number_input(
                        t("fine_tuning.sup_merge_seed", default="随机种子"),
                        min_value=0,
                        max_value=9999999,
                        value=42,
                        step=1,
                        key=f"step3_sup_seed_{project_id}",
                    )
                )

                if st.button(
                    t("fine_tuning.sup_merge_btn", default="确认合并到 FineTune"),
                    type="primary",
                    use_container_width=True,
                    key=f"step3_sup_merge_{project_id}",
                ):
                    original_rows = list(SessionStateManager.get_finetune_data() or [])
                    merged_rows, merge_stats = merge_diagnostic_with_original(
                        diagnostic_rows=s_rows,
                        original_rows=original_rows,
                        target_total=target_total,
                        diagnostic_ratio=diag_ratio,
                        mix_with_original=mix_with_original,
                        exclude_same_l2=exclude_same_l2,
                        fallback_random_if_insufficient=fallback_random,
                        random_seed=random_seed,
                    )
                    SessionStateManager.set_finetune_data(merged_rows)
                    merged_file = _supplement_root(project_id) / f"merged_finetune_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                    merged_file.write_text(json.dumps(merged_rows, ensure_ascii=False, indent=2), encoding="utf-8")
                    flow_state = _load_flow_state(project_id)
                    flow_state.update(
                        {
                            "merged_ready": True,
                            "merged_at": datetime.now().isoformat(),
                            "merged_rows": int(len(merged_rows)),
                            "merged_file": str(merged_file),
                            "source_dataset_id": str(sup_item.get("dataset_id", "")),
                            "source_report_file": str(sup_item.get("report_file", "")),
                        }
                    )
                    _save_flow_state(project_id, flow_state)
                    st.success(
                        t(
                            "fine_tuning.sup_merge_done",
                            default="合并完成：诊断数据 {diag} 条，原始数据 {orig} 条，最终 {total} 条。",
                            diag=merge_stats.get("diagnostic_selected", 0),
                            orig=merge_stats.get("original_selected", 0),
                            total=len(merged_rows),
                        )
                    )
                    st.caption(
                        t(
                            "fine_tuning.sup_merge_file_saved",
                            default="合并结果已保存：{path}",
                            path=str(merged_file),
                        )
                    )


def main() -> None:
    init_i18n()
    render_top_bar()
    render_workflow_sidebar()
    enforce_active_project()

    st.title(t("finetune.title", default="FineTune Data Generation"))
    st.caption(t("finetune.desc", default="Generate finetuning samples from extracted L1/L2 knowledge core."))
    project_id = SessionStateManager.get_current_project_id()
    page_mode = st.radio(
        t("fine_tuning.page_mode", default="子页面"),
        options=["generate", "diagnosis"],
        format_func=lambda x: t("fine_tuning.page_mode_train", default="原始数据生成与训练")
        if x == "generate"
        else t("fine_tuning.page_mode_diagnosis", default="诊断报告生成"),
        horizontal=True,
        key=f"step3_page_mode_{project_id}",
    )
    if page_mode == "diagnosis":
        _render_diagnosis_panel(project_id)
        return

    model_ctx = selected_model_context()
    knowledge_core = SessionStateManager.get_knowledge_core() or {}
    l2 = knowledge_core.get("l2_statements", [])
    if not l2:
        st.warning(t("finetune.need_knowledge_core", default="Please extract knowledge core in Step1 first."))
        if st.button(t("finetune.back_step1", default="Go to Step1"), type="primary"):
            st.switch_page("pages/1_Data_Processing.py")
        return
    if not model_ctx:
        st.warning(t("finetune.need_model", default="Please configure and select a model first."))
        return
    bg = _init_bg_state(project_id)
    top_nav = st.columns(2)
    with top_nav[0]:
        if st.button(t("finetune.go_benchmark", default="返回 Benchmark 数据生成"), use_container_width=True):
            st.switch_page("pages/2_Benchmark_Generation.py")
    with top_nav[1]:
        if st.button(t("finetune.go_step1", default="返回 Step1"), use_container_width=True):
            st.switch_page("pages/1_Data_Processing.py")

    c1, c2, c3 = st.columns(3)
    with c1:
        total_samples = int(
            st.number_input(t("finetune.total_samples", default="Total samples"), 30, 20000, 300, step=10)
        )
    with c2:
        qa_ratio = float(st.slider(t("finetune.qa_ratio", default="QA ratio"), 0.1, 0.9, 0.6, 0.05))
    with c3:
        choice_ratio = float(
            st.slider(t("finetune.choice_ratio", default="Choice ratio"), 0.05, 0.8, 0.3, 0.05)
        )
    c4, c5, c6 = st.columns(3)
    with c4:
        true_ratio = float(st.slider(t("finetune.true_ratio", default="True ratio (TF)"), 0.1, 0.9, 0.6, 0.05))
    with c5:
        single_choice_ratio = float(
            st.slider(t("finetune.single_choice_ratio", default="Single-choice ratio"), 0.1, 0.95, 0.7, 0.05)
        )
    with c6:
        max_workers = int(st.slider(t("finetune.max_workers", default="Parallel workers"), 1, 32, 6))
    c7, c8, c9 = st.columns(3)
    with c7:
        retries = int(st.slider(t("finetune.retries", default="Retries"), 0, 5, 2))
    with c8:
        batch_size = int(st.slider(t("finetune.batch_size", default="Batch size per call"), 1, 20, 8))
    with c9:
        l2_window_size = int(st.slider(t("finetune.l2_window_size", default="L2 window size"), 1, 30, 8))
    c10, c11 = st.columns(2)
    with c10:
        l1_topn = int(st.slider(t("finetune.l1_topn", default="L1 top-N"), 1, 80, 20))
    with c11:
        allow_l2_reuse = st.checkbox(
            t("finetune.allow_l2_reuse", default="Allow L2 reuse after exhaustion"),
            value=True,
        )
    author_notes = st.text_area(t("finetune.author_notes", default="Author notes (optional)"), "")

    op1, op2 = st.columns(2)
    with op1:
        start_clicked = st.button(
            t("finetune.generate", default="Generate FineTune Data"),
            type="primary",
            use_container_width=True,
            disabled=bool(bg.get("running")),
        )
    with op2:
        cancel_clicked = st.button(
            t("finetune.stop_generation", default="中断生成"),
            use_container_width=True,
            disabled=not bool(bg.get("running")),
        )

    if start_clicked and not bg.get("running"):
        cancel_event = threading.Event()
        bg.update(
            {
                "running": True,
                "thread": None,
                "cancel_event": cancel_event,
                "progress_done": 0,
                "progress_total": 1,
                "result": None,
                "stats": None,
                "error": "",
            }
        )

        def _worker():
            try:
                def on_progress(done: int, total: int) -> None:
                    bg["progress_done"] = int(done)
                    bg["progress_total"] = int(max(1, total))

                rows = generate_finetune_data(
                    knowledge_core=knowledge_core,
                    provider=model_ctx["provider"],
                    model=model_ctx["model"],
                    api_key=model_ctx["api_key"],
                    api_base=model_ctx["api_base"],
                    total_samples=total_samples,
                    qa_ratio=qa_ratio,
                    choice_ratio=choice_ratio,
                    single_choice_ratio=single_choice_ratio,
                    true_ratio=true_ratio,
                    author_notes=author_notes,
                    max_workers=max_workers,
                    retries=retries,
                    batch_size=batch_size,
                    l2_window_size=l2_window_size,
                    l1_topn=l1_topn,
                    allow_l2_reuse_after_exhausted=allow_l2_reuse,
                    progress_callback=on_progress,
                    cancel_event=cancel_event,
                )
                bg["result"] = rows
                bg["stats"] = getattr(generate_finetune_data, "last_run_stats", {})
            except Exception as exc:
                bg["error"] = str(exc)
            finally:
                bg["running"] = False

        th = threading.Thread(target=_worker, daemon=True)
        bg["thread"] = th
        th.start()
        st.rerun()

    if cancel_clicked and bg.get("running") and bg.get("cancel_event") is not None:
        bg["cancel_event"].set()
        st.warning(t("finetune.cancelling", default="正在请求中断，请稍候..."))

    if bg.get("running"):
        done = int(bg.get("progress_done", 0))
        total = int(max(1, bg.get("progress_total", 1)))
        st.progress(
            int(done * 100 / total),
            text=t("finetune.progress", default="Progress: {done}/{total}").format(done=done, total=total),
        )
        time.sleep(1)
        st.rerun()
    else:
        if bg.get("error"):
            st.error(t("finetune.gen_failed", default="生成失败：{err}", err=bg["error"]))
            bg["error"] = ""
        elif bg.get("result") is not None:
            rows = list(bg.get("result") or [])
            stats = bg.get("stats") or {}
            SessionStateManager.set_finetune_data(rows)
            bg["result"] = None
            bg["stats"] = None
            if stats.get("cancelled"):
                st.warning(
                    t("finetune.cancelled_count", default="已中断，本次保留 {n} 条结果。").format(n=len(rows))
                )
            else:
                st.success(t("finetune.generated_count", default="Generated {n} records.").format(n=len(rows)))
            if stats:
                st.info(
                    t(
                        "finetune.run_stats",
                        default="任务统计：提交 {submitted}，成功任务 {succeeded}，失败任务 {failed}，补生成轮次 {rounds}",
                        submitted=stats.get("submitted", 0),
                        succeeded=stats.get("succeeded_jobs", 0),
                        failed=stats.get("failed_jobs", 0),
                        rounds=stats.get("refill_rounds", 0),
                    )
                )
                st.caption(
                    t(
                        "finetune.adaptive_stats",
                        default="自适应并发：初始 {initial}，最低 {minw}，最高 {maxw}，最终 {final}，调节次数 {adjusts}",
                        initial=stats.get("initial_workers", 0),
                        minw=stats.get("min_workers", 0),
                        maxw=stats.get("max_workers_seen", 0),
                        final=stats.get("final_workers", 0),
                        adjusts=stats.get("worker_adjustments", 0),
                    )
                )
                st.caption(
                    t(
                        "finetune.window_stats",
                        default="窗口策略：batch {batch}，L2窗口 {window}，L1 topN {topn}，空窗口 {empty}",
                        batch=stats.get("batch_size", 0),
                        window=stats.get("l2_window_size", 0),
                        topn=stats.get("l1_topn", 0),
                        empty=stats.get("empty_windows", 0),
                    )
                )

    rows = SessionStateManager.get_finetune_data()
    if not rows:
        st.info(t("finetune.empty", default="No finetune data yet."))
        return
    flow_state = _load_flow_state(project_id)
    if bool(flow_state.get("merged_ready", False)):
        st.caption(
            t(
                "fine_tuning.sup_flow_ready_hint",
                default="已完成诊断补数据合并（{rows} 条）。可直接进入 Step5 开始二轮微调。",
                rows=int(flow_state.get("merged_rows", 0) or 0),
            )
        )
        if st.button(
            t("fine_tuning.sup_go_step5_btn", default="前往 Step5 二轮微调"),
            use_container_width=True,
            key=f"step3_flow_go_step5_{project_id}",
        ):
            st.switch_page("pages/5_Fine_Tuning.py")

    st.markdown("---")
    st.subheader(t("finetune.review", default="Review and Edit"))
    qtype_options = ["all", "qa", "single_choice", "multiple_choice", "true_false"]
    qtype = st.selectbox(
        t("finetune.filter_type", default="Filter by question type"),
        qtype_options,
        format_func=lambda x: "All" if x == "all" else x,
    )
    keyword = st.text_input(t("finetune.filter_keyword", default="Keyword filter"), "")

    rows_with_id = [{"__row_id__": idx, **row} for idx, row in enumerate(rows)]
    filtered = rows_with_id
    if qtype != "all":
        filtered = [x for x in filtered if str(x.get("question_type", "")).lower() == qtype]
    if keyword.strip():
        kw = keyword.strip().lower()

        def hit(item: dict) -> bool:
            return kw in json.dumps(item, ensure_ascii=False).lower()

        filtered = [x for x in filtered if hit(x)]

    safe_filtered = _editor_safe_rows(filtered)
    edited_df = st.data_editor(
        pd.DataFrame(safe_filtered),
        use_container_width=True,
        num_rows="dynamic",
        height=520,
        key="finetune_editor",
    )
    col_save, col_download, col_next = st.columns(3)
    with col_save:
        if st.button(t("finetune.save_edits", default="Save edits"), use_container_width=True):
            if qtype != "all" or keyword.strip():
                st.warning(
                    t(
                        "finetune.save_filtered_warn",
                        default="Please clear filters before saving to avoid overwriting non-visible rows.",
                    )
                )
            else:
                records = edited_df.to_dict(orient="records")
                cleaned = []
                for r in records:
                    r.pop("__row_id__", None)
                    for key, val in list(r.items()):
                        r[key] = _try_parse_json_string(val)
                    cleaned.append(r)
                SessionStateManager.set_finetune_data(cleaned)
                st.success(t("finetune.saved", default="Edits saved."))
    with col_download:
        st.download_button(
            t("finetune.download", default="Download FineTune JSON"),
            data=json.dumps(SessionStateManager.get_finetune_data(), ensure_ascii=False, indent=2),
            file_name="finetune_data.json",
            mime="application/json",
            use_container_width=True,
        )
    with col_next:
        if st.button(t("finetune.go_step5", default="Go to Fine-Tuning"), use_container_width=True):
            st.switch_page("pages/5_Fine_Tuning.py")


if __name__ == "__main__":
    main()
