from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import streamlit as st


LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"
SUPPORTED = {"zh", "en"}


def _load_locale(lang: str) -> Dict[str, Any]:
    path = LOCALES_DIR / f"{lang}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def init_i18n() -> None:
    if "language" not in st.session_state:
        st.session_state["language"] = "zh"
    if "translations" not in st.session_state:
        st.session_state["translations"] = _load_locale(st.session_state["language"])


def switch_language(lang: str) -> None:
    if lang not in SUPPORTED:
        return
    st.session_state["language"] = lang
    st.session_state["translations"] = _load_locale(lang)
    st.rerun()


def toggle_language() -> None:
    init_i18n()
    switch_language("en" if st.session_state["language"] == "zh" else "zh")


def get_text(key: str, default: Optional[str] = None, **kwargs) -> str:
    init_i18n()
    cur: Any = st.session_state.get("translations", {})
    for part in key.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            cur = default if default is not None else key
            break
    if not isinstance(cur, str):
        cur = default if default is not None else key
    if kwargs:
        try:
            cur = cur.format(**kwargs)
        except Exception:
            pass
    return cur


t = get_text

