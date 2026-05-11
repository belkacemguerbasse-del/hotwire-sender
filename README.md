# HotWire Sender

Application de pilotage moderne pour CNC à fil chaud 4 axes (X Y Z A) basée sur le
firmware [grbl-Mega-5X](https://github.com/fra589/grbl-Mega-5X) (Arduino Mega 2560
+ RAMPS 1.4).

Écrite en Python / PySide6, conçue pour remplacer / dépasser l'application
historique *Grbl HotWire Mega 5X* de RC Keith.

> Interface FR / EN · thèmes clair & sombre · slicer 2 profils intégré · simulation
> 3D · estimation de coupe · export PDF · historique des jobs · webcam avec OSD.

## Cinématique

- **Chariot gauche** : `X` (corde, horizontal) + `Y` (épaisseur, vertical)
- **Chariot droit**  : `A` (corde, horizontal) + `Z` (épaisseur, vertical)
- Profil emplanture sur le graphe **XY**, profil saumon sur le graphe **ZA**.

## Fonctionnalités

- **Connexion série** robuste avec délai bootloader Mega configurable (stk500v2).
- **DRO 4 axes** grand format avec code couleur par axe.
- **Jog** : 3 pavés directionnels (gauche, sync, droit), distances et vitesses
  configurables, contrôle clavier optionnel.
- **Streamer G-code** character-counting (RX buffer 255 B), pause/reprise logicielle,
  surlignage de la ligne courante, watchdog firmware.
- **Visualisation 3D** : aperçu fil de chauffe, simulation visuelle, vue de coupe
  interpolée entre les deux profils.
- **Slicer 2 profils** : import `.dat` Selig ou base Profili Pro (2383 profils),
  génération G-code 4 axes synchronisé avec lead-in/out, kerf adaptatif selon la
  vitesse, twist, offsets, n_resample, sauvegarde projet `.hwproj`.
- **Fil chaud** : slider PWM + gros bouton ON/OFF, indicateur d'état.
- **Overrides Grbl 1.1** : feed / spindle ± 1/10%.
- **MDI** avec historique haut/bas.
- **Réglages firmware `$$`** : éditeur avec recherche, tri, tooltip par paramètre.
- **Macros utilisateur** persistantes.
- **Historique des jobs** avec rejouer / supprimer.
- **Notifications Windows** (tray) à la fin d'un job.
- **Webcam** avec OSD compositée Qt (état, temps écoulé, ligne courante).
- **Export PDF** : fiche de coupe avec géométrie, sections, paramètres,
  estimations.
- **Multi-langue** : Français / English.
- **Thèmes** : clair / sombre, bascule à chaud.

## Captures d'écran

_(à venir — ajouter des screenshots dans `docs/screenshots/` et les référencer ici)_

## Installation

Prérequis : **Python ≥ 3.10**, Windows 10/11 ou Linux.

```powershell
git clone https://github.com/belkacemguerbasse-del/hotwire-sender.git
cd hotwire-sender
python -m venv .venv
.\.venv\Scripts\Activate.ps1     # Linux : source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

### Driver Microsoft Access (optionnel)

Pour utiliser la bibliothèque de 2383 profils Profili Pro (`data/ProfiliProNoPolar.mdb`),
installer le pilote **Microsoft Access Database Engine 2016 Redistributable**
(version 32-bit ou 64-bit selon ton Python) :
https://www.microsoft.com/en-us/download/details.aspx?id=54920

Sans ce pilote, le slicer fonctionne avec les profils `.dat` Selig classiques.

## Architecture

```
core/        Lien Grbl (série + character-counting streamer + parser status)
             Persistance QSettings, état machine, job runner, macros, historique
gcode/       Parser G-code, slicer 2 profils, géométrie aile, export PDF
ui/          Fenêtre principale, widgets, thèmes, i18n FR/EN
  widgets/   DRO, jog pad, status panel, gcode panel, slicer window, webcam…
resources/   Profils .dat embarqués, ressources graphiques
tools/       Scripts utilitaires (extraction Profili .mdb → .dat, etc.)
data/        Base Profili Pro (xlsx + mdb, hors repo si trop volumineuse)
```

## Notes firmware

Le firmware utilisé est `grbl-Mega-5X` 1.2h sur Arduino Mega 2560 + RAMPS 1.4.
Le bootloader stk500v2 nécessite **~3 s de silence absolu** après l'ouverture
du port série pour céder la main à Grbl ; le sender attend ce délai
automatiquement (configurable dans Préférences).

Le sender gère également un **watchdog de sécurité** côté hôte : si aucun
status report n'arrive pendant le délai configuré pendant un job actif,
le fil chaud est coupé automatiquement.

## État du projet

Sender pleinement fonctionnel. Branche `main` testée sur machine réelle.

## Licence

GPLv3 — voir [LICENSE](LICENSE). Compatible avec la licence du firmware
`grbl-Mega-5X`.

## Crédits

- Firmware [grbl-Mega-5X](https://github.com/fra589/grbl-Mega-5X) par fra589
- Application historique *Grbl HotWire Mega 5X* par RC Keith
- Base de profils [Profili Pro](http://www.profili2.com) par Stefano Duranti
