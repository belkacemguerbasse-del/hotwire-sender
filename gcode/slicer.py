"""Slicer fil chaud : projection de 2 profils sur 4 axes (X,Y,Z,A).

Convention :
- chariot gauche = (X, Y) ; chariot droit = (Z, A)
- les profils sont en mm, déjà transformés (corde, twist, offset)
- on suppose des profils ré-échantillonnés au même nombre de points
- le bloc de mousse est positionné entre les deux tours selon `block_root_x`
  (distance du tour gauche à la face emplanture) et `block_tip_x` (distance
  du tour gauche à la face saumon). `wire_span` est la distance entre les
  deux tours.

Pour chaque indice i, le fil traverse la mousse au point P_root[i] côté
emplanture et P_tip[i] côté saumon. Les chariots vont à la projection :

  P_left  = P_root + (P_root - P_tip) * (d_left / L_block)
  P_right = P_tip  + (P_tip - P_root) * (d_right / L_block)

avec d_left = block_root_x, d_right = wire_span - block_tip_x,
     L_block = block_tip_x - block_root_x.
"""

from __future__ import annotations

from dataclasses import dataclass

from .profiles import Profile, resample


@dataclass
class CutGeometry:
    wire_span: float        # distance entre les deux tours (mm)
    block_root_x: float     # distance du tour gauche à la face emplanture (mm)
    block_tip_x: float      # distance du tour gauche à la face saumon (mm)


@dataclass
class CutParams:
    feed: float = 200.0          # mm/min
    hot_wire_s: int = 500        # valeur S pour M3
    leadin_mm: float = 20.0      # longueur d'attaque hors profil
    leadout_mm: float = 20.0     # longueur de sortie hors profil
    n_resample: int = 200        # points par profil
    safe_x: float = 0.0          # X de retour en sécurité
    safe_y: float = 80.0         # Y de retour en sécurité (dégagé du bloc)


def project(
    root: Profile,
    tip: Profile,
    geom: CutGeometry,
) -> list[tuple[float, float, float, float]]:
    """Retourne la liste des positions (X, Y, Z, A) des deux chariots
    pour chaque point indexé des deux profils (qui doivent être de même taille).
    """
    if root.n != tip.n:
        raise ValueError(
            f"Profils de tailles différentes (root={root.n}, tip={tip.n}). "
            "Re-échantillonner avant projection."
        )
    L_block = geom.block_tip_x - geom.block_root_x
    if L_block <= 0:
        raise ValueError("block_tip_x doit être > block_root_x")
    d_left = geom.block_root_x
    d_right = geom.wire_span - geom.block_tip_x
    out: list[tuple[float, float, float, float]] = []
    for (xr, yr), (xt, yt) in zip(root.points, tip.points):
        # Projection chariot gauche (X,Y)
        kl = d_left / L_block
        x_l = xr + (xr - xt) * kl
        y_l = yr + (yr - yt) * kl
        # Projection chariot droit (Z,A)
        kr = d_right / L_block
        x_r = xt + (xt - xr) * kr
        y_r = yt + (yt - yr) * kr
        out.append((x_l, y_l, x_r, y_r))
    return out


def _format_g1(x_l: float, y_l: float, x_r: float, y_r: float, feed: float | None = None) -> str:
    """Sort une ligne `G1` avec la convention machine :
    - chariot gauche : G-code X = corde, Y = épaisseur
    - chariot droit  : G-code A = corde, Z = épaisseur
    """
    parts = [f"X{x_l:.3f}", f"Y{y_l:.3f}", f"A{x_r:.3f}", f"Z{y_r:.3f}"]
    if feed is not None:
        parts.append(f"F{int(feed)}")
    return "G1 " + " ".join(parts)


def generate_gcode(
    root: Profile,
    tip: Profile,
    geom: CutGeometry,
    params: CutParams,
) -> list[str]:
    """Génère le programme complet : préambule, attaque, contour, sortie, postambule."""
    rs = resample(root, params.n_resample)
    ts = resample(tip, params.n_resample)
    pts = project(rs, ts, geom)
    if not pts:
        return []

    lines: list[str] = []
    lines.append(f"; HotWire Sender — slicer 4 axes")
    lines.append(f"; Profil emplanture : {root.name}")
    lines.append(f"; Profil saumon    : {tip.name}")
    lines.append(f"; Bloc : root_x={geom.block_root_x:.1f} tip_x={geom.block_tip_x:.1f} wire={geom.wire_span:.1f}")
    lines.append(f"; Avance F={params.feed:.0f} mm/min, fil chaud S={params.hot_wire_s}")
    lines.append("G21 G90 G94")  # mm, absolu, feed mm/min

    # pts[i] = (x_l, y_l, x_r, y_r) = (corde gauche, épaisseur gauche,
    #                                  corde droite, épaisseur droite)
    x_l0, y_l0, x_r0, y_r0 = pts[0]

    # 1. Position de sécurité au-dessus du profil (dégagement vertical)
    lines.append(
        f"G0 X{x_l0:.3f} Y{params.safe_y:.3f} A{x_r0:.3f} Z{params.safe_y:.3f}"
    )

    # 2. Lead-in : on descend de `leadin_mm` au-dessus du 1er point
    lead_yL = y_l0 + params.leadin_mm
    lead_yR = y_r0 + params.leadin_mm
    lines.append(f"G0 X{x_l0:.3f} Y{lead_yL:.3f} A{x_r0:.3f} Z{lead_yR:.3f}")

    # 3. Allume le fil chaud
    lines.append(f"M3 S{params.hot_wire_s}")
    # 4. Plonge dans le profil à l'avance de coupe
    lines.append(_format_g1(x_l0, y_l0, x_r0, y_r0, params.feed))

    # 5. Suit le profil
    for x_l, y_l, x_r, y_r in pts[1:]:
        lines.append(_format_g1(x_l, y_l, x_r, y_r))

    # 6. Lead-out vers le haut depuis le dernier point
    x_lN, y_lN, x_rN, y_rN = pts[-1]
    lines.append(
        _format_g1(x_lN, y_lN + params.leadout_mm, x_rN, y_rN + params.leadout_mm)
    )
    # 7. Coupe le fil chaud
    lines.append("M5")
    # 8. Retour à la position de sécurité
    lines.append(
        f"G0 X{params.safe_x:.3f} Y{params.safe_y:.3f} "
        f"A{params.safe_x:.3f} Z{params.safe_y:.3f}"
    )
    lines.append("M2")
    return lines
