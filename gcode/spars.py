"""Longerons (spars) : encoches rectangulaires dans le profil pour le passage
des longerons structuraux (tube carbone, baguette balsa, etc.).

Modélisation simplifiée Step 2 : chaque longeron = encoche rectangulaire
définie par sa position le long de la corde, sa largeur (le long de la corde)
et sa profondeur (perpendiculaire à la corde, vers l'intérieur du profil).

Les longerons peuvent être :
- sur l'extrados (`surface="upper"`) : la coupe descend depuis le haut
- sur l'intrados (`surface="lower"`) : la coupe remonte depuis le bas

Pour une aile tapered, chaque dimension peut varier linéairement de
l'emplanture (`*_root`) au saumon (`*_tip`). Le slicer interpole entre les
deux selon la position d'envergure du panneau courant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .profiles import Profile


SparSurface = Literal["upper", "lower"]


@dataclass
class Spar:
    """Définition d'un longeron à inclure dans la coupe."""

    name: str = ""
    surface: SparSurface = "upper"   # extrados ou intrados
    # Position le long de la corde, en mm absolus depuis le bord d'attaque
    # (LE = x=0). Peut être convertie depuis un % de corde par le caller.
    x_root_mm: float = 30.0
    x_tip_mm: float = 30.0
    # Dimensions de la section rectangulaire
    width_root_mm: float = 8.0
    width_tip_mm: float = 8.0
    depth_root_mm: float = 5.0
    depth_tip_mm: float = 5.0

    def at(self, t: float) -> "Spar":
        """Interpole les dimensions à la position normalisée `t` ∈ [0, 1]
        (0 = root, 1 = tip). Retourne un nouveau Spar avec les valeurs
        constantes (root = tip = valeurs interpolées)."""
        t = max(0.0, min(1.0, t))
        x = (1 - t) * self.x_root_mm + t * self.x_tip_mm
        w = (1 - t) * self.width_root_mm + t * self.width_tip_mm
        d = (1 - t) * self.depth_root_mm + t * self.depth_tip_mm
        return Spar(
            name=self.name,
            surface=self.surface,
            x_root_mm=x, x_tip_mm=x,
            width_root_mm=w, width_tip_mm=w,
            depth_root_mm=d, depth_tip_mm=d,
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "surface": self.surface,
            "x_root_mm": self.x_root_mm,
            "x_tip_mm": self.x_tip_mm,
            "width_root_mm": self.width_root_mm,
            "width_tip_mm": self.width_tip_mm,
            "depth_root_mm": self.depth_root_mm,
            "depth_tip_mm": self.depth_tip_mm,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Spar":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def _surface_y_at(points: list[tuple[float, float]], x: float, upper: bool) -> float:
    """Interpole la coordonnée Y de la surface (extrados ou intrados) à
    l'abscisse `x` donnée. Le profil est suppose en convention TE→top→LE→bot→TE."""
    le_idx = min(range(len(points)), key=lambda i: points[i][0])
    if upper:
        seg = points[:le_idx + 1]
    else:
        seg = points[le_idx:]
    # Recherche le segment contenant x
    for i in range(len(seg) - 1):
        x0, y0 = seg[i]
        x1, y1 = seg[i + 1]
        if (x0 <= x <= x1) or (x1 <= x <= x0):
            if abs(x1 - x0) < 1e-9:
                return y0
            u = (x - x0) / (x1 - x0)
            return y0 + u * (y1 - y0)
    # Hors plage : retourne l'extrême le plus proche
    if abs(seg[0][0] - x) < abs(seg[-1][0] - x):
        return seg[0][1]
    return seg[-1][1]


def insert_spars(profile: Profile, spars: list[Spar], t: float = 0.0) -> Profile:
    """Insère les encoches rectangulaires des longerons dans le contour
    du profil (en mm, après transformation par le slicer).

    `t` ∈ [0, 1] : position normalisée du profil dans le panneau (0=root, 1=tip).
    Les dimensions de chaque spar sont interpolées entre root et tip selon `t`.

    Convention du parcours TE→extrados→LE→intrados→TE. Pour un longeron
    extrados, on insère 4 points :
        - entrée au niveau de la surface (xA, y_surf(xA))
        - descente verticale (xA, y_surf(xA) - depth)
        - traversée latérale (xB, y_surf(xA) - depth)
        - remontée verticale (xB, y_surf(xB))
    où xA = x - width/2, xB = x + width/2.

    Pour l'intrados, même logique avec +depth au lieu de -depth, et le
    parcours étant inversé (LE→TE), on insère les points dans l'ordre xA→xB
    en remontant.
    """
    if not spars or profile.n < 4:
        return Profile(name=profile.name, points=list(profile.points))

    pts = list(profile.points)
    closed = pts and pts[0] == pts[-1]
    if closed:
        pts = pts[:-1]

    le_idx = min(range(len(pts)), key=lambda i: pts[i][0])

    # On traite les spars un par un, en triant pour pouvoir les insérer
    # sans décaler les indices déjà calculés.
    spars_at_t = [s.at(t) for s in spars]

    # Sépare extrados / intrados
    upper_spars = [s for s in spars_at_t if s.surface == "upper"]
    lower_spars = [s for s in spars_at_t if s.surface == "lower"]

    # Extrados : parcours TE → LE, x décroissant. On trie les spars par x décroissant.
    upper_spars.sort(key=lambda s: -s.x_root_mm)
    # Intrados : parcours LE → TE, x croissant. Trie par x croissant.
    lower_spars.sort(key=lambda s: s.x_root_mm)

    # Reconstruit la polyline en insérant les notches au passage
    new_pts: list[tuple[float, float]] = []

    # Segment extrados : index 0 (TE haut) → le_idx (LE)
    upper_seg = pts[:le_idx + 1]
    # On itère sur l'extrados et insère les notches quand x du segment courant
    # croise le xA (entrée) du spar
    pending_upper = list(upper_spars)
    for i in range(len(upper_seg)):
        new_pts.append(upper_seg[i])
        if i == len(upper_seg) - 1:
            break
        x0 = upper_seg[i][0]
        x1 = upper_seg[i + 1][0]
        # Sur l'extrados, x décroît (TE→LE)
        while pending_upper:
            s = pending_upper[0]
            xA = s.x_root_mm + s.width_root_mm / 2  # entrée côté TE
            xB = s.x_root_mm - s.width_root_mm / 2  # sortie côté LE
            if x1 <= xA <= x0 or x0 <= xA <= x1:
                yA = _surface_y_at(pts, xA, upper=True)
                yB = _surface_y_at(pts, xB, upper=True)
                d = s.depth_root_mm
                new_pts.append((xA, yA))
                new_pts.append((xA, yA - d))
                new_pts.append((xB, yA - d))
                new_pts.append((xB, yB))
                pending_upper.pop(0)
            else:
                break

    # Segment intrados : le_idx → fin
    lower_seg = pts[le_idx:]
    pending_lower = list(lower_spars)
    for i in range(1, len(lower_seg)):  # le_idx déjà ajouté ci-dessus
        x0 = lower_seg[i - 1][0]
        x1 = lower_seg[i][0]
        # Sur l'intrados, x croît (LE→TE)
        while pending_lower:
            s = pending_lower[0]
            xA = s.x_root_mm - s.width_root_mm / 2  # entrée côté LE
            xB = s.x_root_mm + s.width_root_mm / 2  # sortie côté TE
            if x0 <= xA <= x1 or x1 <= xA <= x0:
                yA = _surface_y_at(pts, xA, upper=False)
                yB = _surface_y_at(pts, xB, upper=False)
                d = s.depth_root_mm
                new_pts.append((xA, yA))
                new_pts.append((xA, yA + d))
                new_pts.append((xB, yA + d))
                new_pts.append((xB, yB))
                pending_lower.pop(0)
            else:
                break
        new_pts.append(lower_seg[i])

    if closed and new_pts and new_pts[0] != new_pts[-1]:
        new_pts.append(new_pts[0])

    return Profile(name=profile.name, points=new_pts)


@dataclass
class LighteningHole:
    """Trou d'allègement (utilisé pour les gabarits de nervures, pas la mousse).

    Conservé dans le projet pour reproductibilité et inclusion dans la
    fiche PDF, mais n'a aucun effet sur le G-code de coupe mousse."""

    name: str = ""
    shape: Literal["airfoil", "rectangle", "ellipse"] = "airfoil"
    rib_edge_thickness_pct: float = 20.0
    automatic: bool = False
    x_start_root_mm: float = 50.0
    x_end_root_mm: float = 100.0
    x_start_tip_mm: float = 50.0
    x_end_tip_mm: float = 100.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "shape": self.shape,
            "rib_edge_thickness_pct": self.rib_edge_thickness_pct,
            "automatic": self.automatic,
            "x_start_root_mm": self.x_start_root_mm,
            "x_end_root_mm": self.x_end_root_mm,
            "x_start_tip_mm": self.x_start_tip_mm,
            "x_end_tip_mm": self.x_end_tip_mm,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LighteningHole":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
