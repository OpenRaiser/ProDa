from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from proda.extractor import extract_knowledge_core  # noqa: E402
from ui.components.top_bar import render_top_bar, selected_model_context  # noqa: E402
from ui.utils.document_loader import chunk_text, extract_json_paths, read_uploaded_file  # noqa: E402
from ui.utils.i18n_helper import init_i18n, t  # noqa: E402
from ui.utils.session_state import SessionStateManager  # noqa: E402
from ui.utils.ui_helpers import enforce_active_project, render_workflow_sidebar  # noqa: E402


st.set_page_config(page_title="ProDA - Step1", page_icon="📁", layout="wide")


def _merge_cores(cores: List[Dict[str, Any]]) -> Dict[str, Any]:
    all_l1, all_l2, all_l3 = [], [], []
    total_chars = 0
    for core in cores:
        all_l1.extend(core.get("l1_concepts", []))
        all_l2.extend(core.get("l2_statements", []))
        all_l3.extend(core.get("l3_chains", []))
        total_chars += int(core.get("statistics", {}).get("text_length", 0))

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


def _render_results() -> None:
    core = SessionStateManager.get_knowledge_core()
    if not core:
        return
    st.markdown(f"### {t('page_data_processing.result_title')}")
    stats = core.get("statistics", {})
    c1, c2, c3 = st.columns(3)
    c1.metric("L3", stats.get("total_chains", 0))
    c2.metric("L2", stats.get("total_statements", 0))
    c3.metric("L1", stats.get("total_concepts", 0))

    tab_l1, tab_l2, tab_l3, tab_export = st.tabs(
        [
            t("page_data_processing.l1_tab"),
            t("page_data_processing.l2_tab"),
            t("page_data_processing.l3_tab"),
            t("page_data_processing.export_tab"),
        ]
    )

    with tab_l1:
        keyword = st.text_input(t("page_data_processing.search"), key="l1_search")
        rows = core.get("l1_concepts", [])
        if keyword:
            rows = [r for r in rows if keyword.lower() in str(r.get("term", "")).lower()]
        edited = st.data_editor(pd.DataFrame(rows), use_container_width=True, num_rows="dynamic")
        if st.button(t("page_data_processing.save_edits"), key="save_l1"):
            core["l1_concepts"] = edited.to_dict(orient="records")
            SessionStateManager.set_knowledge_core(core)
            st.success(t("page_data_processing.saved_edits"))

    with tab_l2:
        l2_rows = core.get("l2_statements", [])
        chain_ids = [t("page_data_processing.all")] + sorted(
            {x.get("parent_chain_id", "") for x in l2_rows if x.get("parent_chain_id")}
        )
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            chain = st.selectbox(t("page_data_processing.chain_filter"), options=chain_ids)
        with col_f2:
            keyword = st.text_input(t("page_data_processing.search"), key="l2_search")
        filtered = l2_rows
        if chain != t("page_data_processing.all"):
            filtered = [r for r in filtered if r.get("parent_chain_id") == chain]
        if keyword:
            filtered = [r for r in filtered if keyword.lower() in json.dumps(r, ensure_ascii=False).lower()]
        edited = st.data_editor(pd.DataFrame(l2_rows), use_container_width=True, num_rows="dynamic")
        if st.button(t("page_data_processing.save_edits"), key="save_l2"):
            core["l2_statements"] = edited.to_dict(orient="records")
            SessionStateManager.set_knowledge_core(core)
            st.success(t("page_data_processing.saved_edits"))

    with tab_l3:
        l3_rows = []
        for row in core.get("l3_chains", []):
            l3_rows.append(
                {
                    "chain_id": row.get("chain_id", ""),
                    "domain_context": row.get("domain_context", ""),
                    "process_name": row.get("process_name", ""),
                    "narrative_summary": row.get("narrative_summary", ""),
                    "steps_text": "\n".join(row.get("steps", [])),
                }
            )
        edited = st.data_editor(pd.DataFrame(l3_rows), use_container_width=True, num_rows="dynamic")
        if st.button(t("page_data_processing.save_edits"), key="save_l3"):
            rows = edited.to_dict(orient="records")
            rebuilt = []
            for row in rows:
                rebuilt.append(
                    {
                        "chain_id": row.get("chain_id", ""),
                        "domain_context": row.get("domain_context", ""),
                        "process_name": row.get("process_name", ""),
                        "narrative_summary": row.get("narrative_summary", ""),
                        "steps": [s.strip() for s in str(row.get("steps_text", "")).splitlines() if s.strip()],
                    }
                )
            core["l3_chains"] = rebuilt
            SessionStateManager.set_knowledge_core(core)
            st.success(t("page_data_processing.saved_edits"))

    with tab_export:
        st.download_button(
            t("page_data_processing.download_json"),
            data=json.dumps(core, ensure_ascii=False, indent=2),
            file_name="knowledge_core.json",
            mime="application/json",
        )

    st.markdown("---")
    st.markdown(f"### {t('page_data_processing.next_actions_title', default='下一步')}")
    c_next_1, c_next_2 = st.columns(2)
    with c_next_1:
        if st.button(
            t("page_data_processing.go_benchmark", default="前往 Benchmark 数据生成"),
            type="primary",
            use_container_width=True,
        ):
            st.switch_page("pages/2_Benchmark_Generation.py")
    with c_next_2:
        if st.button(
            t("page_data_processing.go_finetune", default="前往 FineTune 数据生成"),
            type="primary",
            use_container_width=True,
        ):
            st.switch_page("pages/3_Finetune_Generation.py")


def main() -> None:
    init_i18n()
    SessionStateManager.initialize()
    render_top_bar()
    render_workflow_sidebar()
    enforce_active_project()

    st.title(t("page_data_processing.title"))
    st.info(t("page_data_processing.desc"))

    st.markdown(f"### {t('page_data_processing.upload_title')}")
    st.caption(t("page_data_processing.upload_help"))
    uploaded_files = st.file_uploader(
        label=t("page_data_processing.upload_title"),
        label_visibility="collapsed",
        accept_multiple_files=True,
        type=["pdf", "txt", "md", "docx", "json"],
    )

    json_files = [f for f in uploaded_files if f.name.lower().endswith(".json")] if uploaded_files else []
    selected_fields = SessionStateManager.get_json_fields()
    if json_files:
        sample_obj = json.loads(json_files[0].getvalue().decode("utf-8", errors="ignore"))
        all_paths = extract_json_paths(sample_obj)
        selected_fields = st.multiselect(
            t("page_data_processing.json_fields"),
            options=all_paths,
            default=selected_fields,
        )
        SessionStateManager.set_json_fields(selected_fields)

    st.markdown("---")
    st.markdown(f"### {t('page_data_processing.extract_config_title', default='提取配置')}")
    c_cfg_1, c_cfg_2, c_cfg_3 = st.columns(3)
    with c_cfg_1:
        chunk_size = st.number_input(
            t("page_data_processing.chunk_size", default="分块大小（字符）"),
            min_value=2000,
            max_value=30000,
            value=int(st.session_state.get("cfg_chunk_size", 10000)),
            step=500,
        )
        chunk_overlap = st.number_input(
            t("page_data_processing.chunk_overlap", default="分块重叠（字符）"),
            min_value=0,
            max_value=3000,
            value=int(st.session_state.get("cfg_chunk_overlap", 800)),
            step=100,
        )
    with c_cfg_2:
        processing_mode = st.selectbox(
            t("page_data_processing.processing_mode", default="处理模式"),
            options=["auto", "merge", "per_chunk"],
            index=["auto", "merge", "per_chunk"].index(st.session_state.get("cfg_processing_mode", "auto")),
            format_func=lambda x: t(f"page_data_processing.processing_mode_{x}", default=x),
        )
        merge_threshold = st.number_input(
            t("page_data_processing.merge_threshold", default="自动模式合并阈值（字符）"),
            min_value=2000,
            max_value=100000,
            value=int(st.session_state.get("cfg_merge_threshold", 16000)),
            step=1000,
            disabled=processing_mode != "auto",
        )
    with c_cfg_3:
        parallel_chunks = st.checkbox(
            t("page_data_processing.parallel_chunks", default="逐块模式并发提取"),
            value=bool(st.session_state.get("cfg_parallel_chunks", True)),
            disabled=processing_mode == "merge",
        )
        max_workers = st.slider(
            t("page_data_processing.max_workers", default="最大并发数"),
            min_value=1,
            max_value=16,
            value=int(st.session_state.get("cfg_max_workers", 4)),
            disabled=(processing_mode == "merge" or not parallel_chunks),
        )

    st.session_state["cfg_chunk_size"] = int(chunk_size)
    st.session_state["cfg_chunk_overlap"] = int(chunk_overlap)
    st.session_state["cfg_processing_mode"] = processing_mode
    st.session_state["cfg_merge_threshold"] = int(merge_threshold)
    st.session_state["cfg_parallel_chunks"] = bool(parallel_chunks)
    st.session_state["cfg_max_workers"] = int(max_workers)

    if st.button(t("page_data_processing.extract_button"), type="primary", use_container_width=True):
        model_ctx = selected_model_context()
        if not uploaded_files:
            st.warning(t("page_data_processing.no_files"))
            return
        if not SessionStateManager.get_selected_model():
            st.warning(t("page_data_processing.choose_model_first"))
            return
        if not model_ctx or not model_ctx.get("api_key"):
            st.warning(t("page_data_processing.api_not_ready"))
            return

        with st.spinner(t("page_data_processing.extracting")):
            try:
                texts = []
                for file_obj in uploaded_files:
                    content = read_uploaded_file(file_obj, selected_fields)
                    if content.strip():
                        texts.append(content)
                merged_text = "\n\n".join(texts)
                chunks = chunk_text(merged_text, chunk_size=int(chunk_size), overlap=int(chunk_overlap))

                # Align with OpenDataBench behavior: auto / merge / per_chunk + parallel workers
                effective_mode = processing_mode
                if processing_mode == "auto":
                    effective_mode = "merge" if len(merged_text) < int(merge_threshold) or len(chunks) <= 1 else "per_chunk"

                progress = st.progress(0, text=t("page_data_processing.extracting"))

                if effective_mode == "merge":
                    core = extract_knowledge_core(
                        text=merged_text,
                        provider=model_ctx["provider"],
                        model=model_ctx["model"],
                        api_key=model_ctx["api_key"],
                        api_base=model_ctx["api_base"],
                    )
                    core.setdefault("statistics", {})
                    core["statistics"]["num_chunks"] = len(chunks)
                    core["statistics"]["processing_mode"] = "merge"
                    SessionStateManager.set_knowledge_core(core)
                    progress.progress(100, text=t("page_data_processing.extract_done", default="提取完成"))
                else:
                    cores: List[Dict[str, Any]] = []
                    total = len(chunks)
                    if parallel_chunks and total > 1 and int(max_workers) > 1:
                        with ThreadPoolExecutor(max_workers=int(max_workers)) as executor:
                            future_map = {
                                executor.submit(
                                    extract_knowledge_core,
                                    chunk,
                                    model_ctx["provider"],
                                    model_ctx["model"],
                                    model_ctx["api_key"],
                                    model_ctx["api_base"],
                                ): idx
                                for idx, chunk in enumerate(chunks)
                            }
                            done_count = 0
                            ordered_results: Dict[int, Dict[str, Any]] = {}
                            for future in as_completed(future_map):
                                idx = future_map[future]
                                ordered_results[idx] = future.result()
                                done_count += 1
                                progress.progress(
                                    int(done_count * 100 / total),
                                    text=t(
                                        "page_data_processing.extract_progress",
                                        default="分块提取中：{done}/{total}",
                                        done=done_count,
                                        total=total,
                                    ),
                                )
                            for i in range(total):
                                cores.append(ordered_results[i])
                    else:
                        for idx, chunk in enumerate(chunks, start=1):
                            cores.append(
                                extract_knowledge_core(
                                    text=chunk,
                                    provider=model_ctx["provider"],
                                    model=model_ctx["model"],
                                    api_key=model_ctx["api_key"],
                                    api_base=model_ctx["api_base"],
                                )
                            )
                            progress.progress(
                                int(idx * 100 / len(chunks)),
                                text=t(
                                    "page_data_processing.extract_progress",
                                    default="分块提取中：{done}/{total}",
                                    done=idx,
                                    total=len(chunks),
                                ),
                            )

                    merged_core = _merge_cores(cores)
                    merged_core.setdefault("statistics", {})
                    merged_core["statistics"]["num_chunks"] = len(chunks)
                    merged_core["statistics"]["processing_mode"] = "per_chunk"
                    SessionStateManager.set_knowledge_core(merged_core)
                    progress.progress(100, text=t("page_data_processing.extract_done", default="提取完成"))
            except Exception as exc:
                st.error(t("page_data_processing.extract_failed", error=str(exc)))

    _render_results()


if __name__ == "__main__":
    main()

