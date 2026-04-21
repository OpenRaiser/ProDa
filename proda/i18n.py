from __future__ import annotations

from typing import Dict

import streamlit as st


TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "zh": {
        "app_title": "ProDA - Step 1 知识抽取",
        "step_intro": "Step 1 · Extract——从语料中提取三级知识结构。完成后，知识面板展示 L1 概念列表、L2 关系图谱、L3 推理链条。用户可浏览、筛选、修正提取结果，如同在 IDE 中审查自动生成的代码。",
        "global_config": "全局 LLM 配置（项目级，仅需配置一次）",
        "provider": "服务商",
        "api_key": "API Key",
        "api_base": "API Base（可选）",
        "save_config": "保存全局配置",
        "config_saved": "全局配置已保存",
        "model_selector": "模型选择",
        "choose_model_first": "请先在右上角选择模型后再开始生成。",
        "language_toggle": "English",
        "upload_title": "原始文档上传",
        "upload_help": "支持 PDF / TXT / MD / DOCX / JSON，可多文件。",
        "extract_button": "开始提取 L1/L2/L3",
        "extracting": "正在抽取知识核心，请稍候...",
        "no_files": "请先上传至少一个文档。",
        "result_title": "知识核心面板",
        "l1_tab": "L1 概念列表",
        "l2_tab": "L2 关系图谱",
        "l3_tab": "L3 推理链条",
        "export_tab": "导出",
        "search": "搜索",
        "chain_filter": "按链路过滤",
        "all": "全部",
        "download_json": "下载知识核心 JSON",
        "save_edits": "保存当前修订",
        "saved_edits": "已保存修订结果",
        "extract_failed": "抽取失败",
        "doc_stats": "文档统计",
        "num_files": "文件数",
        "num_chars": "字符数",
        "num_chunks": "切块数",
        "json_fields": "JSON 字段选择（可选）",
    },
    "en": {
        "app_title": "ProDA - Step 1 Extraction",
        "step_intro": "Step 1 · Extract — Build three-layer knowledge structure from raw documents. After completion, the panel shows L1 concepts, L2 relationship graph, and L3 reasoning chains. Users can browse, filter, and revise extraction results like reviewing auto-generated code in an IDE.",
        "global_config": "Global LLM Config (project-level, configure once)",
        "provider": "Provider",
        "api_key": "API Key",
        "api_base": "API Base (optional)",
        "save_config": "Save Global Config",
        "config_saved": "Global config saved",
        "model_selector": "Model Selection",
        "choose_model_first": "Please choose a model from the top-right selector first.",
        "language_toggle": "中文",
        "upload_title": "Upload Source Documents",
        "upload_help": "Supports PDF / TXT / MD / DOCX / JSON, multiple files allowed.",
        "extract_button": "Extract L1/L2/L3",
        "extracting": "Extracting knowledge core, please wait...",
        "no_files": "Please upload at least one file.",
        "result_title": "Knowledge Core Panel",
        "l1_tab": "L1 Concepts",
        "l2_tab": "L2 Relationship Graph",
        "l3_tab": "L3 Reasoning Chains",
        "export_tab": "Export",
        "search": "Search",
        "chain_filter": "Filter by chain",
        "all": "All",
        "download_json": "Download knowledge core JSON",
        "save_edits": "Save Current Edits",
        "saved_edits": "Edits saved",
        "extract_failed": "Extraction failed",
        "doc_stats": "Document Stats",
        "num_files": "Files",
        "num_chars": "Characters",
        "num_chunks": "Chunks",
        "json_fields": "JSON field selection (optional)",
    },
}


def init_language() -> None:
    if "lang" not in st.session_state:
        st.session_state["lang"] = "zh"


def t(key: str) -> str:
    init_language()
    lang = st.session_state["lang"]
    return TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(key, key)


def toggle_language() -> None:
    init_language()
    st.session_state["lang"] = "en" if st.session_state["lang"] == "zh" else "zh"
    st.rerun()

