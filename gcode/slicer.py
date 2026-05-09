"""Slicer fil chaud : projection de profils sur 4 axes (X,Y,Z,A).

Convention :
- chariot gauche = (X, Y) ; chariot droit = (A, Z)
- les profils sont en mm, déjà transformés (corde, twist, offset)
- le bloc de mousse est positionné entre les deux tours selon `block_root_x`
  (distance du tour gauche à la face emplanture) et `block_tip_x` (distance
  du tour gauche à la face saumon). `wire_span` = distance entre les tours.

Pour chaque indice i, le fil traverse la mousse au point P_root[i] côté
emplanture et P_tip[i] côté saumon. Les chariots vont à la projection :
  P_left  = P_root + (P_root - P_tip) * (d_left / L_block)
  P_right = P_tip  + (P_tip - P_root) * (d_right / L_block)

avec d_left = block_root_x, d_right = wire_span - block_tip_x,
     L_block = block_tip_x - block_root_x.

Pour une aile multi-panneaux, chaque panneau est traité individuellement avec
la même géométrie machine, et l'utilisateur change de bloc entre panneaux.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .profiles import Profile, resample
from .wing import Section, WingDefinition


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
    """Retourne les positions (X, Y, Z, A) des chariots pour chaque indice
    des deux profils (qui doivent être de même taille)."""
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
        kl = d_left / L_block
        x_l = xr + (xr - xt) * kl
        y_l = yr + (yr - yt) * kl
        kr = d_right / L_block
        x_r = xt + (xt - xr) * kr
        y_r = yt + (yt - yr) * kr
        out.append((x_l, y_l, x_r, y_r))
    return out


def _format_g1(x_l: float, y_l: float, x_r: float, y_r: float, feed: float | None = None) -> str:
    """Sort une ligne `G1` avec convention machine :
    chariot gauche : G-code X = corde, Y = épaisseur
    chariot droit  : G-code A = corde, Z = épaisseur"""
    parts = [f"X{x_l:.3f}", f"Y{y_l:.3f}", f"A{x_r:.3f}", f"Z{y_r:.3f}"]
    if feed is not None:
        parts.append(f"F{int(feed)}")
    return "G1 " + " ".join(parts)


def _generate_panel_body(
    root: Profile,
    tip: Profile,
    geom: CutGeometry,
    params: CutParams,
) -> list[str]:
    """Lignes G-code pour UN panneau : safe → lead-in → M3 → contour → lead-out → M5.
    Pas de préambule/postambule (G21 G90 G94 / M2). À encapsuler par l'appelant."""
    rs = resample(root, params.n_resample)
    ts = resample(tip, params.n_resample)
    pts = project(rs, ts, geom)
    if not pts:
        return []

    lines: list[str] = []
    x_l0, y_l0, x_r0, y_r0 = pts[0]

    # Position de sécurité au-dessus du profil
    lines.append(
        f"G0 X{x_l0:.3f} Y{params.safe_y:.3f} A{x_r0:.3f} Z{params.safe_y:.3f}"
    )
    # Lead-in
    lead_yL = y_l0 + params.leadin_mm
    lead_yR = y_r0 + params.leadin_mm
    lines.append(f"G0 X{x_l0:.3f} Y{lead_yL:.3f} A{x_r0:.3f} Z{lead_yR:.3f}")
    # Allume fil
    lines.append(f"M3 S{params.hot_wire_s}")
    # Plonge à vitesse de coupe
    lines.append(_format_g1(x_l0, y_l0, x_r0, y_r0, params.feed))
    # Suit le contour
    for x_l, y_l, x_r, y_r in pts[1:]:
        lines.append(_format_g1(x_l, y_l, x_r, y_r))
    # Lead-out
    x_lN, y_lN, x_rN, y_rN = pts[-1]
    lines.append(
        _format_g1(x_lN, y_lN + params.leadout_mm, x_rN, y_rN + params.leadout_mm)
    )
    # Coupe fil
    lines.append("M5")
    return lines


def generate_gcode(
    root: Profile,
    tip: Profile,
    geom: CutGeometry,
    params: CutParams,
) -> list[str]:
    """Génère un programme complet pour UN seul panneau (rétrocompat)."""
    body = _generate_panel_body(root, tip, geom, params)
    if not body:
        return []
    out: list[str] = []
    out.append("; HotWire Sender — slicer 4 axes")
    out.append(f"; Profil emplanture : {root.name}")
    out.append(f"; Profil saumon    : {tip.name}")
    out.append(f"; Bloc : root_x={geom.block_root_x:.1f} tip_x={geom.block_tip_x:.1f} wire={geom.wire_span:.1f}")
    out.append(f"; Avance F={params.feed:.0f} mm/min, fil chaud S={params.hot_wire_s}")
    out.append("G21 G90 G94")
    out.extend(body)
    # Retour à la position de sécurité
    out.append(
        f"G0 X{params.safe_x:.3f} Y{params.safe_y:.3f} "
        f"A{params.safe_x:.3f} Z{params.safe_y:.3f}"
    )
    out.append("M2")
    return out


def generate_gcode_wing(
    wing: WingDefinition,
    geom: CutGeometry,
    params: CutParams,
    mode: Literal["single", "split"] = "single",
) -> list[str] | list[list[str]]:
    """Génère le G-code pour une aile multi-panneaux.

    - mode='single' : un seul programme avec M0 (pause user) entre panneaux,
                      pour repositionner le bloc de mousse manuellement.
    - mode='split'  : retourne une liste de programmes (un par panneau).
    """
    if wing.n_panels == 0:
        return [] if mode == "split" else []

    # Profils transformés pour chaque section
    transformed = [s.transformed() for s in wing.sections]
    if any(p is None for p in transformed):
        raise ValueError("Toutes les sections doivent avoir un profil chargé.")

    if mode == "split":
        out_files: list[list[str]] = []
        for i in range(wing.n_panels):
            sa = wing.sections[i]
            sb = wing.sections[i + 1]
            body = _generate_panel_body(transformed[i], transformed[i + 1], geom, params)
            if not body:
                continue
            prog: list[str] = []
            prog.append("; HotWire Sender — aile multi-panneaux")
            prog.append(f"; Panneau {i + 1}/{wing.n_panels}")
            prog.append(f"; Section gauche : {sa.profile_name} - corde {sa.chord_mm:.1f} mm - twist {sa.twist_deg:+.1f}°")
            prog.append(f"; Section droite : {sb.profile_name} - corde {sb.chord_mm:.1f} mm - twist {sb.twist_deg:+.1f}°")
            prog.append(f"; Envergure de ce panneau : {sb.span_y_mm - sa.span_y_mm:.1f} mm")
            prog.append(f"; Bloc machine : root_x={geom.block_root_x:.1f} tip_x={geom.block_tip_x:.1f} wire={geom.wire_span:.1f}")
            prog.append(f"; Avance F={params.feed:.0f} mm/min, fil chaud S={params.hot_wire_s}")
            prog.append("G21 G90 G94")
            prog.extend(body)
            prog.append(
                f"G0 X{params.safe_x:.3f} Y{params.safe_y:.3f} "
                f"A{params.safe_x:.3f} Z{params.safe_y:.3f}"
            )
            prog.append("M2")
            out_files.append(prog)
        return out_files

    # mode='single' : 1 fichier avec pauses M0 entre panneaux
    out: list[str] = []
    out.append("; HotWire Sender — aile multi-panneaux (mode continu)")
    out.append(f"; {wing.n_sections} sections, {wing.n_panels} panneau(x)")
    out.append(f"; Envergure totale : {wing.total_span_mm:.1f} mm")
    for i, s in enumerate(wing.sections):
        out.append(
            f"; Section {i} : {s.profile_name} - Y={s.span_y_mm:.1f} mm - "
            f"corde {s.chord_mm:.1f} mm - twist {s.twist_deg:+.1f}° - "
            f"offset (X={s.offset_x_mm:+.1f}, Y={s.offset_y_mm:+.1f})"
        )
    out.append(f"; Bloc machine : root_x={geom.block_root_x:.1f} tip_x={geom.block_tip_x:.1f} wire={geom.wire_span:.1f}")
    out.append(f"; Avance F={params.feed:.0f} mm/min, fil chaud S={params.hot_wire_s}")
    out.append("G21 G90 G94")

    for i in range(wing.n_panels):
        out.append("")
        out.append(f"; ========== Panneau {i + 1}/{wing.n_panels} ==========")
        body = _generate_panel_body(transformed[i], transformed[i + 1], geom, params)
        if not body:
            continue
        out.extend(body)
        if i < wing.n_panels - 1:
            out.append(
                f"G0 X{params.safe_x:.3f} Y{params.safe_y:.3f} "
                f"A{params.safe_x:.3f} Z{params.safe_y:.3f}"
            )
            # Pause logicielle : le JobRunner s'arrête sur cette ligne et
            # affiche un dialog modal. Pas de M0 firmware (comportement
            # imprévisible selon les builds Grbl).
            out.append(
                f"; @HW_PAUSE: Repositionner le bloc de mousse pour le "
                f"panneau {i + 2}/{wing.n_panels}, puis cliquez OK pour continuer."
            )
    out.append(
        f"G0 X{params.safe_x:.3f} Y{params.safe_y:.3f} "
        f"A{params.safe_x:.3f} Z{params.safe_y:.3f}"
    )
    out.append("M2")
    return out
