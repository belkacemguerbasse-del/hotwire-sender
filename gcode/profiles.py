"""Chargement et transformations de profils d'aile.

Supporte le format Selig (.dat) — le plus courant. Détection auto du format
Lednicer (header avec 2 entiers, surface haute puis basse).

Un Profile est une polyline 2D fermée allant du bord de fuite (TE) au TE en
passant par le bord d'attaque (LE), dans le sens horaire ou trigonométrique
selon le fichier source. On normalise toujours en sens horaire (TE -> top -> LE
-> bottom -> TE).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class Profile:
    name: str
    points: list[tuple[float, float]]  # x, y

    @property
    def n(self) -> int:
        return len(self.points)

    def copy(self) -> "Profile":
        return Profile(name=self.name, points=list(self.points))


def _parse_floats(line: str) -> list[float]:
    out = []
    for tok in line.replace(",", " ").split():
        try:
            out.append(float(tok))
        except ValueError:
            pass
    return out


def load_profile(path: str) -> Profile:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        raw_lines = [ln.strip() for ln in f.readlines()]

    name = ""
    data_lines: list[str] = []
    for ln in raw_lines:
        if not ln:
            continue
        floats = _parse_floats(ln)
        if len(floats) >= 2:
            data_lines.append(ln)
        else:
            if not name:
                name = ln

    if not name:
        name = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].rsplit(".", 1)[0]

    # Détection Lednicer : la 1ère ligne data a un seul "couple" qui ressemble
    # à 2 entiers genre "61. 61." (nb pts surface haute + basse)
    first_floats = _parse_floats(data_lines[0])
    is_lednicer = (
        len(first_floats) == 2
        and abs(first_floats[0] - round(first_floats[0])) < 1e-6
        and abs(first_floats[1] - round(first_floats[1])) < 1e-6
        and first_floats[0] > 1.5
        and first_floats[1] > 1.5
    )

    pts: list[tuple[float, float]] = []
    if is_lednicer:
        n_top = int(round(first_floats[0]))
        n_bot = int(round(first_floats[1]))
        body = data_lines[1:]
        top = [tuple(_parse_floats(ln)[:2]) for ln in body[:n_top]]
        bot = [tuple(_parse_floats(ln)[:2]) for ln in body[n_top : n_top + n_bot]]
        # Lednicer: top va de LE -> TE, bot va de LE -> TE
        # On veut TE -> top -> LE -> bot -> TE
        top_rev = list(reversed(top))           # TE -> LE (top)
        bot_no_le = bot[1:] if bot and bot[0] == top[0] else bot
        pts = top_rev + bot_no_le
    else:
        for ln in data_lines:
            f = _parse_floats(ln)
            if len(f) >= 2:
                pts.append((f[0], f[1]))

    return Profile(name=name, points=_normalize_orientation(pts))


def _normalize_orientation(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Force le profil à commencer/finir au TE et à parcourir top -> LE -> bot."""
    if len(pts) < 3:
        return pts
    # Trouve l'index du LE (point au x minimal)
    min_idx = min(range(len(pts)), key=lambda i: pts[i][0])
    # Si le LE est au milieu et y au début est positif, on est en convention Selig
    # avec sens trigonométrique. Sinon on retourne.
    # Heuristique simple: regarder la moyenne des y entre point 0 et le LE.
    half_top = sum(p[1] for p in pts[:min_idx]) / max(1, min_idx)
    if half_top < 0:
        # On est en convention "TE -> bot -> LE -> top -> TE", on inverse.
        pts = list(reversed(pts))
    # Assure fermeture (point final = point initial)
    if pts and pts[0] != pts[-1]:
        pts.append(pts[0])
    return pts


def transform(
    p: Profile,
    chord_mm: float = 100.0,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    twist_deg: float = 0.0,
    pivot_xc: float = 0.25,  # pivot de twist en fraction de corde (0=LE, 1=TE)
) -> Profile:
    """Profil normalisé (corde unité) -> profil échelle/rotation/translation."""
    cos_t = math.cos(math.radians(twist_deg))
    sin_t = math.sin(math.radians(twist_deg))
    px = pivot_xc
    py = 0.0
    out: list[tuple[float, float]] = []
    for x, y in p.points:
        # Rotation autour du pivot, en coordonnées normalisées
        dx = x - px
        dy = y - py
        rx = dx * cos_t - dy * sin_t + px
        ry = dx * sin_t + dy * cos_t + py
        # Échelle par corde + offset
        out.append((rx * chord_mm + offset_x, ry * chord_mm + offset_y))
    return Profile(name=p.name, points=out)


def resample(p: Profile, n_points: int) -> Profile:
    """Re-échantillonne le profil avec n_points équirépartis en longueur d'arc."""
    if p.n < 2 or n_points < 2:
        return p.copy()
    # Distances cumulées
    cum = [0.0]
    for i in range(1, p.n):
        x0, y0 = p.points[i - 1]
        x1, y1 = p.points[i]
        d = math.hypot(x1 - x0, y1 - y0)
        cum.append(cum[-1] + d)
    total = cum[-1]
    if total <= 0:
        return p.copy()

    out: list[tuple[float, float]] = []
    j = 0
    for k in range(n_points):
        t = (k / (n_points - 1)) * total
        while j < len(cum) - 2 and cum[j + 1] < t:
            j += 1
        seg = cum[j + 1] - cum[j]
        if seg <= 0:
            out.append(p.points[j])
            continue
        u = (t - cum[j]) / seg
        x0, y0 = p.points[j]
        x1, y1 = p.points[j + 1]
        out.append((x0 + (x1 - x0) * u, y0 + (y1 - y0) * u))
    return Profile(name=p.name, points=out)


def kerf_offset(p: Profile, offset_mm: float) -> Profile:
    """Décale chaque point selon la normale extérieure d'une distance `offset_mm`.
    Positif = vers l'extérieur (compense le sillage du fil chaud)."""
    if p.n < 3 or abs(offset_mm) < 1e-9:
        return p.copy()
    pts = p.points
    out: list[tuple[float, float]] = []
    closed = pts[0] == pts[-1]
    for i in range(len(pts)):
        if closed and i == len(pts) - 1:
            out.append(out[0])
            break
        prev_i = (i - 1) % (len(pts) - (1 if closed else 0))
        next_i = (i + 1) % (len(pts) - (1 if closed else 0))
        x0, y0 = pts[prev_i]
        x1, y1 = pts[i]
        x2, y2 = pts[next_i]
        # Tangente moyenne
        tx = x2 - x0
        ty = y2 - y0
        norm = math.hypot(tx, ty)
        if norm < 1e-12:
            out.append((x1, y1))
            continue
        # Normale "extérieure" pour un parcours horaire = (ty, -tx) / norm
        nx = ty / norm
        ny = -tx / norm
        out.append((x1 + nx * offset_mm, y1 + ny * offset_mm))
    return Profile(name=p.name, points=out)
