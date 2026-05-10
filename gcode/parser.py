"""Parser G-code minimaliste pour la visualisation 2D.

On ne supporte que ce qu'il faut pour tracer les chemins XY et ZA :
- G0/G1 (déplacements rectilignes) en absolu/relatif (G90/G91)
- mots d'axes X, Y, Z, A
- commentaires `;...` et `(...)`

Le parser ne gère pas G2/G3 pour la visu (la machine fil chaud ne les utilise
quasiment pas en pratique). On peut compléter en P1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

WORD_RE = re.compile(r"([A-Za-z])\s*(-?\d*\.?\d+)")


@dataclass
class Move:
    line_no: int
    rapid: bool
    pos: dict[str, float]
    feed: float = 0.0  # mm/min, valeur F modale courante (ignorée si rapid=True)


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
