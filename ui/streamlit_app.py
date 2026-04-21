from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ui.components.top_bar import render_top_bar
from ui.utils.i18n_helper import init_i18n, t
from ui.utils.project_store import create_project, delete_project, get_project, list_projects, rename_project
from ui.utils.session_state import SessionStateManager
from ui.utils.ui_helpers import render_workflow_sidebar


st.set_page_config(page_title="ProDA", page_icon="📘", layout="wide")


def main() -> None:
    init_i18n()
    SessionStateManager.initialize()
    render_top_bar()
    render_workflow_sidebar()

    st.title(t("project_hub.title"))
    st.caption(t("project_hub.desc"))

    active = SessionStateManager.get_current_project_id()
    projects = list_projects()
    project_map = {p["id"]: p for p in projects}
    if active and active in project_map:
        current_project = project_map[active]
        st.success(t("project_hub.current_project", name=current_project["name"]))
        c1, c2 = st.columns(2)
        with c1:
            if st.button(t("project_hub.enter_project"), type="primary", use_container_width=True):
                st.switch_page("pages/1_Data_Processing.py")
        with c2:
            if st.button(t("project_hub.switch_project"), use_container_width=True):
                SessionStateManager.exit_project()
                st.rerun()

        with st.expander(t("project_hub.manage_current"), expanded=False):
            with st.form("rename_project_form"):
                rename_name = st.text_input(t("project_hub.project_name"), value=current_project.get("name", ""))
                rename_desc = st.text_area(t("project_hub.project_desc"), value=current_project.get("description", ""))
                rename_clicked = st.form_submit_button(t("project_hub.rename_button"))
            if rename_clicked:
                if not rename_name.strip():
                    st.warning(t("project_hub.name_required"))
                else:
                    rename_project(active, rename_name, rename_desc)
                    st.success(t("project_hub.renamed", name=rename_name.strip()))
                    st.rerun()

            st.markdown("---")
            st.caption(t("project_hub.delete_warning"))
            confirm_delete = st.checkbox(t("project_hub.delete_confirm"), key="delete_current_confirm")
            if st.button(t("project_hub.delete_button"), type="secondary", use_container_width=True):
                if not confirm_delete:
                    st.warning(t("project_hub.delete_check_required"))
                else:
                    deleted = delete_project(active)
                    SessionStateManager.exit_project()
                    if deleted:
                        st.success(t("project_hub.deleted"))
                    st.rerun()

    st.markdown("---")
    st.markdown(f"### {t('project_hub.create_title')}")
    with st.form("create_project_form"):
        new_name = st.text_input(t("project_hub.project_name"))
        new_desc = st.text_area(t("project_hub.project_desc"))
        create_clicked = st.form_submit_button(t("project_hub.create_button"), type="primary")
    if create_clicked:
        if not new_name.strip():
            st.warning(t("project_hub.name_required"))
        else:
            project = create_project(new_name, new_desc)
            SessionStateManager.enter_project(project["id"])
            st.success(t("project_hub.created_and_entered", name=project["name"]))
            st.switch_page("pages/1_Data_Processing.py")

    st.markdown("---")
    st.markdown(f"### {t('project_hub.select_title')}")
    if not projects:
        st.info(t("project_hub.no_projects"))
        return

    choices = [f"{p['name']} ({p['id']})" for p in projects]
    reverse = {f"{p['name']} ({p['id']})": p["id"] for p in projects}
    selected_label = st.selectbox(t("project_hub.select_project"), options=choices)
    selected_id = reverse[selected_label]
    selected_project = get_project(selected_id)
    if selected_project:
        st.caption(
            t(
                "project_hub.project_meta",
                created=str(selected_project.get("created_at", ""))[:19],
                updated=str(selected_project.get("updated_at", ""))[:19],
            )
        )
    if st.button(t("project_hub.open_button"), type="primary"):
        SessionStateManager.enter_project(selected_id)
        st.switch_page("pages/1_Data_Processing.py")

    st.caption(t("project_hub.delete_warning"))
    delete_selected_confirm = st.checkbox(
        t("project_hub.delete_selected_confirm", default="我确认删除当前选中的项目"),
        key="delete_selected_project_confirm",
    )
    if st.button(t("project_hub.delete_selected_button", default="删除当前选中项目"), type="secondary"):
        if not delete_selected_confirm:
            st.warning(t("project_hub.delete_check_required"))
        else:
            deleted = delete_project(selected_id)
            if deleted:
                if SessionStateManager.get_current_project_id() == selected_id:
                    SessionStateManager.exit_project()
                st.success(t("project_hub.deleted"))
                st.rerun()
            else:
                st.warning(t("project_hub.delete_not_found", default="项目不存在或已被删除。"))


if __name__ == "__main__":
    main()

