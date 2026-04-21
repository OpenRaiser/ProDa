from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from ui.utils.i18n_helper import t


def _leaderboard_df(viz: Dict[str, Any]) -> pd.DataFrame:
    leaderboard = list(viz.get("leaderboard", []) or [])
    if not leaderboard:
        return pd.DataFrame(columns=["rank", "model", "accuracy"])
    df = pd.DataFrame(leaderboard)
    if "rank" not in df.columns:
        df = df.sort_values("accuracy", ascending=False).reset_index(drop=True)
        df["rank"] = df.index + 1
    return df


def _per_dataset_df(viz: Dict[str, Any]) -> pd.DataFrame:
    per_dataset = dict(viz.get("per_dataset", {}) or {})
    rows: List[Dict[str, Any]] = []
    for model_name, ds_map in per_dataset.items():
        for ds, score in (ds_map or {}).items():
            try:
                val = float(score)
            except Exception:
                continue
            rows.append({"model": model_name, "dataset": ds, "accuracy": val})
    if not rows:
        return pd.DataFrame(columns=["model", "dataset", "accuracy"])
    return pd.DataFrame(rows)


def render_quick_insights(viz: Dict[str, Any]) -> None:
    df_lb = _leaderboard_df(viz)
    df_ds = _per_dataset_df(viz)
    if df_lb.empty:
        st.info(t("opencompass_eval.no_leaderboard", default="暂无可展示的 leaderboard（summary 可能为空或解析失败）。"))
        return

    st.markdown(f"### {t('opencompass_eval.quick_insights', default='Quick Insights')}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(t("opencompass_eval.top1_model", default="Top1 Model"), str(df_lb.iloc[0]["model"]))
    c2.metric(t("opencompass_eval.top1_acc", default="Top1 Accuracy"), f"{float(df_lb.iloc[0]['accuracy']):.2f}")
    c3.metric(t("opencompass_eval.model_count", default="Model Count"), int(len(df_lb)))
    c4.metric(t("opencompass_eval.dataset_count", default="Dataset Count"), int(df_ds["dataset"].nunique()) if not df_ds.empty else 0)

    if len(df_lb) > 1:
        gap = float(df_lb.iloc[0]["accuracy"]) - float(df_lb.iloc[1]["accuracy"])
        st.caption(t("opencompass_eval.top_gap", default="Top1 与 Top2 差距：{gap:.2f}", gap=gap))


def render_visualization_tab(viz: Dict[str, Any]) -> None:
    df_lb = _leaderboard_df(viz)
    if df_lb.empty:
        st.info(t("opencompass_eval.no_leaderboard", default="暂无可展示的 leaderboard（summary 可能为空或解析失败）。"))
        return

    st.markdown(f"#### {t('opencompass_eval.acc_bar_title', default='Model Accuracy Comparison')}")
    st.bar_chart(df_lb.set_index("model")[["accuracy"]], use_container_width=True)


def render_comparison_tab(viz: Dict[str, Any]) -> None:
    df_lb = _leaderboard_df(viz)
    df_ds = _per_dataset_df(viz)
    if df_lb.empty:
        st.info(t("opencompass_eval.no_leaderboard", default="暂无可展示的 leaderboard（summary 可能为空或解析失败）。"))
        return

    st.markdown(f"#### {t('opencompass_eval.model_table_title', default='Model Detailed Comparison')}")
    show_df = df_lb.copy()
    show_df["accuracy"] = show_df["accuracy"].map(lambda x: f"{float(x):.2f}")
    st.dataframe(show_df, use_container_width=True, height=260)

    if not df_ds.empty:
        st.markdown(f"#### {t('opencompass_eval.dataset_matrix', default='Dataset x Model Matrix')}")
        mat = df_ds.pivot_table(index="dataset", columns="model", values="accuracy", aggfunc="mean")
        st.dataframe(mat, use_container_width=True, height=260)


def render_leaderboard_tab(viz: Dict[str, Any]) -> None:
    df_lb = _leaderboard_df(viz)
    if df_lb.empty:
        st.info(t("opencompass_eval.no_leaderboard", default="暂无可展示的 leaderboard（summary 可能为空或解析失败）。"))
        return
    st.markdown(f"#### {t('opencompass_eval.leaderboard', default='Leaderboard')}")
    for _, row in df_lb.sort_values("rank").iterrows():
        rank = int(row["rank"])
        medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"#{rank}"
        st.text(f"{medal} {row['model']}: {float(row['accuracy']):.2f}")
