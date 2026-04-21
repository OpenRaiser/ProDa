from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ui.components.opencompass_visualizer import (  # noqa: E402
    render_comparison_tab,
    render_leaderboard_tab,
    render_quick_insights,
    render_visualization_tab,
)
from ui.components.opencompass_test_panel import render_opencompass_test_panel  # noqa: E402
from ui.components.top_bar import render_top_bar  # noqa: E402
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


def _history_path(project_id: str) -> Path:
    return project_dir_path(project_id) / "evaluations" / "opencompass" / "history.json"


def _render_history_overview(df_h: pd.DataFrame) -> None:
    st.markdown(f"### {t('results_center.opencompass_history', default='OpenCompass 历史概览')}")
    c1, c2, c3 = st.columns(3)
    total_runs = int(len(df_h))
    success_runs = 0
    if "success" in df_h.columns:
        success_runs = int(df_h["success"].fillna(False).astype(bool).sum())
    fail_runs = max(0, total_runs - success_runs)
    success_rate = (success_runs / total_runs * 100.0) if total_runs > 0 else 0.0

    c1.metric(t("results_center.total_runs", default="总运行次数"), total_runs)
    c2.metric(t("results_center.success_runs", default="成功次数"), success_runs)
    c3.metric(t("results_center.success_rate", default="成功率"), f"{success_rate:.1f}%")

    if total_runs > 0:
        st.bar_chart(pd.DataFrame({"count": [success_runs, fail_runs]}, index=["success", "failed"]), use_container_width=True)


def _render_run_details(rows: List[Dict[str, Any]]) -> None:
    run_ids = [str(x.get("run_id", "")) for x in rows]
    selected_run = st.selectbox(t("results_center.pick_run", default="查看某次评测详情"), options=run_ids)
    picked = next((x for x in rows if str(x.get("run_id", "")) == selected_run), None)
    if not picked:
        return

    result_file = Path(str(picked.get("result_file", "")))
    st.caption(t("results_center.result_file", default="结果文件：{path}", path=str(result_file)))
    if not result_file.exists():
        st.warning(t("results_center.result_file_missing", default="该次评测结果文件不存在（可能已被移动或删除）。"))
        return

    payload = _load_json(result_file, {})
    viz = payload.get("viz", {})

    render_quick_insights(viz)
    tab1, tab2, tab3 = st.tabs(
        [
            t("results_center.tab_visualization", default="可视化"),
            t("results_center.tab_comparison", default="对比表"),
            t("results_center.tab_leaderboard", default="排行榜"),
        ]
    )
    with tab1:
        render_visualization_tab(viz)
    with tab2:
        render_comparison_tab(viz)
    with tab3:
        render_leaderboard_tab(viz)

    st.markdown("---")
    render_opencompass_test_panel(payload, key_prefix=f"step7_test_{selected_run}")

    with st.expander(t("results_center.raw_json", default="原始结果 JSON"), expanded=False):
        st.json(payload)
    st.download_button(
        t("results_center.download_run_json", default="下载本次评测 JSON"),
        data=json.dumps(payload, ensure_ascii=False, indent=2),
        file_name=f"opencompass_eval_{selected_run}.json",
        mime="application/json",
        use_container_width=True,
    )


def main() -> None:
    init_i18n()
    render_top_bar()
    render_workflow_sidebar()
    enforce_active_project()

    st.title(t("workflow.step7", default="Step 7 · 结果导出"))
    st.caption(t("results_center.desc", default="统一查看产物统计与 OpenCompass 历史，不重复承载评测配置。"))

    nav1, nav2, nav3 = st.columns(3)
    with nav1:
        if st.button(t("results_center.go_step2", default="前往 Step2 Benchmark"), use_container_width=True):
            st.switch_page("pages/2_Benchmark_Generation.py")
    with nav2:
        if st.button(t("results_center.go_step3", default="前往 Step3 FineTune 数据"), use_container_width=True):
            st.switch_page("pages/3_Finetune_Generation.py")
    with nav3:
        if st.button(t("results_center.go_step6", default="前往 Step6 OpenCompass 评测"), type="primary", use_container_width=True):
            st.switch_page("pages/7_OpenCompass_Evaluation.py")

    st.markdown("---")
    benchmark_rows = SessionStateManager.get_benchmark_mcq()
    finetune_rows = SessionStateManager.get_finetune_data()

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric(t("results_center.metric_benchmark", default="Benchmark 条数"), len(benchmark_rows))
    with c2:
        st.metric(t("results_center.metric_finetune", default="FineTune 条数"), len(finetune_rows))
    with c3:
        oc_history = _load_json(_history_path(SessionStateManager.get_current_project_id()), [])
        st.metric(t("results_center.metric_opencompass", default="OpenCompass 评测次数"), len(oc_history) if isinstance(oc_history, list) else 0)

    project_id = SessionStateManager.get_current_project_id()
    history: List[Dict[str, Any]] = _load_json(_history_path(project_id), [])
    if not history:
        st.info(t("results_center.no_opencompass", default="暂无 OpenCompass 评测记录。"))
        return

    rows = sorted(history, key=lambda x: str(x.get("created_at", "")), reverse=True)
    df_h = pd.DataFrame(rows)
    _render_history_overview(df_h)
    st.dataframe(df_h, use_container_width=True, height=240)
    st.markdown("---")
    _render_run_details(rows)


if __name__ == "__main__":
    main()
