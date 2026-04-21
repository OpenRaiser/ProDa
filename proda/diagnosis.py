from __future__ import annotations

import json
import random
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from proda.extractor import call_llm


PROMPT_PATH = Path(__file__).resolve().parent / "resources" / "Diagnosis" / "diagnostic_report.txt"


def _load_prompt() -> str:
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(f"Diagnosis prompt not found: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8")


def _render_prompt(template: str, variables: Dict[str, str]) -> str:
    rendered = template
    for k, v in variables.items():
        rendered = rendered.replace("{" + k + "}", v)
    return rendered


def _render_diagnostic_prompt(template: str, error_sample: Dict[str, Any]) -> str:
    metadata = error_sample.get("metadata", {}) if isinstance(error_sample.get("metadata"), dict) else {}
    replacement = {
        '{error_sample.get("question")}': str(error_sample.get("question", "")),
        "{error_sample.get('question')}": str(error_sample.get("question", "")),
        '{error_sample.get("true_answer")}': str(error_sample.get("true_answer", "")),
        "{error_sample.get('true_answer')}": str(error_sample.get("true_answer", "")),
        '{error_sample.get("predicted_answer")}': str(error_sample.get("predicted_answer", "")),
        "{error_sample.get('predicted_answer')}": str(error_sample.get("predicted_answer", "")),
        '{error_sample.get("question_type")}': str(error_sample.get("question_type", "")),
        "{error_sample.get('question_type')}": str(error_sample.get("question_type", "")),
        '{error_sample.get("subject")}': str(error_sample.get("subject", "")),
        "{error_sample.get('subject')}": str(error_sample.get("subject", "")),
        '{error_sample.get("metadata", {}).get("chain_id")}': str(metadata.get("chain_id", "")),
        "{error_sample.get('metadata', {}).get('chain_id')}": str(metadata.get("chain_id", "")),
    }
    rendered = str(template)
    for k, v in replacement.items():
        rendered = rendered.replace(k, v)
    return rendered


def _read_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def normalize_answer(text: Any) -> str:
    if text is None:
        return ""
    s = str(text).strip().upper().replace("，", ",")
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if len(parts) > 1:
        return ",".join(sorted(parts))
    return parts[0] if parts else s


def infer_question_type(answer: Any, options: Any) -> str:
    if not options:
        return "open_ended"
    answer_s = str(answer or "").strip().upper()
    if "," in answer_s:
        return "multiple_choice"
    if answer_s in {"A", "B"} and isinstance(options, dict) and len(options) == 2:
        a = str(options.get("A", "")).strip().lower()
        b = str(options.get("B", "")).strip().lower()
        if a in {"true", "correct"} and b in {"false", "incorrect"}:
            return "true_false"
    return "single_choice"


def parse_json_response(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw)
        raw = raw.rstrip("`").strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _build_error_samples(
    eval_payload: Dict[str, Any],
    model_abbr: str,
) -> Dict[str, Any]:
    benchmark_path = Path(str(eval_payload.get("benchmark_json", "")))
    benchmark_data = _read_json(benchmark_path, [])
    if not isinstance(benchmark_data, list):
        benchmark_data = []

    question_map: Dict[str, Dict[str, Any]] = {}
    for item in benchmark_data:
        if not isinstance(item, dict):
            continue
        q = str(item.get("question", "")).strip()
        if q:
            question_map[q] = item

    result = eval_payload.get("result", {}) or {}
    run_dir = Path(str(result.get("run_dir", "")))
    model_result_path = run_dir / "results" / str(model_abbr) / "proda_bench.json"
    model_result = _read_json(model_result_path, {})
    details = model_result.get("details", {}) if isinstance(model_result, dict) else {}
    if not isinstance(details, dict):
        details = {}

    error_samples: List[Dict[str, Any]] = []
    subject_metrics: Dict[str, Dict[str, Any]] = {}
    by_question_type = defaultdict(int)
    by_subject = defaultdict(int)

    total_samples = 0
    total_correct = 0
    subject_total = defaultdict(int)
    subject_correct = defaultdict(int)

    for idx_key, entry in details.items():
        if idx_key == "type" or not isinstance(entry, dict):
            continue

        question = str(entry.get("question", "")).strip()
        if not question:
            continue

        try:
            idx = int(idx_key)
        except Exception:
            idx = -1

        bench_info: Dict[str, Any] = {}
        if 0 <= idx < len(benchmark_data) and isinstance(benchmark_data[idx], dict):
            bench_info = benchmark_data[idx]
        if not bench_info:
            bench_info = question_map.get(question, {})

        prediction = entry.get("predictions") or entry.get("prediction") or entry.get("origin_prediction", "")
        reference = entry.get("references") or entry.get("reference") or entry.get("gold", bench_info.get("answer", ""))
        pred_norm = normalize_answer(prediction)
        ref_norm = normalize_answer(reference)

        subject = str(bench_info.get("domain_context") or bench_info.get("subject") or "unknown").strip()
        question_type = infer_question_type(bench_info.get("answer", reference), bench_info.get("options", {}))

        subject_total[subject] += 1
        total_samples += 1
        is_correct = bool(pred_norm and ref_norm and pred_norm == ref_norm)
        if is_correct:
            total_correct += 1
            subject_correct[subject] += 1
            continue

        sample = {
            "index": str(idx_key),
            "subject": subject,
            "question": question,
            "true_answer": str(reference),
            "predicted_answer": str(prediction),
            "question_type": question_type,
            "issue_type": "unknown",
            "metadata": {
                "chain_id": bench_info.get("chain_id"),
                "l2_ids": list(bench_info.get("l2_ids", []) or [])[:3],
                "l1_ids": list(bench_info.get("l1_ids", []) or [])[:3],
                "CID": bench_info.get("CID"),
                "domain": bench_info.get("domain") or subject,
            },
        }
        error_samples.append(sample)
        by_question_type[question_type] += 1
        by_subject[subject] += 1

    for subject, cnt in subject_total.items():
        corr = int(subject_correct.get(subject, 0))
        acc = (corr / cnt * 100.0) if cnt else 0.0
        subject_metrics[subject] = {
            "accuracy": round(acc, 2),
            "total": int(cnt),
            "correct": int(corr),
            "error": int(cnt - corr),
        }

    accuracy = (total_correct / total_samples) if total_samples else 0.0
    return {
        "error_samples": error_samples,
        "subject_metrics": subject_metrics,
        "by_question_type": dict(by_question_type),
        "by_subject": dict(by_subject),
        "total_samples": int(total_samples),
        "correct_samples": int(total_correct),
        "accuracy": round(float(accuracy), 4),
        "result_path": str(model_result_path),
    }


def _diagnose_one(
    sample: Dict[str, Any],
    prompt_template: str,
    provider: str,
    model: str,
    api_key: str,
    api_base: str,
    temperature: float,
    max_tokens: int,
    retries: int,
) -> Dict[str, Any]:
    last_error = ""
    payload_text = _render_diagnostic_prompt(prompt_template, sample)
    for attempt in range(max(0, retries) + 1):
        try:
            text = call_llm(
                provider=provider,
                model=model,
                api_key=api_key,
                api_base=api_base,
                prompt=payload_text,
                max_tokens=max_tokens,
            )
            obj = parse_json_response(text)
            if isinstance(obj, dict) and obj:
                return obj
            last_error = "empty_json"
        except Exception as exc:
            last_error = str(exc)
        if attempt < retries:
            sleep_s = min(10.0, 1.0 * (2**attempt)) + random.uniform(0, 0.5)
            time.sleep(sleep_s)
    return {"_error": last_error}


def generate_recommendations(report: Dict[str, Any]) -> List[str]:
    recs: List[str] = []
    by_issue = report.get("llm_diagnosis_issue_distribution", {}) or {}
    total_err = int(report.get("error_samples_count", 0))
    if by_issue and total_err > 0:
        top_issue, top_cnt = sorted(by_issue.items(), key=lambda x: x[1], reverse=True)[0]
        ratio = float(top_cnt) / float(total_err)
        if top_issue == "concept_gap":
            recs.append(
                f"[Main Issue] concept_gap {top_cnt}/{total_err} ({ratio*100:.1f}%). "
                "Add more concept-disambiguation samples, boundary-definition examples, and confusing-pair contrasts."
            )
        elif top_issue == "capability_deficit":
            recs.append(
                f"[Main Issue] capability_deficit {top_cnt}/{total_err} ({ratio*100:.1f}%). "
                "Add more multi-step reasoning samples, process decomposition examples, and error-chain repair cases."
            )
    by_subject = report.get("error_patterns", {}).get("by_subject", {}) or {}
    if by_subject:
        worst = sorted(by_subject.items(), key=lambda x: x[1], reverse=True)[:3]
        recs.append("Priority subjects to fix: " + ", ".join([f"{k}({v})" for k, v in worst]))
    acc = float(report.get("accuracy", 0.0))
    if acc < 0.70:
        recs.append("Overall accuracy is low; prioritize high-coverage iterative data augmentation first.")
    elif acc < 0.85:
        recs.append("Overall accuracy is moderate; run targeted iterative augmentation based on error distribution.")
    else:
        recs.append("Overall accuracy is relatively high; use small-scale targeted augmentation plus validation.")
    return recs


def generate_diagnostic_report(
    eval_payload: Dict[str, Any],
    target_model_abbr: str,
    provider: str,
    model: str,
    api_key: str,
    api_base: str,
    max_diagnose: int = 0,
    max_workers: int = 8,
    temperature: float = 0.2,
    max_tokens: int = 1024,
    retries: int = 3,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Dict[str, Any]:
    if not api_key.strip():
        raise ValueError("API key is empty")
    if not model.strip():
        raise ValueError("Diagnosis model is empty")

    prompt_template = _load_prompt()
    base = _build_error_samples(eval_payload, target_model_abbr)
    error_samples = list(base.get("error_samples", []))

    samples_to_diagnose = error_samples if int(max_diagnose) == 0 else error_samples[: int(max_diagnose)]
    total = len(samples_to_diagnose)
    diagnosed: List[Dict[str, Any]] = [None] * total  # type: ignore
    by_issue = defaultdict(int)

    if progress_callback:
        progress_callback(0, max(1, total))

    workers = max(1, min(int(max_workers), max(1, total)))
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        future_map = {}
        for i, sample in enumerate(samples_to_diagnose):
            future = ex.submit(
                _diagnose_one,
                sample,
                prompt_template,
                provider,
                model,
                api_key,
                api_base,
                float(temperature),
                int(max_tokens),
                int(retries),
            )
            future_map[future] = i

        for future in as_completed(future_map):
            i = future_map[future]
            sample = dict(samples_to_diagnose[i])
            try:
                diagnosis = future.result()
            except Exception as exc:
                diagnosis = {"_error": str(exc)}
            sample["diagnosis"] = diagnosis if isinstance(diagnosis, dict) and "_error" not in diagnosis else {}
            issue_type = str(sample["diagnosis"].get("issue_type", "unknown")).strip() if isinstance(sample["diagnosis"], dict) else "unknown"
            if issue_type not in {"concept_gap", "capability_deficit"}:
                issue_type = "unknown"
            sample["issue_type"] = issue_type
            by_issue[issue_type] += 1
            diagnosed[i] = sample
            done += 1
            if progress_callback:
                progress_callback(done, max(1, total))

    diagnosed_samples = [x for x in diagnosed if isinstance(x, dict)]
    report = {
        "model_name": str(target_model_abbr),
        "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "total_samples": int(base.get("total_samples", 0)),
        "correct_samples": int(base.get("correct_samples", 0)),
        "error_samples_count": int(len(error_samples)),
        "accuracy": float(base.get("accuracy", 0.0)),
        "subject_metrics": dict(base.get("subject_metrics", {})),
        "error_patterns": {
            "by_question_type": dict(base.get("by_question_type", {})),
            "by_issue_type": dict(by_issue),
            "by_subject": dict(base.get("by_subject", {})),
        },
        "error_samples": diagnosed_samples,
        "diagnosed_samples": diagnosed_samples,
        "llm_diagnosis_issue_distribution": dict(by_issue),
    }
    report["recommendations"] = generate_recommendations(report)
    return report

