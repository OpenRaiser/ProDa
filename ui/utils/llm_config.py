from __future__ import annotations

import json
from typing import Dict, List, Tuple

DEFAULT_PROFILES: Dict[str, Dict[str, object]] = {
    "openai": {
        "api_key": "",
        "api_base": "",
        "verified_models": [],
        "available_models": [],
        "configured": False,
        "last_model": "",
    },
    "anthropic": {
        "api_key": "",
        "api_base": "",
        "verified_models": [],
        "available_models": [],
        "configured": False,
        "last_model": "",
    },
    "deepseek": {
        "api_key": "",
        "api_base": "",
        "verified_models": [],
        "available_models": [],
        "configured": False,
        "last_model": "",
    },
}


def default_llm_profiles() -> Dict[str, Dict[str, object]]:
    return json.loads(json.dumps(DEFAULT_PROFILES))


def _normalize_profile(payload: Dict[str, object], default: Dict[str, object]) -> Dict[str, object]:
    normalized = dict(default)
    normalized.update(payload)

    verified_models = payload.get("verified_models")
    legacy_models = payload.get("models")
    if not isinstance(verified_models, list) or not verified_models:
        if isinstance(legacy_models, list):
            verified_models = legacy_models
        else:
            verified_models = []
    normalized["verified_models"] = sorted(list({str(x).strip() for x in verified_models if str(x).strip()}))

    available_models = payload.get("available_models")
    if not isinstance(available_models, list):
        available_models = normalized["verified_models"]
    normalized["available_models"] = sorted(list({str(x).strip() for x in available_models if str(x).strip()}))
    normalized["configured"] = len(normalized["verified_models"]) > 0
    normalized["last_model"] = str(payload.get("last_model", "")).strip()
    return normalized


def normalize_llm_profiles(raw_profiles: Dict[str, Dict[str, object]]) -> Dict[str, Dict[str, object]]:
    profiles = default_llm_profiles()
    for provider, payload in raw_profiles.items():
        if provider in profiles and isinstance(payload, dict):
            profiles[provider] = _normalize_profile(payload, profiles[provider])
    return profiles


def configured_model_options(profiles: Dict[str, Dict[str, object]]) -> List[Tuple[str, str]]:
    options: List[Tuple[str, str]] = []
    for provider, payload in profiles.items():
        if not payload.get("configured"):
            continue
        for model in payload.get("verified_models", []):
            model_str = str(model).strip()
            if not model_str:
                continue
            key = f"{provider}::{model_str}"
            label = f"{provider} / {model_str}"
            options.append((key, label))
    return options


def parse_selected_model(model_key: str) -> Tuple[str, str]:
    if "::" not in model_key:
        return "", ""
    provider, model = model_key.split("::", 1)
    return provider, model


def _openai_like_models(api_key: str, api_base: str) -> List[str]:
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=(api_base.strip() or None))
    resp = client.models.list()
    return sorted(list({x.id for x in resp.data if getattr(x, "id", None)}))


def _openai_like_ping(api_key: str, api_base: str, model_name: str) -> None:
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=(api_base.strip() or None))
    client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": "ping"}],
        temperature=0,
        max_tokens=1,
    )


def _anthropic_models(api_key: str, api_base: str) -> List[str]:
    import anthropic

    kwargs = {"api_key": api_key}
    if api_base.strip():
        kwargs["base_url"] = api_base.strip()
    client = anthropic.Anthropic(**kwargs)
    resp = client.models.list(limit=100)
    return sorted(list({x.id for x in resp.data if getattr(x, "id", None)}))


def _anthropic_ping(api_key: str, api_base: str, model_name: str) -> None:
    import anthropic

    kwargs = {"api_key": api_key}
    if api_base.strip():
        kwargs["base_url"] = api_base.strip()
    client = anthropic.Anthropic(**kwargs)
    client.messages.create(
        model=model_name,
        messages=[{"role": "user", "content": "ping"}],
        temperature=0,
        max_tokens=1,
    )


def test_connectivity(provider: str, api_key: str, api_base: str, model_name: str) -> Tuple[bool, List[str], str]:
    if not api_key.strip():
        return False, [], "API Key is empty"
    if not model_name.strip():
        return False, [], "Model name is empty"

    model_name = model_name.strip()
    try:
        if provider == "openai":
            models = _openai_like_models(api_key, api_base)
            _openai_like_ping(api_key, api_base, model_name)
        elif provider == "deepseek":
            base = api_base.strip() or "https://api.deepseek.com"
            models = _openai_like_models(api_key, base)
            _openai_like_ping(api_key, base, model_name)
        elif provider == "anthropic":
            models = _anthropic_models(api_key, api_base)
            _anthropic_ping(api_key, api_base, model_name)
        else:
            return False, [], f"Unsupported provider: {provider}"
    except Exception as exc:
        return False, [], str(exc)

    if model_name not in models:
        models = sorted(list(set(models + [model_name])))
    return True, models, ""

