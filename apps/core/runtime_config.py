from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from django.conf import settings
from django.utils import timezone


DEFAULT_ML_WEIGHTS: Dict[str, float] = {
    "price": 0.40,
    "distance": 0.20,
    "rating": 0.20,
    "delivery": 0.10,
    "reliability": 0.10,
}

ML_WEIGHT_KEYS = tuple(DEFAULT_ML_WEIGHTS.keys())


def _runtime_dir() -> Path:
    return Path(settings.BASE_DIR) / "runtime"


def _ml_weights_path() -> Path:
    return _runtime_dir() / "ml_weights.json"


def _normalize_weights(weights: Dict[str, float]) -> Dict[str, float]:
    cleaned: Dict[str, float] = {}
    for key in ML_WEIGHT_KEYS:
        try:
            value = float(weights.get(key, DEFAULT_ML_WEIGHTS[key]) or 0)
        except (TypeError, ValueError):
            value = DEFAULT_ML_WEIGHTS[key]
        cleaned[key] = max(value, 0.0)

    total = sum(cleaned.values())
    if total <= 0:
        return DEFAULT_ML_WEIGHTS.copy()

    return {key: round(value / total, 4) for key, value in cleaned.items()}


def get_ml_weights() -> Dict[str, float]:
    path = _ml_weights_path()
    if not path.exists():
        return DEFAULT_ML_WEIGHTS.copy()

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_ML_WEIGHTS.copy()

    return _normalize_weights(payload.get("weights", {}))


def get_ml_weights_metadata() -> Dict[str, object]:
    path = _ml_weights_path()
    weights = get_ml_weights()
    updated_at = None
    exists = path.exists()

    if exists:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            updated_at = payload.get("updated_at")
        except (OSError, json.JSONDecodeError):
            updated_at = None

    return {
        "weights": weights,
        "path": str(path),
        "exists": exists,
        "updated_at": updated_at,
    }


def save_ml_weights(weights: Dict[str, float]) -> Dict[str, float]:
    normalized = _normalize_weights(weights)
    path = _ml_weights_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "weights": normalized,
        "updated_at": timezone.now().isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return normalized
