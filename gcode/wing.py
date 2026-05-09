"""Modèle de données pour une aile multi-panneaux.

Une `WingDefinition` est une liste ordonnée de `Section` triée par position
le long de l'envergure (`span_y`, en mm depuis l'emplanture). Entre 2 sections
consécutives, on a un `Panel` qui sera découpé en faisant varier les profils,
cordes, twists, offsets de manière linéaire.

Convention :
- l'emplanture (root) est à `span_y = 0`
- le saumon (tip) est à `span_y = WingDefinition.total_span_mm`

Chaque Section porte le **profil normalisé** (.dat Selig en 0..1), pas encore
transformé. La transformation (corde, twist, offset, kerf) est appliquée par
le slicer au moment de générer le G-code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from .profiles import Profile, kerf_offset, load_profile, morph, transform


@dataclass
class Section:
    """Une section transversale de l'aile à une position d'envergure donnée."""

    span_y_mm: float                  # position le long de l'envergure (mm)
    profile_path: str = ""            # chemin .dat (peut être vide si non chargé)
    profile_name: str = ""            # nom convivial (du fichier .dat ou affiché)
    chord_mm: float = 200.0           # corde réelle en mm
    twist_deg: float = 0.0            # vrillage en degrés (positif = nez en haut)
    offset_x_mm: float = 0.0          # décalage horizontal (sweep accumulé)
    offset_y_mm: float = 0.0          # décalage vertical (dièdre accumulé)
    kerf_mm: float = 0.0              # compensation sillage fil pour cette section
    profile: Optional[Profile] = field(default=None, repr=False)

    def is_loaded(self) -> bool:
        return self.profile is not None

    def to_dict(self) -> dict:
        d = {k: v for k, v in asdict(self).items() if k != "profile"}
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Section":
        d2 = dict(d)
        d2.pop("profile", None)
        s = cls(**d2)
        if s.profile_path:
            try:
                s.profile = load_profile(s.profile_path)
                if not s.profile_name:
                    s.profile_name = s.profile.name
            except Exception:
                pass
        return s

    def transformed(self) -> Optional[Profile]:
        """Profil transformé en mm prêt pour la projection sur les chariots :
        échelle par corde + twist + offset + kerf."""
        if self.profile is None:
            return None
        p = transform(
            self.profile,
            chord_mm=self.chord_mm,
            offset_x=self.offset_x_mm,
            offset_y=self.offset_y_mm,
            twist_deg=self.twist_deg,
        )
        if abs(self.kerf_mm) > 1e-9:
            p = kerf_offset(p, self.kerf_mm)
        return p


@dataclass
class WingDefinition:
    """Définition complète d'une aile à découper.

    Les sections sont triées par `span_y_mm` croissant. La section[0] est
    forcément à span_y=0 (emplanture). La dernière définit l'envergure totale.
    """

    sections: list[Section] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.sort()

    def sort(self) -> None:
        self.sections.sort(key=lambda s: s.span_y_mm)

    @property
    def n_sections(self) -> int:
        return len(self.sections)

    @property
    def n_panels(self) -> int:
        return max(0, self.n_sections - 1)

    @property
    def total_span_mm(self) -> float:
        if not self.sections:
            return 0.0
        return self.sections[-1].span_y_mm - self.sections[0].span_y_mm

    def panel(self, i: int) -> tuple[Section, Section]:
        return self.sections[i], self.sections[i + 1]

    def is_loaded(self) -> bool:
        return self.n_sections >= 2 and all(s.is_loaded() for s in self.sections)

    # ---- Sérialisation ----

    def to_dict(self) -> dict:
        return {"sections": [s.to_dict() for s in self.sections]}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=1)

    @classmethod
    def from_dict(cls, d: dict) -> "WingDefinition":
        return cls(sections=[Section.from_dict(s) for s in d.get("sections", [])])

    @classmethod
    def from_json(cls, text: str) -> "WingDefinition":
        return cls.from_dict(json.loads(text))

    @classmethod
    def load(cls, path: str | Path) -> "WingDefinition":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_json(f.read())

    def save(self, path: str | Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())

    # ---- Helpers ----

    def section_at_span(self, span_y_mm: float, n_points: int = 200) -> Optional[Section]:
        """Calcule la section interpolée à une position arbitraire le long de
        l'envergure. Utilisé pour la prévisualisation et la coupe par
        sub-divisions le long d'un panneau si on voulait être plus fin."""
        if self.n_sections < 2:
            return None
        # Clamp aux bords
        y0 = self.sections[0].span_y_mm
        y1 = self.sections[-1].span_y_mm
        if span_y_mm <= y0:
            return self.sections[0]
        if span_y_mm >= y1:
            return self.sections[-1]
        # Trouve le panneau englobant
        for i in range(self.n_panels):
            sa, sb = self.panel(i)
            if sa.span_y_mm <= span_y_mm <= sb.span_y_mm:
                if sb.span_y_mm == sa.span_y_mm:
                    return sa
                t = (span_y_mm - sa.span_y_mm) / (sb.span_y_mm - sa.span_y_mm)
                return _interp_sections(sa, sb, t, n_points=n_points)
        return None


def _interp_sections(a: Section, b: Section, t: float, n_points: int = 200) -> Section:
    """Crée une section virtuelle interpolée entre a et b à `t` ∈ [0, 1].
    Utile pour visualiser une tranche au milieu d'un panneau."""
    if a.profile is None or b.profile is None:
        return a
    if a.profile is b.profile or a.profile.points == b.profile.points:
        # Même profil -> pas de morphing nécessaire
        prof = a.profile
    else:
        prof = morph(a.profile, b.profile, t, n_points=n_points)
    return Section(
        span_y_mm=(1 - t) * a.span_y_mm + t * b.span_y_mm,
        profile_path="",
        profile_name=prof.name,
        chord_mm=(1 - t) * a.chord_mm + t * b.chord_mm,
        twist_deg=(1 - t) * a.twist_deg + t * b.twist_deg,
        offset_x_mm=(1 - t) * a.offset_x_mm + t * b.offset_x_mm,
        offset_y_mm=(1 - t) * a.offset_y_mm + t * b.offset_y_mm,
        kerf_mm=(1 - t) * a.kerf_mm + t * b.kerf_mm,
        profile=prof,
    )
