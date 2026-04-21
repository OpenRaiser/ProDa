from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


PROMPT_DIR = Path(__file__).resolve().parent / "resources" / "KnowledgeCore"
L1_PROMPT_PATH = PROMPT_DIR / "L1_Concept.txt"
L2_PROMPT_PATH = PROMPT_DIR / "L2_Statement.txt"
L3_PROMPT_PATH = PROMPT_DIR / "L3_Reasoning_chain.txt"


L1_PROMPT_FALLBACK = """{L2_STATEMENTS_INPUT}"""
L2_PROMPT_FALLBACK = """{L3_CHAINS_INPUT}\n{ORIGINAL_TEXT}"""
L3_PROMPT_FALLBACK = """{INPUT_TEXT}"""


def _load_prompt(path: Path, fallback: str) -> str:
    try:
        content = path.read_text(encoding="utf-8").strip()
        if content:
            return content
    except Exception:
        pass
    return fallback


L1_PROMPT = _load_prompt(L1_PROMPT_PATH, L1_PROMPT_FALLBACK)
L2_PROMPT = _load_prompt(L2_PROMPT_PATH, L2_PROMPT_FALLBACK)
L3_PROMPT = _load_prompt(L3_PROMPT_PATH, L3_PROMPT_FALLBACK)


def _render_prompt(template: str, variables: Dict[str, str]) -> str:
    """
    Render prompt placeholders safely without Python .format().

    Prompt templates include many JSON braces like { and }, which conflict with
    str.format syntax. We only replace known placeholders directly.
    """
    rendered = template
    for key, value in variables.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered


def parse_json_array(text: str) -> List[Dict[str, Any]]:
    match = re.search(r"\[[\s\S]*\]", text)
    payload = match.group(0) if match else text
    data = json.loads(payload)
    if not isinstance(data, list):
        raise ValueError("LLM response is not a JSON array")
    return data


def _renumber_chains(chains: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    id_map: Dict[str, str] = {}
    for idx, chain in enumerate(chains, start=1):
        old = str(chain.get("chain_id", f"chain-{idx:03d}"))
        new = f"chain-{idx:03d}"
        chain["chain_id"] = new
        id_map[old] = new
    return chains, id_map


def _renumber_statements(statements: List[Dict[str, Any]], id_map: Dict[str, str]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for idx, item in enumerate(statements, start=1):
        old_parent = str(item.get("parent_chain_id", ""))
        if old_parent in id_map:
            item["parent_chain_id"] = id_map[old_parent]
        item["statement_id"] = f"stmt-{idx:03d}"
        result.append(item)
    return result


def _renumber_concepts(concepts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for idx, item in enumerate(concepts, start=1):
        item["concept_id"] = f"concept-{idx:03d}"
    return concepts


def _dedupe_by_key(items: Iterable[Dict[str, Any]], key_fn) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for item in items:
        key = key_fn(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def call_llm(provider: str, model: str, api_key: str, api_base: str, prompt: str, max_tokens: int = 4096) -> str:
    if provider in {"openai", "deepseek"}:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Missing dependency: openai") from exc
        base_url = api_base.strip() or (None if provider == "openai" else "https://api.deepseek.com")
        client = OpenAI(api_key=api_key, base_url=base_url)
        res = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=max_tokens,
        )
        return (res.choices[0].message.content or "").strip()

    if provider == "anthropic":
        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError("Missing dependency: anthropic") from exc
        kwargs = {"api_key": api_key}
        if api_base.strip():
            kwargs["base_url"] = api_base.strip()
        client = anthropic.Anthropic(**kwargs)
        res = client.messages.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=max_tokens,
        )
        return "".join([b.text for b in res.content if hasattr(b, "text")]).strip()

    raise ValueError(f"Unsupported provider: {provider}")


def extract_knowledge_core(text: str, provider: str, model: str, api_key: str, api_base: str) -> Dict[str, Any]:
    l3_prompt = _render_prompt(L3_PROMPT, {"INPUT_TEXT": text})
    l3_raw = call_llm(provider, model, api_key, api_base, l3_prompt)
    l3 = parse_json_array(l3_raw)
    l3_json = json.dumps(l3, ensure_ascii=False, indent=2)
    l2_prompt = _render_prompt(
        L2_PROMPT,
        {
            "L3_CHAINS_INPUT": l3_json,
            "ORIGINAL_TEXT": text,
        },
    )
    l2_raw = call_llm(
        provider,
        model,
        api_key,
        api_base,
        l2_prompt,
    )
    l2 = parse_json_array(l2_raw)
    l2_json = json.dumps(l2, ensure_ascii=False, indent=2)
    l1_prompt = _render_prompt(L1_PROMPT, {"L2_STATEMENTS_INPUT": l2_json})
    l1_raw = call_llm(
        provider,
        model,
        api_key,
        api_base,
        l1_prompt,
    )
    l1 = parse_json_array(l1_raw)

    l3 = _dedupe_by_key(l3, lambda x: tuple(x.get("steps", [])))
    l3, chain_map = _renumber_chains(l3)
    l2 = _dedupe_by_key(
        l2,
        lambda x: (
            str(x.get("parent_chain_id", "")).strip().lower(),
            str(x.get("subject", "")).strip().lower(),
            str(x.get("predicate", "")).strip().lower(),
            str(x.get("object", "")).strip().lower(),
        ),
    )
    l2 = _renumber_statements(l2, chain_map)
    l1 = _dedupe_by_key(l1, lambda x: str(x.get("term", "")).strip().lower())
    l1 = _renumber_concepts(l1)
    return {
        "l3_chains": l3,
        "l2_statements": l2,
        "l1_concepts": l1,
        "statistics": {
            "total_chains": len(l3),
            "total_statements": len(l2),
            "total_concepts": len(l1),
            "text_length": len(text),
        },
    }

