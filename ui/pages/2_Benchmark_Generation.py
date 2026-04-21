from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import pandas as pd
import streamlit as st

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from proda.benchmark_generator import generate_benchmark_mcq  # noqa: E402
from ui.components.top_bar import render_top_bar  # noqa: E402
from ui.components.top_bar import selected_model_context  # noqa: E402
from ui.utils.i18n_helper import init_i18n, t  # noqa: E402
from ui.utils.session_state import SessionStateManager  # noqa: E402
from ui.utils.ui_helpers import enforce_active_project, render_workflow_sidebar  # noqa: E402


st.set_page_config(page_title="ProDA", page_icon="📘", layout="wide")


def _bg_state_key(project_id: str) -> str:
    return f"benchmark_bg_{project_id}"


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


def main() -> None:
    init_i18n()
    render_top_bar()
    render_workflow_sidebar()
    enforce_active_project()

    st.title(t("benchmark.title", default="Benchmark 数据生成"))
    st.caption(t("benchmark.desc", default="基于 L3 reasoning chains 生成高质量 MCQ。"))

    model_ctx = selected_model_context()
    knowledge_core = SessionStateManager.get_knowledge_core()
    l3_chains = (knowledge_core or {}).get("l3_chains", [])

    if not knowledge_core or not l3_chains:
        st.warning(t("benchmark.need_knowledge_core", default="请先在 Step1 提取知识核心。"))
        if st.button(t("benchmark.back_step1", default="返回 Step1"), type="primary"):
            st.switch_page("pages/1_Data_Processing.py")
        return

    if not model_ctx:
        st.warning(t("benchmark.need_model", default="请先在右上角配置并选择模型。"))
        return

    st.info(t("benchmark.loaded_chains", default="已加载 {count} 条 L3 chains。", count=len(l3_chains)))
    project_id = SessionStateManager.get_current_project_id()
    bg = _init_bg_state(project_id)

    c1, c2, c3 = st.columns(3)
    with c1:
        max_workers = st.slider(t("benchmark.max_workers", default="并发数"), 1, 16, 4)
    with c2:
        temperature = st.slider(t("benchmark.temperature", default="温度"), 0.0, 1.5, 0.3, 0.1)
    with c3:
        retries = st.slider(t("benchmark.retries", default="重试次数"), 0, 5, 2)
    questions_per_chain = st.slider(t("benchmark.questions_per_chain", default="每条链目标题数"), 1, 10, 5)
    st.caption(
        t(
            "benchmark.expected_total",
            default="目标总数：{chains} 条链 × {qpc} = {total}",
            chains=len(l3_chains),
            qpc=questions_per_chain,
            total=len(l3_chains) * questions_per_chain,
        )
    )
    nav_cols = st.columns(2)
    with nav_cols[0]:
        if st.button(t("benchmark.go_step1", default="返回 Step1"), use_container_width=True):
            st.switch_page("pages/1_Data_Processing.py")
    with nav_cols[1]:
        if st.button(t("benchmark.go_finetune", default="前往 FineTune 数据生成"), use_container_width=True):
            st.switch_page("pages/3_Finetune_Generation.py")

    op1, op2 = st.columns(2)
    with op1:
        start_clicked = st.button(
            t("benchmark.generate", default="生成 Benchmark MCQ"),
            type="primary",
            use_container_width=True,
            disabled=bool(bg.get("running")),
        )
    with op2:
        cancel_clicked = st.button(
            t("benchmark.stop_generation", default="中断生成"),
            use_container_width=True,
            disabled=not bool(bg.get("running")),
        )

    if start_clicked and not bg.get("running"):
        cancel_event = threading.Event()
        bg.update(
            {
                "running": True,
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
                def _on_progress(done: int, total: int):
                    bg["progress_done"] = int(done)
                    bg["progress_total"] = int(max(1, total))

                rows = generate_benchmark_mcq(
                    l3_chains=l3_chains,
                    provider=model_ctx["provider"],
                    model=model_ctx["model"],
                    api_key=model_ctx["api_key"],
                    api_base=model_ctx["api_base"],
                    max_workers=max_workers,
                    questions_per_chain=questions_per_chain,
                    temperature=temperature,
                    retries=retries,
                    progress_callback=_on_progress,
                    cancel_event=cancel_event,
                )
                bg["result"] = rows
                bg["stats"] = getattr(generate_benchmark_mcq, "last_run_stats", {})
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
        st.warning(t("benchmark.cancelling", default="正在请求中断，请稍候..."))

    if bg.get("running"):
        done = int(bg.get("progress_done", 0))
        total = int(max(1, bg.get("progress_total", 1)))
        st.progress(
            int(done * 100 / total),
            text=t("benchmark.progress", default="进度：{done}/{total}", done=done, total=total),
        )
        time.sleep(1)
        st.rerun()
    else:
        if bg.get("error"):
            st.error(t("benchmark.gen_failed", default="生成失败：{err}", err=bg["error"]))
            bg["error"] = ""
        elif bg.get("result") is not None:
            rows = list(bg.get("result") or [])
            stats = bg.get("stats") or {}
            SessionStateManager.set_benchmark_mcq(rows)
            bg["result"] = None
            bg["stats"] = None
            if stats.get("cancelled"):
                st.warning(
                    t(
                        "benchmark.cancelled_count",
                        default="已中断，本次保留 {count} 条结果。",
                        count=len(rows),
                    )
                )
            else:
                st.success(
                    t(
                        "benchmark.done_count",
                        default="生成完成，共 {count} 条（目标 {target}）。",
                        count=len(rows),
                        target=len(l3_chains) * questions_per_chain,
                    )
                )
            if stats:
                st.info(
                    t(
                        "benchmark.run_stats",
                        default="任务统计：提交 {submitted}，成功 {succeeded}，失败 {failed}，完全重复丢弃 {dups}，语义重复丢弃 {sem_dups}，补生成轮次 {rounds}",
                        submitted=stats.get("submitted", 0),
                        succeeded=stats.get("succeeded", 0),
                        failed=stats.get("failed", 0),
                        dups=stats.get("duplicates_dropped", 0),
                        sem_dups=stats.get("semantic_dedup_dropped", 0),
                        rounds=stats.get("refill_rounds", 0),
                    )
                )
                st.caption(
                    t(
                        "benchmark.adaptive_stats",
                        default="自适应并发：初始 {initial}，最低 {minw}，最高 {maxw}，最终 {final}，调节次数 {adjusts}",
                        initial=stats.get("initial_workers", 0),
                        minw=stats.get("min_workers", 0),
                        maxw=stats.get("max_workers_seen", 0),
                        final=stats.get("final_workers", 0),
                        adjusts=stats.get("worker_adjustments", 0),
                    )
                )

    rows = SessionStateManager.get_benchmark_mcq()
    if rows:
        st.markdown("---")
        st.markdown(f"### {t('benchmark.results', default='结果')}")
        keyword = st.text_input(t("benchmark.filter_keyword", default="关键词筛选"), "")
        rows_with_id = [{"__row_id__": idx, **row} for idx, row in enumerate(rows)]
        filtered = rows_with_id
        if keyword.strip():
            kw = keyword.strip().lower()
            filtered = [x for x in filtered if kw in json.dumps(x, ensure_ascii=False).lower()]
        edited = st.data_editor(pd.DataFrame(filtered), use_container_width=True, num_rows="dynamic", height=460)
        if st.button(t("benchmark.save_edits", default="保存修改"), use_container_width=True):
            if keyword.strip():
                st.warning(
                    t(
                        "benchmark.save_filtered_warn",
                        default="请先清空筛选后再保存，避免覆盖未显示数据。",
                    )
                )
            else:
                records = edited.to_dict(orient="records")
                cleaned = []
                for r in records:
                    r.pop("__row_id__", None)
                    cleaned.append(r)
                SessionStateManager.set_benchmark_mcq(cleaned)
                st.success(t("benchmark.saved", default="修改已保存"))
        st.download_button(
            t("benchmark.download", default="下载 Benchmark JSON"),
            data=json.dumps(SessionStateManager.get_benchmark_mcq(), ensure_ascii=False, indent=2),
            file_name="benchmark_mcq.json",
            mime="application/json",
        )


if __name__ == "__main__":
    main()
