from __future__ import annotations

import json
import random
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from proda.extractor import call_llm


PROMPT_DIR = Path(__file__).resolve().parent / "resources" / "Diagnosis"
PROMPT_CONCEPT_GAP = PROMPT_DIR / "concept_gap.txt"
PROMPT_CAPABILITY_DEFICIT = PROMPT_DIR / "capability_deficit.txt"


def _read_prompt(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


def _render_prompt(template: str, variables: Dict[str, str]) -> str:
    text = template
    for k, v in variables.items():
        text = text.replace("{" + k + "}", v)
    return text


def _extract_json_array(text: str) -> List[Dict[str, Any]]:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw).rstrip("`").strip()
    try:
        obj = json.loads(raw)
        if isinstance(obj, list):
            return [x for x in obj if isinstance(x, dict)]
        if isinstance(obj, dict):
            return [obj]
    except Exception:
        pass
    m = re.search(r"\[[\s\S]*\]", raw)
    if not m:
        return []
    try:
        obj = json.loads(m.group(0))
        if isinstance(obj, list):
            return [x for x in obj if isinstance(x, dict)]
    except Exception:
        return []
    return []


def _extract_embedded_options(question: str) -> Tuple[str, Dict[str, str]]:
    text = str(question or "").strip()
    if not text:
        return "", {}
    pattern = re.compile(
        r"(?:^|\n)\s*A[\.\):]\s*(?P<A>.+?)"
        r"(?:\n\s*B[\.\):]\s*(?P<B>.+?))"
        r"(?:\n\s*C[\.\):]\s*(?P<C>.+?))"
        r"(?:\n\s*D[\.\):]\s*(?P<D>.+?))"
        r"(?=\n\s*[A-Z][\.\):]|\Z)",
        re.S,
    )
    m = pattern.search(text)
    if not m:
        return text, {}
    stem = text[: m.start()].strip()
    options = {k: re.sub(r"\s+", " ", str(m.group(k) or "").strip()) for k in ["A", "B", "C", "D"]}
    if not all(options.values()):
        return text, {}
    return stem, options


def _split_answer_and_explanation(text: Any) -> Tuple[str, str]:
    raw = str(text or "").strip()
    if not raw:
        return "", ""
    parts = re.split(r"\n\s*\n", raw, maxsplit=1)
    if len(parts) == 1:
        return parts[0].strip(), ""
    return parts[0].strip(), parts[1].strip()


def _normalize_tf_answer(raw_answer: str) -> str:
    first = str(raw_answer or "").strip().upper()
    if not first:
        return ""
    first_token = first.splitlines()[0].strip()
    if first_token in {"A", "TRUE", "T", "YES", "Y"}:
        return "A"
    if first_token in {"B", "FALSE", "F", "NO", "N"}:
        return "B"
    if re.search(r"\bTRUE\b|\bYES\b", first):
        return "A"
    if re.search(r"\bFALSE\b|\bNO\b", first):
        return "B"
    if "A" in first and "B" not in first:
        return "A"
    if "B" in first and "A" not in first:
        return "B"
    return ""


def _normalize_choice(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    raw_question = str(item.get("question", "")).strip()
    question, embedded_options = _extract_embedded_options(raw_question)
    options = item.get("options", {})
    if isinstance(options, list):
        options = {
            "A": str(options[0]) if len(options) > 0 else "",
            "B": str(options[1]) if len(options) > 1 else "",
            "C": str(options[2]) if len(options) > 2 else "",
            "D": str(options[3]) if len(options) > 3 else "",
        }
    if not isinstance(options, dict):
        options = {}
    opt = {k: str(options.get(k, "")).strip() for k in ["A", "B", "C", "D"]}
    if not all(opt.values()) and embedded_options:
        opt = embedded_options
    if not question or not all(opt.values()):
        return None
    first_line, explanation = _split_answer_and_explanation(item.get("answer", ""))
    letters = re.findall(r"[A-D]", first_line.upper())
    uniq: List[str] = []
    for x in letters:
        if x not in uniq:
            uniq.append(x)
    if not uniq:
        return None
    answer = ",".join(sorted(uniq))
    qtype = "multiple_choice" if "," in answer else "single_choice"
    return {
        "question_type": qtype,
        "question": question,
        "options": opt,
        "answer": answer,
        "explanation": explanation,
    }


def _normalize_tf(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    question = str(item.get("question", "") or item.get("statement", "")).strip()
    if not question:
        return None
    first_line, explanation = _split_answer_and_explanation(item.get("answer", ""))
    ans = _normalize_tf_answer(first_line)
    if ans not in {"A", "B"}:
        return None
    raw_options = item.get("options", {})
    if isinstance(raw_options, list):
        raw_options = {
            "A": str(raw_options[0]) if len(raw_options) > 0 else "",
            "B": str(raw_options[1]) if len(raw_options) > 1 else "",
        }
    if not isinstance(raw_options, dict):
        raw_options = {}
    opt_a = str(raw_options.get("A", "")).strip() or "True"
    opt_b = str(raw_options.get("B", "")).strip() or "False"
    return {
        "question_type": "true_false",
        "question": question,
        "options": {"A": opt_a, "B": opt_b},
        "answer": ans,
        "explanation": explanation,
    }


def _normalize_qa(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    question = str(item.get("question", "")).strip()
    answer = str(item.get("answer", "")).strip()
    if item.get("options"):
        return None
    question_stem, embedded_options = _extract_embedded_options(question)
    if embedded_options:
        return None
    first_line, _ = _split_answer_and_explanation(answer)
    first = first_line.strip().upper()
    if first in {"A", "B", "A,B", "A,C", "A,D", "B,C", "B,D", "C,D", "A,B,C", "A,B,D", "A,C,D", "B,C,D", "A,B,C,D", "TRUE", "FALSE"}:
        return None
    lowered_q = question_stem.lower()
    if any(flag in lowered_q for flag in ["select all that apply", "which of the following", "true or false"]):
        return None
    if not question or not answer:
        return None
    return {
        "question_type": "qa",
        "question": question_stem or question,
        "answer": answer,
    }


def _extract_l2_ids(item: Dict[str, Any]) -> List[str]:
    values: List[str] = []
    for source in [item, item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {}]:
        if not isinstance(source, dict):
            continue
        for key in ["l2_ids", "l2_statement_ids"]:
            v = source.get(key, [])
            if isinstance(v, list):
                values.extend([str(x).strip() for x in v if str(x).strip()])
        one = source.get("l2_statement_id")
        if one:
            values.append(str(one).strip())
    uniq: List[str] = []
    for x in values:
        if x and x not in uniq:
            uniq.append(x)
    return uniq


def _build_prompt_variables(sample: Dict[str, Any], issue_type: str, max_questions: int) -> Dict[str, str]:
    diagnosis = sample.get("diagnosis", {}) if isinstance(sample.get("diagnosis"), dict) else {}
    concept = str(diagnosis.get("key_concept") or sample.get("subject") or "unknown_concept").strip()
    note = " | ".join(
        [
            str(diagnosis.get("reasoning", "")).strip(),
            str(diagnosis.get("recommendation", "")).strip(),
        ]
    ).strip(" |")
    if not note:
        note = "Model produced an incorrect answer and needs targeted remediation."

    knowledge_snippet = (
        f"Question: {sample.get('question', '')}\n"
        f"Correct: {sample.get('true_answer', '')}\n"
        f"Predicted: {sample.get('predicted_answer', '')}\n"
        f"Metadata: {json.dumps(sample.get('metadata', {}), ensure_ascii=False)}"
    )

    if issue_type == "concept_gap":
        return {
            "concept": concept,
            "l1_definition": str(diagnosis.get("reasoning", "")).strip() or str(sample.get("true_answer", "")),
            "l2_facts": knowledge_snippet,
            "examples": note,
            "max_questions": str(max_questions),
        }
    return {
        "concept": concept,
        "knowledge_snippet": knowledge_snippet,
        "diagnosis_note": note,
        "max_questions": str(max_questions),
    }


def _task_prefix(task_type: str, max_questions: int) -> str:
    if task_type == "qa":
        return (
            f"You must generate ONLY open-ended QA items.\n"
            f"Generate exactly {max_questions} QA items if possible.\n"
            "Do NOT generate multiple-choice questions.\n"
            "Do NOT generate true/false questions.\n"
            "Every item must contain only `question` and `answer`.\n\n"
        )
    if task_type == "choice":
        return (
            f"You must generate ONLY multiple-choice questions.\n"
            f"Generate exactly {max_questions} multiple-choice items if possible.\n"
            "Each item must include `question`, `options`, and `answer`.\n"
            "Do NOT output open-ended QA.\n"
            "Do NOT output true/false.\n"
            "The question stem must NOT inline the options; put all options inside the `options` object.\n"
            "The answer must contain the correct option letters, followed by a blank line, then a detailed explanation.\n\n"
        )
    return (
        f"You must generate ONLY true/false questions.\n"
        f"Generate exactly {max_questions} true/false items if possible.\n"
        "Each item must include `question`, `options`, and `answer`.\n"
        "Use options A=True and B=False.\n"
        "Do NOT output open-ended QA.\n"
        "Do NOT output multiple-choice with four options.\n"
        "The answer must contain True/False (or A/B), followed by a blank line, then a brief explanation.\n\n"
    )


def _generate_one_task(
    sample: Dict[str, Any],
    issue_type: str,
    task_type: str,
    max_questions: int,
    prompts: Dict[str, str],
    provider: str,
    model: str,
    api_key: str,
    api_base: str,
    max_tokens: int,
    retries: int,
) -> List[Dict[str, Any]]:
    template = prompts[issue_type]
    variables = _build_prompt_variables(sample, issue_type, max_questions)
    prompt = _task_prefix(task_type, max_questions) + _render_prompt(template, variables)

    last_error = ""
    max_questions = max(1, int(max_questions))
    collected: List[Dict[str, Any]] = []
    seen_keys = set()
    max_rounds = max(1, int(retries) + 1)
    for _ in range(max_rounds):
        try:
            text = call_llm(
                provider=provider,
                model=model,
                api_key=api_key,
                api_base=api_base,
                prompt=prompt,
                max_tokens=max_tokens,
            )
            data = _extract_json_array(text)
            for item in data:
                row: Optional[Dict[str, Any]]
                if task_type == "qa":
                    row = _normalize_qa(item)
                elif task_type == "choice":
                    row = _normalize_choice(item)
                else:
                    row = _normalize_tf(item)
                if row is None:
                    continue
                meta = sample.get("metadata", {}) if isinstance(sample.get("metadata"), dict) else {}
                row["source"] = "diagnosis_generated"
                row["issue_type"] = issue_type
                row["original_sample_index"] = str(sample.get("index", ""))
                row["metadata"] = {
                    "chain_id": meta.get("chain_id"),
                    "l2_ids": _extract_l2_ids(sample),
                    "l1_ids": list(meta.get("l1_ids", []) or []),
                    "CID": meta.get("CID"),
                    "domain": meta.get("domain") or sample.get("subject"),
                    "subject": sample.get("subject"),
                }
                dedup_key = (
                    str(row.get("question_type", "")),
                    str(row.get("question", "")).strip(),
                )
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)
                collected.append(row)
                if len(collected) >= max_questions:
                    return collected[:max_questions]
            last_error = "empty_rows"
        except Exception as exc:
            last_error = str(exc)
    if collected:
        return collected[:max_questions]
    return [{"_error": last_error, "issue_type": issue_type, "task_type": task_type}]


def generate_diagnostic_training_data(
    diagnostic_report: Dict[str, Any],
    provider: str,
    model: str,
    api_key: str,
    api_base: str,
    issue_windows: Dict[str, Dict[str, int]],
    max_error_samples: int = 200,
    max_workers: int = 6,
    max_tokens: int = 2048,
    retries: int = 2,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    prompts = {
        "concept_gap": _read_prompt(PROMPT_CONCEPT_GAP),
        "capability_deficit": _read_prompt(PROMPT_CAPABILITY_DEFICIT),
    }
    error_samples = list(diagnostic_report.get("error_samples", []) or [])
    error_samples = [x for x in error_samples if isinstance(x, dict) and str(x.get("issue_type", "")).strip()]
    if max_error_samples > 0:
        error_samples = error_samples[: int(max_error_samples)]

    tasks: List[Tuple[Dict[str, Any], str, str, int]] = []
    for sample in error_samples:
        issue_type = str(sample.get("issue_type", "")).strip()
        if issue_type not in {"concept_gap", "capability_deficit"}:
            continue
        cfg = issue_windows.get(issue_type, {})
        qa_n = max(0, int(cfg.get("qa", 0)))
        choice_n = max(0, int(cfg.get("choice", 0)))
        tf_n = max(0, int(cfg.get("tf", 0)))
        if qa_n > 0:
            tasks.append((sample, issue_type, "qa", qa_n))
        if choice_n > 0:
            tasks.append((sample, issue_type, "choice", choice_n))
        if tf_n > 0:
            tasks.append((sample, issue_type, "tf", tf_n))

    total = len(tasks)
    if progress_callback:
        progress_callback(0, max(1, total))

    generated: List[Dict[str, Any]] = []
    failed_tasks = 0
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, int(max_workers))) as ex:
        fut_map = {}
        for sample, issue_type, task_type, count in tasks:
            fut = ex.submit(
                _generate_one_task,
                sample,
                issue_type,
                task_type,
                count,
                prompts,
                provider,
                model,
                api_key,
                api_base,
                int(max_tokens),
                int(retries),
            )
            fut_map[fut] = (issue_type, task_type)
        for fut in as_completed(fut_map):
            rows = fut.result()
            if rows and isinstance(rows[0], dict) and "_error" in rows[0]:
                failed_tasks += 1
            else:
                generated.extend([x for x in rows if isinstance(x, dict)])
            done += 1
            if progress_callback:
                progress_callback(done, max(1, total))

    stats = {
        "error_samples_used": len(error_samples),
        "tasks_total": total,
        "tasks_failed": failed_tasks,
        "generated_rows": len(generated),
    }
    return generated, stats


def merge_diagnostic_with_original(
    diagnostic_rows: List[Dict[str, Any]],
    original_rows: List[Dict[str, Any]],
    target_total: int,
    diagnostic_ratio: float,
    mix_with_original: bool = True,
    exclude_same_l2: bool = True,
    fallback_random_if_insufficient: bool = True,
    random_seed: int = 42,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rng = random.Random(int(random_seed))
    diag_pool = [x for x in diagnostic_rows if isinstance(x, dict)]
    orig_pool = [x for x in original_rows if isinstance(x, dict)]
    rng.shuffle(diag_pool)
    rng.shuffle(orig_pool)

    target_total = max(0, int(target_total))
    diag_target = min(len(diag_pool), target_total if not mix_with_original else int(round(target_total * float(diagnostic_ratio))))
    diag_selected = diag_pool[:diag_target]

    if not mix_with_original:
        merged = diag_selected[:target_total]
        rng.shuffle(merged)
        return merged, {
            "target_total": target_total,
            "diagnostic_selected": len(merged),
            "original_selected": 0,
            "original_filtered_pool": 0,
            "fallback_used": 0,
        }

    orig_needed = max(0, target_total - len(diag_selected))
    diag_l2_ids = set()
    for row in diag_selected:
        diag_l2_ids.update(_extract_l2_ids(row))

    filtered_orig = orig_pool
    if exclude_same_l2 and diag_l2_ids:
        filtered_orig = []
        for row in orig_pool:
            row_l2 = set(_extract_l2_ids(row))
            if row_l2 and row_l2.intersection(diag_l2_ids):
                continue
            filtered_orig.append(row)

    orig_selected = filtered_orig[:orig_needed]
    fallback_used = 0
    if len(orig_selected) < orig_needed and fallback_random_if_insufficient:
        needed = orig_needed - len(orig_selected)
        used_ids = {id(x) for x in orig_selected}
        candidates = [x for x in orig_pool if id(x) not in used_ids]
        extra = candidates[:needed]
        fallback_used = len(extra)
        orig_selected.extend(extra)

    merged = list(diag_selected) + list(orig_selected)
    merged = merged[:target_total]
    rng.shuffle(merged)
    return merged, {
        "target_total": target_total,
        "diagnostic_selected": len(diag_selected),
        "original_selected": len(orig_selected),
        "original_filtered_pool": len(filtered_orig),
        "fallback_used": fallback_used,
    }

