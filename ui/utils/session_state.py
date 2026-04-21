from __future__ import annotations

import streamlit as st

from ui.utils.llm_config import default_llm_profiles, normalize_llm_profiles
from ui.utils.project_store import load_project_state, mark_project_opened, save_project_state


class SessionStateManager:
    CURRENT_PROJECT_ID = "current_project_id"
    LLM_PROFILES = "llm_profiles"
    SELECTED_MODEL = "selected_model"
    KNOWLEDGE_CORE = "knowledge_core"
    BENCHMARK_MCQ = "benchmark_mcq"
    FINETUNE_DATA = "finetune_data"
    JSON_FIELDS = "json_fields"

    @staticmethod
    def initialize() -> None:
        if SessionStateManager.CURRENT_PROJECT_ID not in st.session_state:
            st.session_state[SessionStateManager.CURRENT_PROJECT_ID] = ""
        if SessionStateManager.LLM_PROFILES not in st.session_state:
            st.session_state[SessionStateManager.LLM_PROFILES] = default_llm_profiles()
        if SessionStateManager.SELECTED_MODEL not in st.session_state:
            st.session_state[SessionStateManager.SELECTED_MODEL] = ""
        if SessionStateManager.KNOWLEDGE_CORE not in st.session_state:
            st.session_state[SessionStateManager.KNOWLEDGE_CORE] = None
        if SessionStateManager.BENCHMARK_MCQ not in st.session_state:
            st.session_state[SessionStateManager.BENCHMARK_MCQ] = []
        if SessionStateManager.FINETUNE_DATA not in st.session_state:
            st.session_state[SessionStateManager.FINETUNE_DATA] = []
        if SessionStateManager.JSON_FIELDS not in st.session_state:
            st.session_state[SessionStateManager.JSON_FIELDS] = []

    @staticmethod
    def has_active_project() -> bool:
        return bool(st.session_state.get(SessionStateManager.CURRENT_PROJECT_ID, ""))

    @staticmethod
    def get_current_project_id() -> str:
        return st.session_state.get(SessionStateManager.CURRENT_PROJECT_ID, "")

    @staticmethod
    def enter_project(project_id: str) -> None:
        SessionStateManager.initialize()
        state = load_project_state(project_id)
        mark_project_opened(project_id)
        st.session_state[SessionStateManager.CURRENT_PROJECT_ID] = project_id
        st.session_state[SessionStateManager.LLM_PROFILES] = normalize_llm_profiles(state.get("llm_profiles", {}))
        st.session_state[SessionStateManager.SELECTED_MODEL] = str(state.get("selected_model", ""))
        st.session_state[SessionStateManager.KNOWLEDGE_CORE] = state.get("knowledge_core")
        st.session_state[SessionStateManager.BENCHMARK_MCQ] = state.get("benchmark_mcq", [])
        st.session_state[SessionStateManager.FINETUNE_DATA] = state.get("finetune_data", [])
        st.session_state[SessionStateManager.JSON_FIELDS] = state.get("json_fields", [])

    @staticmethod
    def exit_project() -> None:
        SessionStateManager.persist_active_project_state()
        st.session_state[SessionStateManager.CURRENT_PROJECT_ID] = ""
        st.session_state[SessionStateManager.LLM_PROFILES] = default_llm_profiles()
        st.session_state[SessionStateManager.SELECTED_MODEL] = ""
        st.session_state[SessionStateManager.KNOWLEDGE_CORE] = None
        st.session_state[SessionStateManager.BENCHMARK_MCQ] = []
        st.session_state[SessionStateManager.FINETUNE_DATA] = []
        st.session_state[SessionStateManager.JSON_FIELDS] = []

    @staticmethod
    def persist_active_project_state() -> None:
        project_id = SessionStateManager.get_current_project_id()
        if not project_id:
            return
        payload = {
            "llm_profiles": st.session_state.get(SessionStateManager.LLM_PROFILES, default_llm_profiles()),
            "selected_model": st.session_state.get(SessionStateManager.SELECTED_MODEL, ""),
            "knowledge_core": st.session_state.get(SessionStateManager.KNOWLEDGE_CORE),
            "benchmark_mcq": st.session_state.get(SessionStateManager.BENCHMARK_MCQ, []),
            "finetune_data": st.session_state.get(SessionStateManager.FINETUNE_DATA, []),
            "json_fields": st.session_state.get(SessionStateManager.JSON_FIELDS, []),
        }
        save_project_state(project_id, payload)

    @staticmethod
    def get_llm_profiles():
        return st.session_state.get(SessionStateManager.LLM_PROFILES, {})

    @staticmethod
    def set_llm_profiles(profiles):
        st.session_state[SessionStateManager.LLM_PROFILES] = profiles
        SessionStateManager.persist_active_project_state()

    @staticmethod
    def get_selected_model() -> str:
        return st.session_state.get(SessionStateManager.SELECTED_MODEL, "")

    @staticmethod
    def set_selected_model(model_key: str) -> None:
        st.session_state[SessionStateManager.SELECTED_MODEL] = model_key
        SessionStateManager.persist_active_project_state()

    @staticmethod
    def get_knowledge_core():
        return st.session_state.get(SessionStateManager.KNOWLEDGE_CORE)

    @staticmethod
    def set_knowledge_core(data):
        st.session_state[SessionStateManager.KNOWLEDGE_CORE] = data
        SessionStateManager.persist_active_project_state()

    @staticmethod
    def get_benchmark_mcq():
        return st.session_state.get(SessionStateManager.BENCHMARK_MCQ, [])

    @staticmethod
    def set_benchmark_mcq(data):
        st.session_state[SessionStateManager.BENCHMARK_MCQ] = data
        SessionStateManager.persist_active_project_state()

    @staticmethod
    def get_finetune_data():
        return st.session_state.get(SessionStateManager.FINETUNE_DATA, [])

    @staticmethod
    def set_finetune_data(data):
        st.session_state[SessionStateManager.FINETUNE_DATA] = data
        SessionStateManager.persist_active_project_state()

    @staticmethod
    def get_json_fields():
        return st.session_state.get(SessionStateManager.JSON_FIELDS, [])

    @staticmethod
    def set_json_fields(fields):
        st.session_state[SessionStateManager.JSON_FIELDS] = fields
        SessionStateManager.persist_active_project_state()

