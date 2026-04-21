from __future__ import annotations

import json
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Event
from typing import Any, Dict, List, Tuple

from proda.extractor import call_llm


PROMPT_DIR = Path(__file__).resolve().parent / "resources" / "FineTune"
PROMPT_QA = PROMPT_DIR / "FineTune_QA.txt"
PROMPT_CHOICE = PROMPT_DIR / "FineTune_Choice.txt"
PROMPT_TF = PROMPT_DIR / "FineTune_TF.txt"


def _read_prompt(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


def _render_prompt(template: str, variables: Dict[str, str]) -> str:
    text = template
    for k, v in variables.items():
        text = text.replace("{" + k + "}", v)
    return text


def _extract_json(text: str) -> Any:
    cleaned = re.sub(r"```json\s*", "", text)
    cleaned = re.sub(r"```\s*", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    s = cleaned.find("[")
    e = cleaned.rfind("]")
    if s != -1 and e != -1 and e > s:
        try:
            return json.loads(cleaned[s : e + 1])
        except Exception:
            pass
    s = cleaned.find("{")
    e = cleaned.rfind("}")
    if s != -1 and e != -1 and e > s:
        try:
            return json.loads(cleaned[s : e + 1])
        except Exception:
            pass
    return []


def _normalize_qa(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for x in items:
        q = str(x.get("question", "")).strip()
        a = str(x.get("answer", "")).strip()
        if q and a:
            out.append(
                {
                    "question_type": "qa",
                    "question": q,
                    "answer": a,
                    "l2_statement_id": x.get("l2_statement_id", ""),
                    "linked_concepts": x.get("linked_concepts", []),
                    "meta_style": x.get("question_style", ""),
                }
            )
    return out


def _normalize_choice(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for x in items:
        q = str(x.get("question", "")).strip()
        opts = x.get("options", [])
        if isinstance(opts, dict):
            opts = [opts.get("A", ""), opts.get("B", ""), opts.get("C", ""), opts.get("D", "")]
        opts = [str(o).strip() for o in opts][:4]
        if len(opts) < 4:
            continue
        ans = x.get("answer", "")
        if isinstance(ans, list):
            ans = ",".join([str(i).strip().upper() for i in ans if str(i).strip()])
        ans = str(ans).replace(" ", "").upper()
        if not q or not ans:
            continue
        out.append(
            {
                "question_type": str(x.get("question_type", "single_choice")),
                "question": q,
                "options": opts,
                "answer": ans,
                "explanation": str(x.get("explanation", "")).strip(),
                "l2_statement_ids": x.get("l2_statement_ids", []),
                "linked_concepts": x.get("linked_concepts", []),
            }
        )
    return out


def _normalize_tf(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for x in items:
        s = str(x.get("statement", "")).strip()
        a = str(x.get("answer", "")).strip().lower()
        if a in {"true", "t", "yes"}:
            a = "true"
        elif a in {"false", "f", "no"}:
            a = "false"
        else:
            continue
        if s:
            out.append(
                {
                    "question_type": "true_false",
                    "question": s,
                    "answer": a,
                    "explanation": str(x.get("reasoning", "")).strip(),
                    "l2_statement_id": x.get("l2_statement_id", ""),
                    "linked_concepts": x.get("linked_concepts", []),
                }
            )
    return out


def _as_id_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if "," in text:
            return [x.strip() for x in text.split(",") if x.strip()]
        return [text]
    return [str(value).strip()]


def _compact_l1_entries(l1_subset: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    compacted = []
    for item in l1_subset:
        compacted.append(
            {
                "concept_id": item.get("concept_id"),
                "term": item.get("term"),
                "definition": item.get("definition"),
                "parent_statement_ids": _as_id_list(
                    item.get("parent_statement_ids")
                    or item.get("supporting_statement_ids")
                    or item.get("statement_ids")
                    or item.get("related_statement_ids")
                    or item.get("parent_l2_ids")
                ),
            }
        )
    return compacted


def _select_related_l1(
    l1_list: List[Dict[str, Any]],
    l2_batch: List[Dict[str, Any]],
    topn: int,
) -> List[Dict[str, Any]]:
    if not l1_list or topn <= 0:
        return []

    l2_ids = {str(x.get("statement_id", "")).strip() for x in l2_batch if str(x.get("statement_id", "")).strip()}
    l2_text = " ".join(
        f"{x.get('subject', '')} {x.get('predicate', '')} {x.get('object', '')}".lower()
        for x in l2_batch
    )

    matched: List[Dict[str, Any]] = []
    for item in l1_list:
        parent_ids = _as_id_list(
            item.get("parent_statement_ids")
            or item.get("supporting_statement_ids")
            or item.get("statement_ids")
            or item.get("related_statement_ids")
            or item.get("parent_l2_ids")
        )
        if parent_ids and l2_ids and set(parent_ids).intersection(l2_ids):
            matched.append(item)
            continue

        term = str(item.get("term", "")).strip().lower()
        if term and term in l2_text:
            matched.append(item)

    if len(matched) < topn:
        remain = [x for x in l1_list if x not in matched]
        if remain:
            matched.extend(random.sample(remain, min(topn - len(matched), len(remain))))
    return matched[:topn]


class L2WindowSampler:
    def __init__(self, l2_list: List[Dict[str, Any]], allow_reuse: bool) -> None:
        self._data = list(l2_list)
        self._allow_reuse = allow_reuse
        self._idx = 0
        random.shuffle(self._data)

    def next_batch(self, window_size: int) -> List[Dict[str, Any]]:
        if not self._data:
            return []
        window_size = max(1, int(window_size))
        out: List[Dict[str, Any]] = []
        while len(out) < window_size:
            if self._idx >= len(self._data):
                if not self._allow_reuse:
                    break
                random.shuffle(self._data)
                self._idx = 0
            out.append(self._data[self._idx])
            self._idx += 1
        return out


def _run_task(
    task_name: str,
    prompt_template: str,
    provider: str,
    model: str,
    api_key: str,
    api_base: str,
    variables: Dict[str, str],
    retries: int,
    cancel_event: Event | None = None,
) -> Tuple[List[Dict[str, Any]], bool]:
    if cancel_event is not None and cancel_event.is_set():
        return [], False
    prompt = _render_prompt(prompt_template, variables)
    for i in range(retries + 1):
        if cancel_event is not None and cancel_event.is_set():
            return [], False
        try:
            raw = call_llm(provider, model, api_key, api_base, prompt, max_tokens=4096)
            data = _extract_json(raw)
            if isinstance(data, dict):
                data = [data]
            if not isinstance(data, list):
                data = []
            if task_name == "qa":
                rows = _normalize_qa([x for x in data if isinstance(x, dict)])
                return rows, bool(rows)
            if task_name == "choice":
                rows = _normalize_choice([x for x in data if isinstance(x, dict)])
                return rows, bool(rows)
            rows = _normalize_tf([x for x in data if isinstance(x, dict)])
            return rows, bool(rows)
        except Exception:
            if i < retries:
                time.sleep(min(8.0, 1.5 * (2**i)))
    return [], False


def _adapt_workers(current: int, ceiling: int, fail_rate: float, healthy_streak: int) -> Tuple[int, int, bool]:
    new_workers = current
    changed = False
    if fail_rate >= 0.30:
        new_workers = max(1, current // 2)
        healthy_streak = 0
    elif fail_rate >= 0.15:
        new_workers = max(1, current - 1)
        healthy_streak = 0
    elif fail_rate <= 0.03:
        healthy_streak += 1
        if healthy_streak >= 2 and current < ceiling:
            new_workers = min(ceiling, current + 1)
            healthy_streak = 0
    else:
        healthy_streak = 0
    if new_workers != current:
        changed = True
    return new_workers, healthy_streak, changed


def generate_finetune_data(
    knowledge_core: Dict[str, Any],
    provider: str,
    model: str,
    api_key: str,
    api_base: str,
    total_samples: int = 300,
    qa_ratio: float = 0.6,
    choice_ratio: float = 0.3,
    single_choice_ratio: float = 0.7,
    true_ratio: float = 0.6,
    author_notes: str = "",
    max_workers: int = 3,
    retries: int = 2,
    max_refill_rounds: int = 4,
    adaptive_concurrency: bool = True,
    batch_size: int = 8,
    l2_window_size: int = 8,
    l1_topn: int = 20,
    allow_l2_reuse_after_exhausted: bool = True,
    l1_compact: bool = True,
    progress_callback=None,
    cancel_event: Event | None = None,
) -> List[Dict[str, Any]]:
    l2 = knowledge_core.get("l2_statements", [])
    l1 = knowledge_core.get("l1_concepts", [])

    qa_target = max(1, int(total_samples * qa_ratio))
    choice_target = max(1, int(total_samples * choice_ratio))
    tf_target = max(1, total_samples - qa_target - choice_target)

    templates = {
        "qa": _read_prompt(PROMPT_QA),
        "choice": _read_prompt(PROMPT_CHOICE),
        "tf": _read_prompt(PROMPT_TF),
    }

    merged: Dict[str, List[Dict[str, Any]]] = {"qa": [], "choice": [], "tf": []}
    target_map = {"qa": qa_target, "choice": choice_target, "tf": tf_target}
    stats = {
        "submitted": 0,
        "succeeded_jobs": 0,
        "failed_jobs": 0,
        "refill_rounds": 0,
        "target_total": total_samples,
        "adaptive_enabled": bool(adaptive_concurrency),
        "initial_workers": int(max_workers),
        "min_workers": int(max_workers),
        "max_workers_seen": int(max_workers),
        "final_workers": int(max_workers),
        "worker_adjustments": 0,
        "batch_size": int(batch_size),
        "l2_window_size": int(l2_window_size),
        "l1_topn": int(l1_topn),
        "empty_windows": 0,
    }
    current_workers = max(1, int(max_workers))
    healthy_streak = 0
    total_planned = 0
    done = 0

    samplers = {
        "qa": L2WindowSampler(l2, allow_l2_reuse_after_exhausted),
        "choice": L2WindowSampler(l2, allow_l2_reuse_after_exhausted),
        "tf": L2WindowSampler(l2, allow_l2_reuse_after_exhausted),
    }

    def build_jobs(task_name: str, total_target: int) -> List[Tuple[str, Dict[str, str]]]:
        jobs: List[Tuple[str, Dict[str, str]]] = []
        remain = max(0, int(total_target))
        while remain > 0:
            batch = min(max(1, int(batch_size)), remain)
            l2_batch = samplers[task_name].next_batch(l2_window_size)
            if not l2_batch:
                stats["empty_windows"] += 1
                break
            l1_subset = _select_related_l1(l1, l2_batch, l1_topn)
            if l1_compact:
                l1_subset = _compact_l1_entries(l1_subset)

            vars_map = {
                "L2_STATEMENTS": json.dumps(l2_batch, ensure_ascii=False, separators=(",", ":")),
                "L1_CONCEPTS": json.dumps(l1_subset, ensure_ascii=False, separators=(",", ":")),
                "AUTHOR_NOTES": author_notes or "None",
                "MAX_QUESTIONS": str(batch),
            }
            if task_name == "choice":
                vars_map["SINGLE_CHOICE_RATIO"] = str(int(single_choice_ratio * 100))
            if task_name == "tf":
                vars_map["TRUE_RATIO"] = str(int(true_ratio * 100))
            jobs.append((task_name, vars_map))
            remain -= batch
        return jobs

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for round_idx in range(max(1, int(max_refill_rounds))):
            if cancel_event is not None and cancel_event.is_set():
                break
            deficits = {
                task: max(0, target_map[task] - len(merged[task]))
                for task in ["qa", "choice", "tf"]
            }
            if not any(deficits.values()):
                break
            if round_idx > 0:
                stats["refill_rounds"] += 1

            jobs: List[Tuple[str, Dict[str, str]]] = []
            for task_name, need in deficits.items():
                jobs.extend(build_jobs(task_name, need))
            if not jobs:
                break
            total_planned += len(jobs)

            ptr = 0
            while ptr < len(jobs):
                if cancel_event is not None and cancel_event.is_set():
                    break
                window = jobs[ptr : ptr + max(1, current_workers)]
                ptr += len(window)

                future_map = {}
                for task_name, vars_map in window:
                    if cancel_event is not None and cancel_event.is_set():
                        break
                    future = ex.submit(
                        _run_task,
                        task_name,
                        templates[task_name],
                        provider,
                        model,
                        api_key,
                        api_base,
                        vars_map,
                        retries,
                        cancel_event,
                    )
                    future_map[future] = task_name
                    stats["submitted"] += 1

                window_fail = 0
                for future in as_completed(future_map):
                    if cancel_event is not None and cancel_event.is_set():
                        break
                    task_name = future_map[future]
                    rows, ok = future.result()
                    merged[task_name].extend(rows)
                    if ok:
                        stats["succeeded_jobs"] += 1
                    else:
                        stats["failed_jobs"] += 1
                        window_fail += 1
                    done += 1
                    if progress_callback:
                        progress_callback(done, total_planned)

                fail_rate = window_fail / max(1, len(window))
                if adaptive_concurrency:
                    new_workers, healthy_streak, changed = _adapt_workers(
                        current_workers, int(max_workers), fail_rate, healthy_streak
                    )
                    if changed:
                        stats["worker_adjustments"] += 1
                    current_workers = new_workers
                    stats["min_workers"] = min(stats["min_workers"], current_workers)
                    stats["max_workers_seen"] = max(stats["max_workers_seen"], current_workers)

                if fail_rate > 0.25:
                    time.sleep(min(6.0, 1.5 + round_idx))
            if cancel_event is not None and cancel_event.is_set():
                break

    results = (
        merged["qa"][:qa_target]
        + merged["choice"][:choice_target]
        + merged["tf"][:tf_target]
    )
    stats["generated_total"] = len(results)
    stats["final_workers"] = current_workers
    stats["cancelled"] = bool(cancel_event is not None and cancel_event.is_set())
    generate_finetune_data.last_run_stats = stats
    return results

