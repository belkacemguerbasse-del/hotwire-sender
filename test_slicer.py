"""Test rapide du slicer sur un profil NACA0012 inline (Selig)."""

import sys
sys.path.insert(0, ".")

from gcode.profiles import Profile, transform, resample
from gcode.slicer import CutGeometry, CutParams, generate_gcode

# NACA 0012 simplifié — quelques points (Selig: TE -> top -> LE -> bot -> TE)
naca0012_pts = [
    (1.000, 0.001),
    (0.900, 0.020),
    (0.700, 0.045),
    (0.500, 0.057),
    (0.300, 0.060),
    (0.150, 0.052),
    (0.050, 0.034),
    (0.010, 0.016),
    (0.000, 0.000),
    (0.010, -0.016),
    (0.050, -0.034),
    (0.150, -0.052),
    (0.300, -0.060),
    (0.500, -0.057),
    (0.700, -0.045),
    (0.900, -0.020),
    (1.000, -0.001),
    (1.000, 0.001),  # fermeture
]

root = Profile(name="NACA0012-root", points=naca0012_pts)
tip = Profile(name="NACA0012-tip", points=naca0012_pts)

# Emplanture: corde 200 mm, saumon: corde 120 mm avec 2° de twist
root_t = transform(root, chord_mm=200.0, offset_x=0, offset_y=0, twist_deg=0)
tip_t = transform(tip, chord_mm=120.0, offset_x=0, offset_y=0, twist_deg=2)

geom = CutGeometry(wire_span=1000.0, block_root_x=150.0, block_tip_x=850.0)
params = CutParams(feed=200.0, hot_wire_s=500, leadin_mm=20, leadout_mm=20, n_resample=80)

lines = generate_gcode(root_t, tip_t, geom, params)
print(f"Généré {len(lines)} lignes G-code")
for ln in lines[:10]:
    print(" ", ln)
print(" ...")
for ln in lines[-5:]:
    print(" ", ln)

# Vérifie que le G-code est ré-injectable dans notre parser
from gcode.parser import parse_program
parsed = parse_program("\n".join(lines))
print(f"Parser a vu {len(parsed.moves)} déplacements")
print(f"Étendue XY : {parsed.extents_xy}")
print(f"Étendue ZA : {parsed.extents_za}")
