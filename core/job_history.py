"""Historique des coupes exécutées.

Chaque job lancé enregistre une entrée au moment de sa fin (normale, stop
utilisateur, abort sur erreur/alarme/watchdog). L'historique est persisté
dans `<AppLocalData>/job_history.json` (typiquement
`%LOCALAPPDATA%/HotWire/HotWire Sender/job_history.json` sous Windows).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QStandardPaths, Signal


@dataclass
class HistoryEntry:
    started_at: str         # ISO datetime local
    finished_at: str
    duration_s: float
    file_path: str          # chemin original ou "<slicer>"
    file_name: str          # basename pour affichage
    lines_count: int
    status: str             # "ok" | "stopped" | "aborted" | "error"
    notes: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "HistoryEntry":
        return cls(
            started_at=d.get("started_at", ""),
            finished_at=d.get("finished_at", ""),
            duration_s=float(d.get("duration_s", 0)),
            file_path=d.get("file_path", ""),
            file_name=d.get("file_name", ""),
            lines_count=int(d.get("lines_count", 0)),
            status=d.get("status", "ok"),
            notes=d.get("notes", ""),
        )


class JobHistory(QObject):
    """Liste persistante des jobs exécutés. Émet `changed` après ajout/clear."""

    changed = Signal()

    def __init__(self, max_entries: int = 200, parent: QObject | None = None):
        super().__init__(parent)
        self._max = max_entries
        self._entries: list[HistoryEntry] = []
        base = QStandardPaths.writableLocation(
            QStandardPaths.AppLocalDataLocation
        )
        self._path = Path(base) / "job_history.json" if base else None
        if self._path is not None:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
        self.load()

    @property
    def file_path(self) -> Path | None:
        return self._path

    def all(self) -> list[HistoryEntry]:
        """Retourne la liste, du plus récent en premier."""
        return list(reversed(self._entries))

    def add(self, entry: HistoryEntry) -> None:
        self._entries.append(entry)
        if len(self._entries) > self._max:
            self._entries = self._entries[-self._max:]
        self.save()
        self.changed.emit()

    def clear(self) -> None:
        self._entries.clear()
        self.save()
        self.changed.emit()

    def load(self) -> None:
        if self._path is None or not self._path.exists():
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._entries = [
                HistoryEntry.from_dict(d) for d in data.get("entries", [])
            ]
        except Exception:
            self._entries = []

    def save(self) -> None:
        if self._path is None:
            return
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(
                    {"entries": [asdict(e) for e in self._entries]},
                    f, ensure_ascii=False, indent=1,
                )
        except Exception:
            pass


def make_entry(
    started_at: datetime,
    duration_s: float,
    file_path: str,
    lines_count: int,
    status: str,
    notes: str = "",
) -> HistoryEntry:
    """Helper pour construire un HistoryEntry avec timestamps formatés."""
    name = file_path
    if file_path and file_path != "<slicer>":
        try:
            name = Path(file_path).name
        except Exception:
            pass
    return HistoryEntry(
        started_at=started_at.isoformat(timespec="seconds"),
        finished_at=datetime.now().isoformat(timespec="seconds"),
        duration_s=duration_s,
        file_path=file_path or "",
        file_name=name or "(programme sans nom)",
        lines_count=lines_count,
        status=status,
        notes=notes,
    )
