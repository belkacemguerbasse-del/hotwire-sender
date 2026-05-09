"""Extraction one-shot de la base Profili 2 Pro vers des fichiers .dat Selig.

Usage :
    python tools/extract_profili.py [chemin/vers/ProfiliProNoPolar.mdb]

Si le chemin n'est pas fourni, utilise le défaut du user :
    C:\\Users\\kaiez\\grbl-Mega-5X\\data\\ProfiliProNoPolar.mdb

Sortie : `resources/airfoils/<id>_<nom_safe>.dat` + `_index.json`.

Format Selig écrit :
    <ligne 1 : nom du profil>
    1.000  0.001
    ...   ...     ← extrados (TE → LE)
    0.000  0.000   ← LE
    ...            ← intrados (LE → TE)
    1.000 -0.001
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pyodbc

DEFAULT_MDB = r"C:\Users\kaiez\grbl-Mega-5X\data\ProfiliProNoPolar.mdb"

# Chemin de sortie : resources/airfoils/ relatif au projet
THIS_DIR = Path(__file__).resolve().parent
OUT_DIR = THIS_DIR.parent / "resources" / "airfoils"


def safe_filename(name: str) -> str:
    """Garde une chaîne utilisable comme nom de fichier sur Windows."""
    s = name.strip()
    # Remplace les caractères interdits par _
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s)
    # Compresse les espaces et tirets multiples
    s = re.sub(r"\s+", " ", s)
    # Limite la longueur
    return s[:80].strip(" .") or "profil"


def fetch_profiles(cn) -> list[dict]:
    cur = cn.cursor()
    cur.execute(
        "SELECT Id, Nome, Note, MaxWidth, MaxWidthSuCorda, "
        "MaxCamber, MaxCamberSuCorda FROM Profili ORDER BY Nome"
    )
    rows = []
    for r in cur.fetchall():
        rows.append({
            "id": int(r[0]),
            "nome": (r[1] or "").strip(),
            "note": (r[2] or "").strip(),
            "max_width_pct": float(r[3]) if r[3] is not None else None,
            "max_width_pos": float(r[4]) if r[4] is not None else None,
            "max_camber_pct": float(r[5]) if r[5] is not None else None,
            "max_camber_pos": float(r[6]) if r[6] is not None else None,
        })
    return rows


def fetch_coordinates_grouped(cn) -> dict[int, dict[int, list[tuple[float, float]]]]:
    """Retourne {fk_id : {flag : [(x, y), ...]}} où flag 0=sopra(haut), 1=sotto(bas).

    On ordonne ici dans le sens naturel pour la base, on retriera côté Selig.
    """
    cur = cn.cursor()
    cur.execute(
        "SELECT Fk_Id_Profilo, FlagSopraSotto, X, Y FROM Coordinate "
        "ORDER BY Fk_Id_Profilo, FlagSopraSotto, X"
    )
    out: dict[int, dict[int, list]] = {}
    for fk, flag, x, y in cur.fetchall():
        if x is None or y is None:
            continue
        out.setdefault(int(fk), {0: [], 1: []}).setdefault(int(flag), []).append(
            (float(x), float(y))
        )
    return out


def to_selig(haut: list[tuple[float, float]], bas: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Construit la polyline Selig : TE → top → LE → bot → TE.

    `haut` et `bas` arrivent triés par X croissant et en POURCENTAGE de corde
    (Profili stocke X,Y de 0 à 100). On normalise en 0..1 pour le format
    Selig standard.

    - extrados parcourue de TE (X=1) à LE (X=0) → on inverse `haut`
    - intrados parcourue de LE (X=0) à TE (X=1) → on garde `bas` tel quel
    - on enlève le doublon au LE
    """
    if not haut and not bas:
        return []
    # Normalise pourcentage → fraction de corde (Selig standard)
    haut_n = [(x / 100.0, y / 100.0) for x, y in haut]
    bas_n = [(x / 100.0, y / 100.0) for x, y in bas]
    top_rev = list(reversed(haut_n))  # X décroissant
    if top_rev and bas_n and abs(top_rev[-1][0] - bas_n[0][0]) < 1e-9 \
            and abs(top_rev[-1][1] - bas_n[0][1]) < 1e-9:
        bas_clean = bas_n[1:]
    else:
        bas_clean = bas_n
    return top_rev + bas_clean


def write_selig(path: Path, name: str, points: list[tuple[float, float]]) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"{name}\n")
        for x, y in points:
            f.write(f"{x:>10.6f}  {y:>10.6f}\n")


def main(mdb_path: str = DEFAULT_MDB) -> int:
    mdb = Path(mdb_path)
    if not mdb.exists():
        print(f"[ERREUR] Fichier introuvable : {mdb}")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Connexion à {mdb} …")
    conn_str = (
        f"DRIVER={{Microsoft Access Driver (*.mdb, *.accdb)}};"
        f"DBQ={mdb};"
    )
    cn = pyodbc.connect(conn_str)

    print("Lecture des métadonnées Profili …")
    profiles = fetch_profiles(cn)
    print(f"  {len(profiles)} profils trouvés")

    print("Lecture des coordonnées (177 710 points attendus) …")
    coords = fetch_coordinates_grouped(cn)
    print(f"  {len(coords)} profils ont des coordonnées")

    cn.close()

    print(f"Écriture dans {OUT_DIR} …")
    written = 0
    skipped = 0
    index = []
    for p in profiles:
        pid = p["id"]
        if pid not in coords:
            skipped += 1
            continue
        groups = coords[pid]
        haut = sorted(groups.get(0, []), key=lambda t: t[0])
        bas = sorted(groups.get(1, []), key=lambda t: t[0])
        pts = to_selig(haut, bas)
        if len(pts) < 5:
            skipped += 1
            continue
        fname = f"{pid:04d}_{safe_filename(p['nome'])}.dat"
        path = OUT_DIR / fname
        write_selig(path, p["nome"], pts)
        index.append({
            **p,
            "file": fname,
            "n_points": len(pts),
        })
        written += 1
        if written % 200 == 0:
            print(f"  … {written} profils écrits")

    # Index JSON pour usage UI (sélecteur, filtre, recherche)
    idx_path = OUT_DIR / "_index.json"
    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump({"count": len(index), "profiles": index}, f, ensure_ascii=False, indent=1)

    print()
    print(f"=== Terminé ===")
    print(f"  écrits  : {written}")
    print(f"  ignorés : {skipped}")
    print(f"  index   : {idx_path}")
    return 0


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MDB
    sys.exit(main(arg))
