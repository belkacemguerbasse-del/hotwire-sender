"""Parser G-code minimaliste pour la visualisation 2D.

On ne supporte que ce qu'il faut pour tracer les chemins XY et ZA :
- G0/G1 (déplacements rectilignes) en absolu/relatif (G90/G91)
- mots d'axes X, Y, Z, A
- commentaires `;...` et `(...)`
- M3/M5 pour suivre l'état du fil chaud (wire_on flag par move)
- F modal (feed rate)

Le parser ne gère pas G2/G3 pour la visu (la machine fil chaud ne les utilise
quasiment pas en pratique). On peut compléter en P1.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

WORD_RE = re.compile(r"([A-Za-z])\s*(-?\d*\.?\d+)")


@dataclass
class Move:
    line_no: int
    rapid: bool
    pos: dict[str, float]
    feed: float = 0.0      # mm/min, valeur F modale courante (ignorée si rapid=True)
    wire_on: bool = False  # M3 actif pendant ce déplacement


@dataclass
class ParseResult:
    moves: list[Move] = field(default_factory=list)
    extents_xy: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    extents_za: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)


def _strip_comments(line: str) -> str:
    out = []
    depth = 0
    for ch in line:
        if ch == "(":
            depth += 1
            continue
        if ch == ")":
            depth = max(0, depth - 1)
            continue
        if depth == 0:
            if ch == ";":
                break
            out.append(ch)
    return "".join(out)


def parse_program(text: str) -> ParseResult:
    cur = {"X": 0.0, "Y": 0.0, "Z": 0.0, "A": 0.0}
    absolute = True
    motion = "G0"
    feed = 0.0  # F modal en mm/min
    wire_on = False  # état modal M3/M5
    moves: list[Move] = []

    for i, raw in enumerate(text.splitlines(), start=1):
        body = _strip_comments(raw).strip()
        if not body:
            continue
        words = WORD_RE.findall(body)
        if not words:
            continue
        target_words: dict[str, float] = {}
        for letter, value in words:
            L = letter.upper()
            try:
                v = float(value)
            except ValueError:
                continue
            if L == "G":
                code = int(round(v))
                if code in (0, 1):
                    motion = f"G{code}"
                elif code == 90:
                    absolute = True
                elif code == 91:
                    absolute = False
            elif L == "M":
                code = int(round(v))
                if code == 3 or code == 4:
                    wire_on = True
                elif code == 5 or code == 30 or code == 2:
                    wire_on = False
            elif L == "F":
                feed = v
            elif L in cur:
                target_words[L] = v

        if not target_words:
            continue

        new_pos = dict(cur)
        if absolute:
            for L, v in target_words.items():
                new_pos[L] = v
        else:
            for L, v in target_words.items():
                new_pos[L] = cur[L] + v

        if new_pos != cur:
            is_rapid = (motion == "G0")
            moves.append(
                Move(
                    line_no=i,
                    rapid=is_rapid,
                    pos=dict(new_pos),
                    feed=0.0 if is_rapid else feed,
                    wire_on=wire_on,
                )
            )
            cur = new_pos

    if moves:
        xs = [m.pos["X"] for m in moves]
        ys = [m.pos["Y"] for m in moves]
        zs = [m.pos["Z"] for m in moves]
        as_ = [m.pos["A"] for m in moves]
        extents_xy = (min(xs), min(ys), max(xs), max(ys))
        extents_za = (min(zs), min(as_), max(zs), max(as_))
    else:
        extents_xy = extents_za = (0.0, 0.0, 0.0, 0.0)

    return ParseResult(moves=moves, extents_xy=extents_xy, extents_za=extents_za)


def estimate_program(
    parsed: ParseResult,
    rapid_mm_min: float = 1500.0,
    default_feed_mm_min: float = 200.0,
) -> dict:
    """Estime la durée et la longueur de trajet d'un programme G-code.

    Retourne un dict :
      total_time_s     : durée totale estimée en secondes
      total_length_mm  : longueur totale parcourue (G0+G1)
      cut_length_mm    : longueur en coupe (G1, fil chaud actif)
      wire_length_mm   : longueur où le fil est actif (M3..M5)
      n_moves          : nombre de mouvements
    """
    total_time_s = 0.0
    total_length_mm = 0.0
    cut_length_mm = 0.0
    wire_length_mm = 0.0
    prev = (0.0, 0.0, 0.0, 0.0)
    for m in parsed.moves:
        end = (m.pos["X"], m.pos["Y"], m.pos["Z"], m.pos["A"])
        dist = math.sqrt(sum((end[i] - prev[i]) ** 2 for i in range(4)))
        total_length_mm += dist
        if not m.rapid:
            cut_length_mm += dist
        if m.wire_on:
            wire_length_mm += dist
        feed = rapid_mm_min if m.rapid else (m.feed if m.feed > 0 else default_feed_mm_min)
        if feed > 0:
            total_time_s += dist / (feed / 60.0)
        prev = end
    return {
        "total_time_s": total_time_s,
        "total_length_mm": total_length_mm,
        "cut_length_mm": cut_length_mm,
        "wire_length_mm": wire_length_mm,
        "n_moves": len(parsed.moves),
    }
