from __future__ import annotations

import streamlit as st

from ui.utils.i18n_helper import t
from ui.utils.session_state import SessionStateManager


def render_workflow_sidebar() -> None:
    with st.sidebar:
        st.markdown(f"### {t('app.title')}")
        st.caption(t("app.description"))
        st.markdown("---")
        for key in [
            "workflow.step1",
            "workflow.step2",
            "workflow.step3",
            "workflow.step5",
            "workflow.step6",
            "workflow.step7",
        ]:
            st.markdown(f"- {t(key)}")


def render_placeholder_page(title_key: str) -> None:
    st.title(t(title_key))
    st.info(t("placeholder.desc"))
    st.warning(t("placeholder.blocked"))


def enforce_active_project() -> None:
    if SessionStateManager.has_active_project():
        return
    st.warning(t("project_hub.must_select_project"))
    if st.button(t("project_hub.go_hub"), type="primary"):
        st.switch_page("streamlit_app.py")
    st.stop()

