from __future__ import annotations

import streamlit as st

from ui.utils.i18n_helper import t, toggle_language
from ui.utils.llm_config import (
    configured_model_options,
    parse_selected_model,
    normalize_llm_profiles,
    test_connectivity,
)
from ui.utils.session_state import SessionStateManager


def _render_config_popover() -> None:
    profiles = SessionStateManager.get_llm_profiles()
    st.markdown(f"**{t('llm_config.title')}**")
    provider = st.selectbox(t("llm_config.provider"), options=["openai", "anthropic", "deepseek"], key="cfg_provider")
    current = profiles.get(provider, {})
    verified_models = list(current.get("verified_models", []))
    if verified_models:
        st.success(t("llm_config.provider_ready", count=len(verified_models)))
        st.caption(", ".join(verified_models))
    else:
        st.warning(t("llm_config.provider_not_ready"))

    api_key = st.text_input(
        t("llm_config.api_key"),
        value=str(current.get("api_key", "")),
        type="password",
        key=f"cfg_api_key_{provider}",
    )
    api_base = st.text_input(
        t("llm_config.api_base"),
        value=str(current.get("api_base", "")),
        key=f"cfg_api_base_{provider}",
    )
    model_name = st.text_input(
        t("llm_config.model_name"),
        value=str(current.get("last_model", "")),
        key=f"cfg_model_name_{provider}",
        help=t("llm_config.model_name_help"),
    )

    if st.button(t("llm_config.test_connection"), key=f"cfg_test_{provider}", use_container_width=True):
        ok, models, error = test_connectivity(provider, api_key, api_base, model_name)
        if ok:
            st.session_state[f"cfg_models_{provider}"] = models
            st.session_state[f"cfg_model_ok_{provider}"] = model_name.strip()
            st.session_state[f"cfg_status_{provider}"] = "ok"
            st.success(t("llm_config.connection_ok"))
        else:
            st.session_state[f"cfg_model_ok_{provider}"] = ""
            st.session_state[f"cfg_status_{provider}"] = "failed"
            st.error(t("llm_config.connection_failed", error=error))

    tested_models = st.session_state.get(f"cfg_models_{provider}", [])
    tested_model = st.session_state.get(f"cfg_model_ok_{provider}", "")
    status = st.session_state.get(f"cfg_status_{provider}", "")
    if status == "ok":
        st.markdown(f"✅ {t('llm_config.status_ok')}")
    elif status == "failed":
        st.markdown(f"❌ {t('llm_config.status_failed')}")

    if st.button(t("llm_config.save_config"), key=f"cfg_save_{provider}", type="primary", use_container_width=True):
        if not tested_model:
            st.warning(t("llm_config.save_need_test"))
            return
        available_list = tested_models if tested_models else list(current.get("available_models", []))
        verified_list = list(current.get("verified_models", []))
        if tested_model not in verified_list:
            verified_list.append(tested_model)
        verified_list = sorted(list({str(x).strip() for x in verified_list if str(x).strip()}))
        available_list = sorted(list({str(x).strip() for x in available_list if str(x).strip()}))
        profiles[provider] = {
            "api_key": api_key,
            "api_base": api_base,
            "available_models": available_list,
            "verified_models": verified_list,
            "configured": len(verified_list) > 0,
            "last_model": tested_model,
        }
        SessionStateManager.set_llm_profiles(normalize_llm_profiles(profiles))
        st.success(t("llm_config.saved"))
        st.caption(t("llm_config.models_hint"))
        st.rerun()

    if verified_models:
        remove_target = st.selectbox(
            t("llm_config.remove_model_select"),
            options=[""] + verified_models,
            key=f"cfg_remove_select_{provider}",
        )
        if st.button(t("llm_config.remove_model_button"), key=f"cfg_remove_btn_{provider}", use_container_width=True):
            if not remove_target:
                st.warning(t("llm_config.remove_choose_first"))
            else:
                left = [m for m in verified_models if m != remove_target]
                available = [m for m in list(current.get("available_models", [])) if m != remove_target]
                profiles[provider] = {
                    "api_key": api_key,
                    "api_base": api_base,
                    "available_models": available,
                    "verified_models": left,
                    "configured": len(left) > 0,
                    "last_model": str(current.get("last_model", "")) if str(current.get("last_model", "")) != remove_target else "",
                }
                SessionStateManager.set_llm_profiles(normalize_llm_profiles(profiles))
                st.success(t("llm_config.removed_model", model=remove_target))
                st.rerun()


def render_top_bar() -> None:
    SessionStateManager.initialize()
    col_title, col_model, col_cfg, col_lang, col_exit = st.columns([4, 3, 1, 1, 1])

    with col_title:
        st.markdown(f"## {t('app.title')} · {t('app.subtitle')}")

    with col_model:
        profiles = SessionStateManager.get_llm_profiles()
        options = configured_model_options(profiles)
        key_to_label = {key: label for key, label in options}
        model_keys = [key for key, _ in options]
        current = SessionStateManager.get_selected_model()

        if not model_keys:
            st.selectbox(t("topbar.model_selector"), options=[t("topbar.no_models")], index=0, disabled=True)
            st.caption(t("topbar.choose_model_hint"))
        else:
            idx = model_keys.index(current) if current in model_keys else 0
            selected = st.selectbox(
                t("topbar.model_selector"),
                options=model_keys,
                index=idx,
                format_func=lambda x: key_to_label.get(x, x),
                key="topbar_model_selector",
            )
            if selected != current:
                SessionStateManager.set_selected_model(selected)

    with col_cfg:
        with st.popover(t("topbar.config_button"), use_container_width=True):
            _render_config_popover()

    with col_lang:
        if st.button(t("topbar.language_button"), use_container_width=True):
            toggle_language()

    with col_exit:
        if SessionStateManager.has_active_project() and st.button(t("topbar.exit_project"), use_container_width=True):
            SessionStateManager.exit_project()
            st.switch_page("streamlit_app.py")


def selected_model_context():
    profiles = SessionStateManager.get_llm_profiles()
    selected = SessionStateManager.get_selected_model()
    provider, model = parse_selected_model(selected)
    if not provider or not model:
        return None
    payload = profiles.get(provider, {})
    if not payload.get("configured"):
        return None
    return {
        "provider": provider,
        "model": model,
        "api_key": str(payload.get("api_key", "")),
        "api_base": str(payload.get("api_base", "")),
    }

