"""Gestion des macros utilisateur.

Une macro = un nom court + une liste de lignes G-code à envoyer en séquence.
Stockée dans `<AppLocalData>/macros.json`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, QStandardPaths, Signal


@dataclass
class Macro:
    name: str = ""
    description: str = ""
    lines: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Macro":
        return cls(
            name=d.get("name", ""),
            description=d.get("description", ""),
            lines=list(d.get("lines", [])),
        )


DEFAULT_MACROS = [
    Macro(
        name="Position parking",
        description="Va à une position dégagée pour changer le bloc de mousse.",
        lines=["G90 G0 X0 Y80 A0 Z80"],
    ),
    Macro(
        name="Aller à G28",
        description="Va à la position mémorisée G28.",
        lines=["G28"],
    ),
    Macro(
        name="Test fil chaud 5s",
        description="Allume le fil à puissance 500 pendant 5 secondes (pour calibrer le courant).",
        lines=["M3 S500", "G4 P5", "M5"],
    ),
]


class MacroStore(QObject):
    changed = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._macros: list[Macro] = []
        base = QStandardPaths.writableLocation(
            QStandardPaths.AppLocalDataLocation
        )
        self._path = Path(base) / "macros.json" if base else None
        if self._path is not None:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
        self.load()
        if not self._macros:
            # Init avec les macros d'exemple à la 1ère utilisation
            self._macros = [Macro(**asdict(m)) for m in DEFAULT_MACROS]
            self.save()

    @property
    def file_path(self) -> Path | None:
        return self._path

    def all(self) -> list[Macro]:
        return list(self._macros)

    def add(self, macro: Macro) -> None:
        self._macros.append(macro)
        self.save()
        self.changed.emit()

    def update(self, index: int, macro: Macro) -> None:
        if 0 <= index < len(self._macros):
            self._macros[index] = macro
            self.save()
            self.changed.emit()

    def remove(self, index: int) -> None:
        if 0 <= index < len(self._macros):
            del self._macros[index]
            self.save()
            self.changed.emit()

    def load(self) -> None:
        if self._path is None or not self._path.exists():
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._macros = [Macro.from_dict(d) for d in data.get("macros", [])]
        except Exception:
            self._macros = []

    def save(self) -> None:
        if self._path is None:
            return
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(
                    {"macros": [asdict(m) for m in self._macros]},
                    f, ensure_ascii=False, indent=1,
                )
        except Exception:
            pass
