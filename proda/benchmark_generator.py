from __future__ import annotations

import json
import re
import time
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Event
from typing import Any, Dict, List, Optional, Tuple

from proda.extractor import call_llm


PROMPT_PATH = Path(__file__).resolve().parent / "resources" / "Benchmark" / "extract_mcq_prompt_multi.txt"


def load_prompt() -> str:
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(f"Benchmark prompt not found: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8")


def format_reasoning_chain_input(chain: Dict[str, Any]) -> str:
    parts: List[str] = []
    if chain.get("chain_id"):
        parts.append(f"Chain ID: {chain['chain_id']}")
    if chain.get("domain_context"):
        parts.append(f"Domain: {chain['domain_context']}")
    if chain.get("process_name"):
        parts.append(f"Process: {chain['process_name']}")
    if chain.get("narrative_summary"):
        parts.append(f"\nSummary:\n{chain['narrative_summary']}")
    if chain.get("preconditions"):
        parts.append("\nPreconditions:")
        for i, x in enumerate(chain.get("preconditions", []), start=1):
            parts.append(f"  {i}. {x}")
    if chain.get("negative_constraints"):
        parts.append("\nNegative Constraints:")
        for i, x in enumerate(chain.get("negative_constraints", []), start=1):
            parts.append(f"  {i}. {x}")
    if chain.get("steps"):
        parts.append("\nReasoning Steps:")
        for i, step in enumerate(chain.get("steps", []), start=1):
            parts.append(f"  Step {i}: {step}")
    return "\n".join(parts)


def extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    cleaned = re.sub(r"```json\s*", "", text)
    cleaned = re.sub(r"```\s*", "", cleaned).strip()
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    start = cleaned.find("{")
    if start < 0:
        return None
    depth = 0
    end = -1
    for i in range(start, len(cleaned)):
        if cleaned[i] == "{":
            depth += 1
        elif cleaned[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        return None
    try:
        data = json.loads(cleaned[start : end + 1])
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def validate_mcq(item: Dict[str, Any]) -> bool:
    if not isinstance(item, dict):
        return False
    for k in ["question", "options", "answer"]:
        if k not in item:
            return False
    if not isinstance(item["options"], dict):
        return False
    expected = {"A", "B", "C", "D"}
    if set(item["options"].keys()) != expected:
        return False
    answer = str(item["answer"]).replace(" ", "").upper()
    opts = [x for x in answer.split(",") if x]
    if len(opts) < 1 or len(opts) > 4:
        return False
    if len(opts) != len(set(opts)):
        return False
    for x in opts:
        if x not in expected:
            return False
    return True


def _build_single_prompt(prompt_template: str, chain: Dict[str, Any], variation_tag: str) -> str:
    chain_input = format_reasoning_chain_input(chain)
    return (
        f"{prompt_template}\n\n"
        f"Input Reasoning Chain:\n{chain_input}\n\n"
        "Additional requirement:\n"
        f"- Generate a UNIQUE question variant for this chain.\n"
        f"- Variation tag: {variation_tag}\n\n"
        "Output:"
    )


def _mcq_key(item: Dict[str, Any]) -> str:
    question = str(item.get("question", "")).strip().lower()
    answer = str(item.get("answer", "")).replace(" ", "").upper()
    options = item.get("options", {}) or {}
    if isinstance(options, dict):
        opt_text = "|".join(str(options.get(k, "")).strip().lower() for k in ["A", "B", "C", "D"])
    else:
        opt_text = str(options).strip().lower()
    return f"{question}::{answer}::{opt_text}"


def _normalize_semantic_text(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _token_jaccard(a: str, b: str) -> float:
    sa = set(a.split())
    sb = set(b.split())
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / max(1, len(sa | sb))


def _is_semantic_duplicate(candidate: Dict[str, Any], existing: List[Dict[str, Any]]) -> bool:
    cq = _normalize_semantic_text(str(candidate.get("question", "")))
    if not cq:
        return True
    for item in existing:
        eq = _normalize_semantic_text(str(item.get("question", "")))
        if not eq:
            continue
        ratio = SequenceMatcher(None, cq, eq).ratio()
        jac = _token_jaccard(cq, eq)
        # Strongly similar wording OR very high token overlap.
        if ratio >= 0.92 or jac >= 0.88:
            return True
        # Moderate wording similarity + high token overlap.
        if ratio >= 0.82 and jac >= 0.75:
            return True
    return False


def _process_one_chain(
    chain: Dict[str, Any],
    provider: str,
    model: str,
    api_key: str,
    api_base: str,
    prompt_template: str,
    max_tokens: int,
    temperature: float,
    retries: int,
    variation_tag: str,
    cancel_event: Optional[Event] = None,
) -> Tuple[Optional[Dict[str, Any]], str]:
    if cancel_event is not None and cancel_event.is_set():
        return None, "cancelled"
    full_prompt = _build_single_prompt(prompt_template, chain, variation_tag)
    for i in range(retries + 1):
        if cancel_event is not None and cancel_event.is_set():
            return None, "cancelled"
        try:
            text = call_llm(provider, model, api_key, api_base, full_prompt, max_tokens=max_tokens)
            parsed = extract_json_object(text)
            if parsed and validate_mcq(parsed):
                parsed["chain_id"] = chain.get("chain_id", "")
                parsed["domain_context"] = chain.get("domain_context", "")
                parsed["process_name"] = chain.get("process_name", "")
                return parsed, "ok"
        except Exception as exc:
            msg = str(exc).lower()
            if i < retries:
                sleep_s = min(8.0, 1.5 * (2**i))
                if "rate limit" in msg or "too many requests" in msg or "429" in msg:
                    sleep_s = min(20.0, sleep_s + 2.0)
                time.sleep(sleep_s)
            continue
        if i < retries:
            time.sleep(1.0 * (i + 1))
    return None, "invalid_or_exception"


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


def generate_benchmark_mcq(
    l3_chains: List[Dict[str, Any]],
    provider: str,
    model: str,
    api_key: str,
    api_base: str,
    max_workers: int = 4,
    questions_per_chain: int = 5,
    max_tokens: int = 4096,
    temperature: float = 0.3,
    retries: int = 2,
    max_refill_rounds: int = 4,
    adaptive_concurrency: bool = True,
    existing_mcqs: Optional[List[Dict[str, Any]]] = None,
    progress_callback=None,
    cancel_event: Optional[Event] = None,
) -> List[Dict[str, Any]]:
    prompt_template = load_prompt()
    if not l3_chains:
        return []
    questions_per_chain = max(1, int(questions_per_chain))
    total_planned = len(l3_chains) * questions_per_chain
    outputs_by_chain: Dict[int, List[Dict[str, Any]]] = {i: [] for i in range(len(l3_chains))}
    done = 0
    stats = {
        "submitted": 0,
        "succeeded": 0,
        "failed": 0,
        "duplicates_dropped": 0,
        "semantic_dedup_dropped": 0,
        "refill_rounds": 0,
        "adaptive_enabled": bool(adaptive_concurrency),
        "initial_workers": int(max_workers),
        "min_workers": int(max_workers),
        "max_workers_seen": int(max_workers),
        "final_workers": int(max_workers),
        "worker_adjustments": 0,
    }
    current_workers = max(1, int(max_workers))
    healthy_streak = 0

    # Build chain_id → chain_idx mapping (used for resume pre-population)
    chain_id_to_idx: Dict[str, int] = {
        str(c.get("chain_id", "")): i
        for i, c in enumerate(l3_chains)
        if c.get("chain_id")
    }

    # seen_keys must be initialised before the executor so resume can pre-populate it
    seen_keys: Dict[int, set] = {i: set() for i in range(len(l3_chains))}

    # --- Resume: restore already-accepted MCQs from a previous run ---
    if existing_mcqs:
        for mcq in existing_mcqs:
            cid = str(mcq.get("chain_id", ""))
            chain_idx = chain_id_to_idx.get(cid)
            if chain_idx is None:
                continue  # chain no longer exists after re-extraction
            if len(outputs_by_chain[chain_idx]) >= questions_per_chain:
                continue  # chain already full (e.g. lower qpc requested)
            outputs_by_chain[chain_idx].append(mcq)
            seen_keys[chain_idx].add(_mcq_key(mcq))
            done += 1
        if progress_callback and done > 0:
            progress_callback(done, total_planned)
    # ------------------------------------------------------------------

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for round_idx in range(max(1, int(max_refill_rounds))):
            if cancel_event is not None and cancel_event.is_set():
                break
            deficits: Dict[int, int] = {}
            for chain_idx in range(len(l3_chains)):
                need = questions_per_chain - len(outputs_by_chain[chain_idx])
                if need > 0:
                    deficits[chain_idx] = need
            if not deficits:
                break
            if round_idx > 0:
                stats["refill_rounds"] += 1

            # total_planned stays fixed at len(l3_chains)*questions_per_chain;
            # we do NOT inflate it with refill deficits — that caused the
            # progress bar to jump backwards every refill round.

            pending_chain_indices: List[int] = []
            for chain_idx, need in deficits.items():
                pending_chain_indices.extend([chain_idx] * need)

            ptr = 0
            while ptr < len(pending_chain_indices):
                if cancel_event is not None and cancel_event.is_set():
                    break
                window = pending_chain_indices[ptr : ptr + max(1, current_workers)]
                ptr += len(window)

                future_map = {}
                for chain_idx in window:
                    if cancel_event is not None and cancel_event.is_set():
                        break
                    chain = l3_chains[chain_idx]
                    variation_tag = f"r{round_idx+1}-w{ptr}-c{chain_idx}-t{time.time_ns()%1000000}"
                    future = ex.submit(
                        _process_one_chain,
                        chain,
                        provider,
                        model,
                        api_key,
                        api_base,
                        prompt_template,
                        max_tokens,
                        temperature,
                        retries,
                        variation_tag,
                        cancel_event,
                    )
                    future_map[future] = chain_idx
                    stats["submitted"] += 1

                window_fail = 0
                for future in as_completed(future_map):
                    if cancel_event is not None and cancel_event.is_set():
                        break
                    chain_idx = future_map[future]
                    result, _ = future.result()
                    if result:
                        key = _mcq_key(result)
                        if key in seen_keys[chain_idx]:
                            stats["duplicates_dropped"] += 1
                            stats["failed"] += 1
                            window_fail += 1
                        elif _is_semantic_duplicate(result, outputs_by_chain[chain_idx]):
                            stats["semantic_dedup_dropped"] += 1
                            stats["failed"] += 1
                            window_fail += 1
                        else:
                            seen_keys[chain_idx].add(key)
                            outputs_by_chain[chain_idx].append(result)
                            stats["succeeded"] += 1
                            # Only count genuinely accepted questions; keeps
                            # done monotonically increasing toward total_planned
                            # with no jumps caused by refill rounds.
                            done += 1
                            if progress_callback:
                                progress_callback(done, total_planned)
                    else:
                        window_fail += 1
                        stats["failed"] += 1

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
                    time.sleep(min(5.0, 1.2 + round_idx))
            if cancel_event is not None and cancel_event.is_set():
                break

    outputs: List[Dict[str, Any]] = []
    for chain_idx, items in outputs_by_chain.items():
        for sample_idx, item in enumerate(items[:questions_per_chain], start=1):
            chain_id = str(item.get("chain_id", f"chain-{chain_idx:03d}"))
            item["sample_id"] = f"{chain_id}-q{sample_idx:02d}"
            outputs.append(item)

    stats["final_workers"] = current_workers
    stats["cancelled"] = bool(cancel_event is not None and cancel_event.is_set())
    generate_benchmark_mcq.last_run_stats = stats
    return outputs

