"""Persistance des préférences utilisateur via QSettings.

Stocke sur Windows dans la base de registre sous
HKCU\\Software\\HotWire\\HotWire Sender. Aucun fichier à gérer.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSettings


def settings() -> QSettings:
    """Retourne l'objet QSettings configuré pour l'app."""
    return QSettings("HotWire", "HotWire Sender")


def get(key: str, default: Any = None, type_=None) -> Any:
    s = settings()
    if type_ is not None:
        return s.value(key, default, type=type_)
    return s.value(key, default)


def set_(key: str, value: Any) -> None:
    settings().setValue(key, value)


def get_bool(key: str, default: bool = False) -> bool:
    v = settings().value(key, default)
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() in ("1", "true", "yes", "on")
    return bool(v)


def get_int(key: str, default: int = 0) -> int:
    try:
        return int(settings().value(key, default))
    except (TypeError, ValueError):
        return default


def get_float(key: str, default: float = 0.0) -> float:
    try:
        return float(settings().value(key, default))
    except (TypeError, ValueError):
        return default


def get_str(key: str, default: str = "") -> str:
    v = settings().value(key, default)
    return str(v) if v is not None else default
