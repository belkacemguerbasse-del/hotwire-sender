"""Sérialisation d'un projet HotWire complet (`.hwproj`).

Un fichier `.hwproj` est un JSON qui contient :
- la `WingDefinition` (sections + profils référencés par chemin)
- la géométrie machine (wire_span, faces du bloc)
- les paramètres de coupe (feed, S, leadin/out, n_resample, safe_y, mode)
- une métadonnée de version pour la rétrocompat

Usage typique : tu sauves « aile_droite_planeur1.hwproj », tu réouvres
exactement le même setup pour découper l'aile gauche en miroir.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .wing import WingDefinition

PROJECT_FORMAT = "hotwire-project"
PROJECT_VERSION = 1
PROJECT_EXTENSION = ".hwproj"


@dataclass
class CutGeometryDict:
    wire_span: float = 1000.0
    block_root_x: float = 150.0
    block_tip_x: float = 850.0
    # Épaisseur du bloc (T) — utile pour la coupe LE/TE et le placement vertical
    block_thickness_mm: float = 50.0
    # Hauteur du panneau (H) au-dessus de la base du bloc, root/tip
    panel_height_root_mm: float = 25.0
    panel_height_tip_mm: float = 25.0


@dataclass
class CutParamsDict:
    feed: float = 200.0
    hot_wire_s: int = 500
    leadin_mm: float = 20.0
    leadout_mm: float = 20.0
    n_resample: int = 200
    safe_y: float = 80.0
    mode: str = "single"
    adaptive_kerf: bool = False
    kerf_ref_feed: float = 300.0
    # --- Sheeting (coffrage extrados/intrados) ---
    sheeting_upper_mm: float = 0.0
    sheeting_lower_mm: float = 0.0
    # Allongement tangentiel du bord de fuite (mm)
    tangent_extend_te_mm: float = 0.0
    # Kerf différencié root/tip. Si > 0 : override le kerf des sections.
    # Interpolé linéairement entre root et tip pour les panneaux intérieurs.
    kerf_root_mm: float = 0.0
    kerf_tip_mm: float = 0.0
    use_differential_kerf: bool = False


@dataclass
class HotWireProject:
    wing: WingDefinition = field(default_factory=WingDefinition)
    geometry: CutGeometryDict = field(default_factory=CutGeometryDict)
    cut_params: CutParamsDict = field(default_factory=CutParamsDict)
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "format": PROJECT_FORMAT,
            "version": PROJECT_VERSION,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "wing": self.wing.to_dict(),
            "geometry": asdict(self.geometry),
            "cut_params": asdict(self.cut_params),
            "notes": self.notes,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "HotWireProject":
        if d.get("format") != PROJECT_FORMAT:
            raise ValueError(
                f"Format invalide : attendu {PROJECT_FORMAT!r}, reçu {d.get('format')!r}"
            )
        version = int(d.get("version", 0))
        if version > PROJECT_VERSION:
            raise ValueError(
                f"Version {version} non supportée (cette app gère ≤ {PROJECT_VERSION})."
            )
        return cls(
            wing=WingDefinition.from_dict(d.get("wing", {})),
            geometry=CutGeometryDict(**d.get("geometry", {})),
            cut_params=CutParamsDict(**d.get("cut_params", {})),
            notes=d.get("notes", ""),
        )

    @classmethod
    def from_json(cls, text: str) -> "HotWireProject":
        return cls.from_dict(json.loads(text))

    @classmethod
    def load(cls, path: str | Path) -> "HotWireProject":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_json(f.read())

    def save(self, path: str | Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())
