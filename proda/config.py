from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List


CONFIG_PATH = Path(__file__).resolve().parent.parent / ".proda_config.json"


DEFAULT_CONFIG: Dict[str, str] = {
    "provider": "openai",
    "api_key": "",
    "api_base": "",
    "selected_model": "",
}


MODEL_CATALOG: Dict[str, List[str]] = {
    "openai": ["gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini"],
    "anthropic": ["claude-3-5-sonnet-20241022", "claude-3-7-sonnet-latest"],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
}


def load_config() -> Dict[str, str]:
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG.copy()
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        merged = DEFAULT_CONFIG.copy()
        merged.update({k: str(v) for k, v in data.items() if k in merged})
        return merged
    except Exception:
        return DEFAULT_CONFIG.copy()


def save_config(config: Dict[str, str]) -> None:
    payload = DEFAULT_CONFIG.copy()
    payload.update(config)
    CONFIG_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_provider_models(provider: str) -> List[str]:
    return MODEL_CATALOG.get(provider, [])

