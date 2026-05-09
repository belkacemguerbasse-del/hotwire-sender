# HotWire Sender

Logiciel de pilotage pour CNC à fil chaud 4 axes (X Y Z A) basée sur le firmware
[grbl-Mega-5X](https://github.com/fra589/grbl-Mega-5X).

Remplace / complète l'application historique *Grbl HotWire Mega 5X*.

## Cinématique

- **Chariot gauche** : `X` (horizontal) + `Y` (vertical)
- **Chariot droit**  : `Z` (horizontal) + `A` (vertical)
- Profil emplanture sur graphe **XY**, profil saumon sur graphe **ZA**.

## Installation

```powershell
cd c:\Users\kaiez\hotwire-sender
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## Architecture

```
core/        Lien Grbl (série + character-counting streamer + parser status)
gcode/       Parser G-code et (P2) slicer 2 profils
ui/          Fenêtre principale et widgets
```

## État

- **P0 (livré)** : connexion série, DRO 4 axes, jog 3 pavés, streamer G-code,
  logs verbose, contrôle fil chaud, overrides, MDI, visualisation XY/ZA.
- **P1** : édition `$$`, macros utilisateur.
- **P2** : slicer 2 profils `.dat` → G-code 4 axes synchronisé.
