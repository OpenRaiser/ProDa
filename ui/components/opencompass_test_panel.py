from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from ui.utils.i18n_helper import t


def _load_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _answer_labels(text: Any) -> List[str]:
    s = str(text or "").upper()
    labels = re.findall(r"[A-Z]", s)
    out: List[str] = []
    for x in labels:
        if x not in out:
            out.append(x)
    return out


def _norm_answer(text: Any) -> str:
    labels = sorted(_answer_labels(text))
    return ",".join(labels)


def _infer_question_type(item: Dict[str, Any]) -> str:
    qtype = str(item.get("question_type", "")).strip().lower()
    if qtype:
        return qtype
    opts = item.get("options", {}) or {}
    if isinstance(opts, dict) and len(opts) == 2:
        a = str(opts.get("A", "")).strip().lower()
        b = str(opts.get("B", "")).strip().lower()
        if a in {"true", "正确"} and b in {"false", "错误"}:
            return "true_false"
    return "multiple_choice" if len(_answer_labels(item.get("answer", ""))) > 1 else "single_choice"


def _build_test_rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    benchmark_path = Path(str(payload.get("benchmark_json", "")))
    benchmark = _load_json(benchmark_path, [])
    if not isinstance(benchmark, list):
        benchmark = []

    result = payload.get("result", {}) or {}
    run_dir = Path(str(result.get("run_dir", "")))
    models = payload.get("models", []) or []

    rows: List[Dict[str, Any]] = []
    for m in models:
        if not bool(m.get("enabled", True)):
            continue
        abbr = str(m.get("abbr", "")).strip()
        if not abbr:
            continue
        result_path = run_dir / "results" / abbr / "proda_bench.json"
        model_result = _load_json(result_path, {})
        details = model_result.get("details", {}) if isinstance(model_result, dict) else {}
        if not isinstance(details, dict):
            continue

        for k, d in details.items():
            if not isinstance(d, dict):
                continue
            try:
                idx = int(k)
            except Exception:
                continue
            b = benchmark[idx] if 0 <= idx < len(benchmark) and isinstance(benchmark[idx], dict) else {}
            question = str(d.get("question") or b.get("question") or "").strip()
            options = d.get("options") or b.get("options") or {}
            pred = str(d.get("predictions", d.get("prediction", ""))).strip()
            gold = str(d.get("references", d.get("gold", b.get("answer", "")))).strip()
            passed = _norm_answer(pred) == _norm_answer(gold)

            subject = str(b.get("domain_context") or b.get("subject") or "unknown").strip()
            knowledge = str(b.get("process_name") or b.get("knowledge_node") or b.get("chain_id") or "unknown").strip()
            qtype = _infer_question_type(b)

            rows.append(
                {
                    "idx": idx,
                    "model": abbr,
                    "status": "pass" if passed else "fail",
                    "passed": passed,
                    "subject": subject,
                    "knowledge_node": knowledge,
                    "question_type": qtype,
                    "question": question,
                    "prediction": pred,
                    "gold": gold,
                    "raw_prediction": str(d.get("origin_prediction", pred)),
                    "options": options if isinstance(options, dict) else {},
                }
            )
    return rows


def render_opencompass_test_panel(payload: Dict[str, Any], key_prefix: str = "oc_test_panel") -> None:
    rows = _build_test_rows(payload)
    if not rows:
        st.info(t("opencompass_eval.test_no_data", default="暂无题目级评测明细（无法渲染测试面板）。"))
        return

    st.markdown(f"### {t('opencompass_eval.test_panel_title', default='Step 4 · Test（测试面板）')}")
    st.caption(
        t(
            "opencompass_eval.test_panel_desc",
            default="支持单模型查看逐题通过/失败，可按学科、知识节点、题型筛选。",
        )
    )

    df = pd.DataFrame(rows)
    summary_rows: List[Dict[str, Any]] = []
    for model_name, g in df.groupby("model"):
        total = int(len(g))
        ok = int(g["passed"].sum())
        fail = total - ok
        acc = (ok / total * 100.0) if total > 0 else 0.0
        summary_rows.append(
            {
                "model": model_name,
                "total": total,
                "pass": ok,
                "fail": fail,
                "accuracy": f"{acc:.2f}%",
                "status": "PASS" if fail == 0 else "FAIL",
            }
        )
    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, height=220)

    model_options = sorted(set(str(x) for x in df["model"].dropna().tolist()))
    selected_model = st.selectbox(
        t("opencompass_eval.filter_model", default="模型"),
        options=model_options,
        key=f"{key_prefix}_model",
    )
    df = df[df["model"] == selected_model].copy()

    c1, c2, c3, c4 = st.columns(4)
    subjects = [t("common.all", default="全部")] + sorted(set(str(x) for x in df["subject"].dropna().tolist()))
    knowledges = [t("common.all", default="全部")] + sorted(set(str(x) for x in df["knowledge_node"].dropna().tolist()))
    qtypes = [t("common.all", default="全部")] + sorted(set(str(x) for x in df["question_type"].dropna().tolist()))
    with c1:
        sel_subject = st.selectbox(t("opencompass_eval.filter_subject", default="学科"), subjects, key=f"{key_prefix}_subject")
    with c2:
        sel_knowledge = st.selectbox(
            t("opencompass_eval.filter_knowledge", default="知识节点"),
            knowledges,
            key=f"{key_prefix}_knowledge",
        )
    with c3:
        sel_qtype = st.selectbox(t("opencompass_eval.filter_qtype", default="题型"), qtypes, key=f"{key_prefix}_qtype")
    with c4:
        only_fail = st.checkbox(t("opencompass_eval.filter_only_fail", default="仅看失败"), value=False, key=f"{key_prefix}_only_fail")

    filtered = df.copy()
    all_opt = t("common.all", default="全部")
    if sel_subject != all_opt:
        filtered = filtered[filtered["subject"] == sel_subject]
    if sel_knowledge != all_opt:
        filtered = filtered[filtered["knowledge_node"] == sel_knowledge]
    if sel_qtype != all_opt:
        filtered = filtered[filtered["question_type"] == sel_qtype]
    if only_fail:
        filtered = filtered[~filtered["passed"]]

    show_df = filtered.copy()
    show_df["A"] = show_df["options"].map(lambda x: str((x or {}).get("A", "")) if isinstance(x, dict) else "")
    show_df["B"] = show_df["options"].map(lambda x: str((x or {}).get("B", "")) if isinstance(x, dict) else "")
    show_df["C"] = show_df["options"].map(lambda x: str((x or {}).get("C", "")) if isinstance(x, dict) else "")
    show_df["D"] = show_df["options"].map(lambda x: str((x or {}).get("D", "")) if isinstance(x, dict) else "")
    show_df = show_df[
        [
            "status",
            "subject",
            "knowledge_node",
            "question_type",
            "prediction",
            "gold",
            "question",
            "A",
            "B",
            "C",
            "D",
        ]
    ].copy()
    show_df["status"] = show_df["status"].map(lambda x: "✅ pass" if x == "pass" else "❌ fail")
    st.dataframe(show_df, use_container_width=True, height=320)
