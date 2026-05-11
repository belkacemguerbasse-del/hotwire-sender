"""Panneau caméra : prévisualisation live + capture.

Utilise PySide6 QtMultimedia (Windows Media Foundation par défaut).
S'intègre dans un QDockWidget mais reste autonome.

Si aucune caméra n'est connectée ou que QtMultimedia plante, le panneau affiche
un message clair au lieu de planter l'application.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedLayout,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core import persistence
from ui.theme import COLORS, ui_font

from .webcam_osd import WebcamOSD

try:
    from PySide6.QtMultimedia import (
        QCamera,
        QImageCapture,
        QMediaCaptureSession,
        QMediaDevices,
    )
    from PySide6.QtMultimediaWidgets import QVideoWidget
    _MM_OK = True
    _MM_ERR = ""
except Exception as e:  # pragma: no cover
    _MM_OK = False
    _MM_ERR = str(e)


class WebcamPanel(QWidget):
    """Widget autonome : on l'ajoute dans un QDockWidget côté MainWindow."""

    snapshot_taken = Signal(str)  # chemin du fichier sauvegardé

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumWidth(280)

        self._camera: "QCamera | None" = None
        self._session: "QMediaCaptureSession | None" = None
        self._capture: "QImageCapture | None" = None
        self._video: "QVideoWidget | None" = None
        self._running = False

        self._build_ui()
        if _MM_OK:
            self._init_pipeline()
            self._refresh_devices()
            # Restaure le dernier device choisi
            last = persistence.get_str("camera/device")
            if last:
                idx = self.cb_device.findData(last)
                if idx >= 0:
                    self.cb_device.setCurrentIndex(idx)

    # ---------- UI ----------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        if not _MM_OK:
            msg = QLabel(
                "Module caméra indisponible :\n\n"
                f"{_MM_ERR}\n\n"
                "Vérifie que PySide6.QtMultimedia est installé "
                "(normalement fourni avec PySide6)."
            )
            msg.setWordWrap(True)
            msg.setAlignment(Qt.AlignCenter)
            msg.setStyleSheet(f"color: {COLORS['danger']}; padding: 20px;")
            outer.addWidget(msg, 1)
            return

        # --- Sélecteurs ---
        gb_src = QGroupBox("Source")
        gs = QVBoxLayout(gb_src)
        self.cb_device = QComboBox()
        self.cb_device.setToolTip("Caméra à utiliser")
        self.cb_resolution = QComboBox()
        self.cb_resolution.setToolTip("Résolution de la caméra")
        self.cb_device.currentIndexChanged.connect(self._on_device_changed)
        self.cb_resolution.currentIndexChanged.connect(self._on_resolution_changed)

        gs.addWidget(QLabel("Caméra :"))
        gs.addWidget(self.cb_device)
        gs.addWidget(QLabel("Résolution :"))
        gs.addWidget(self.cb_resolution)
        outer.addWidget(gb_src)

        # --- Vidéo (stack pour montrer un message si pas de cam) ---
        self._stack = QStackedWidget()
        self._stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._stack.setMinimumHeight(220)
        self._stack.setStyleSheet("background-color: #1a1d22; border-radius: 8px;")

        self._video = QVideoWidget()
        self._video.setStyleSheet("background-color: black; border-radius: 8px;")

        # OSD overlay au-dessus du video, dans un container avec
        # QStackedLayout en mode StackAll (les widgets sont empilés
        # visuellement, le dernier ajouté est au-dessus).
        self.osd = WebcamOSD()
        video_container = QWidget()
        video_layers = QStackedLayout(video_container)
        video_layers.setStackingMode(QStackedLayout.StackAll)
        video_layers.addWidget(self._video)   # fond
        video_layers.addWidget(self.osd)      # overlay au-dessus
        self._video_container = video_container

        self._lbl_no_video = QLabel("Aucune caméra disponible")
        self._lbl_no_video.setAlignment(Qt.AlignCenter)
        self._lbl_no_video.setFont(ui_font(11))
        self._lbl_no_video.setStyleSheet(
            "color: #c0c8d2; background-color: #1a1d22; border-radius: 8px; padding: 30px;"
        )

        self._stack.addWidget(self._lbl_no_video)
        self._stack.addWidget(video_container)
        self._stack.setCurrentIndex(0)
        outer.addWidget(self._stack, 1)

        # Toggle OSD on/off
        self.cb_osd = QCheckBox("Afficher OSD (info sur la vidéo)")
        self.cb_osd.setChecked(persistence.get_bool("camera/osd_visible", True))
        self.cb_osd.toggled.connect(self._on_osd_toggle)
        self.osd.setVisible(self.cb_osd.isChecked())

        # --- Actions ---
        self.btn_start_stop = QPushButton("Démarrer")
        self.btn_start_stop.setProperty("variant", "primary")
        self.btn_start_stop.setMinimumHeight(34)
        self.btn_start_stop.clicked.connect(self._toggle)

        self.btn_capture = QPushButton("Capturer")
        self.btn_capture.setMinimumHeight(34)
        self.btn_capture.setToolTip("Enregistrer une photo de l'image courante")
        self.btn_capture.clicked.connect(self._take_snapshot)

        row = QHBoxLayout()
        row.addWidget(self.btn_start_stop, 1)
        row.addWidget(self.btn_capture, 1)
        outer.addLayout(row)

        # --- Toggle OSD ---
        outer.addWidget(self.cb_osd)

        # --- Statut ---
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet(f"color: {COLORS['text_muted']};")
        f = self.lbl_status.font()
        f.setItalic(True)
        self.lbl_status.setFont(f)
        outer.addWidget(self.lbl_status)

    def _init_pipeline(self) -> None:
        self._session = QMediaCaptureSession(self)
        self._capture = QImageCapture(self)
        self._session.setImageCapture(self._capture)
        self._session.setVideoOutput(self._video)
        self._capture.imageSaved.connect(self._on_image_saved)
        self._capture.errorOccurred.connect(
            lambda _id, _err, msg: self._set_status(f"Erreur capture : {msg}", error=True)
        )

    # ---------- Devices ----------

    def _refresh_devices(self) -> None:
        self.cb_device.blockSignals(True)
        self.cb_device.clear()
        devices = QMediaDevices.videoInputs()
        if not devices:
            self.cb_device.addItem("(aucune caméra détectée)", None)
            self._set_status("Aucune caméra détectée. Branche une webcam puis Re-Scan.")
        else:
            for d in devices:
                # data = id() utilisable pour persistence (string)
                dev_id = bytes(d.id()).decode("ascii", errors="replace")
                self.cb_device.addItem(d.description(), dev_id)
            self._set_status(f"{len(devices)} caméra(s) détectée(s).")
        self.cb_device.blockSignals(False)
        self._refresh_resolutions()

    def _on_device_changed(self) -> None:
        self._refresh_resolutions()
        # Sauvegarde l'id sélectionné
        dev_id = self.cb_device.currentData()
        if dev_id:
            persistence.set_("camera/device", dev_id)
        if self._running:
            self._restart()

    def _refresh_resolutions(self) -> None:
        self.cb_resolution.blockSignals(True)
        self.cb_resolution.clear()
        idx = self.cb_device.currentIndex()
        device = QMediaDevices.videoInputs()
        if 0 <= idx < len(device):
            d = device[idx]
            formats = d.videoFormats()
            seen = set()
            for f in formats:
                w = f.resolution().width()
                h = f.resolution().height()
                key = (w, h)
                if key in seen or w <= 0 or h <= 0:
                    continue
                seen.add(key)
                self.cb_resolution.addItem(f"{w} × {h}", (w, h))
        if self.cb_resolution.count() == 0:
            self.cb_resolution.addItem("(défaut)", None)
        # Restaure dernière résolution
        last = persistence.get_str("camera/resolution")
        if last:
            idx2 = self.cb_resolution.findText(last)
            if idx2 >= 0:
                self.cb_resolution.setCurrentIndex(idx2)
        self.cb_resolution.blockSignals(False)

    def _on_resolution_changed(self) -> None:
        persistence.set_("camera/resolution", self.cb_resolution.currentText())
        if self._running:
            self._restart()

    # ---------- Lifecycle ----------

    def _toggle(self) -> None:
        if self._running:
            self._stop()
        else:
            self._start()

    def _start(self) -> None:
        idx = self.cb_device.currentIndex()
        devices = QMediaDevices.videoInputs()
        if not (0 <= idx < len(devices)):
            QMessageBox.warning(self, "Caméra", "Sélectionne une caméra valide.")
            return
        device = devices[idx]
        try:
            cam = QCamera(device, self)
            # Choix du format selon la résolution sélectionnée si possible
            res = self.cb_resolution.currentData()
            if res is not None:
                target = (res[0], res[1])
                for fmt in device.videoFormats():
                    r = fmt.resolution()
                    if (r.width(), r.height()) == target:
                        cam.setCameraFormat(fmt)
                        break
            self._session.setCamera(cam)
            self._camera = cam
            cam.errorOccurred.connect(
                lambda _err, msg: self._set_status(f"Erreur caméra : {msg}", error=True)
            )
            cam.start()
        except Exception as e:
            self._set_status(f"Échec démarrage : {e}", error=True)
            return

        self._running = True
        self.btn_start_stop.setText("Arrêter")
        self.btn_start_stop.setProperty("variant", "danger")
        self.btn_start_stop.style().unpolish(self.btn_start_stop)
        self.btn_start_stop.style().polish(self.btn_start_stop)
        self._stack.setCurrentIndex(1)
        self._set_status("En direct.")

    def _stop(self) -> None:
        if self._camera is not None:
            try:
                self._camera.stop()
            except Exception:
                pass
            self._camera = None
        self._session.setCamera(None)
        self._running = False
        self.btn_start_stop.setText("Démarrer")
        self.btn_start_stop.setProperty("variant", "primary")
        self.btn_start_stop.style().unpolish(self.btn_start_stop)
        self.btn_start_stop.style().polish(self.btn_start_stop)
        self._stack.setCurrentIndex(0)
        self._set_status("Arrêtée.")

    def _restart(self) -> None:
        if self._running:
            self._stop()
            self._start()

    # ---------- Capture ----------

    def _take_snapshot(self) -> None:
        if not self._running or self._capture is None:
            QMessageBox.information(self, "Caméra", "Démarre d'abord la caméra.")
            return
        out_dir = persistence.get_str(
            "camera/capture_dir",
            str(Path.home() / "Pictures" / "HotWire"),
        )
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_path = str(Path(out_dir) / f"hotwire-{ts}.jpg")
        try:
            self._capture.captureToFile(out_path)
        except Exception as e:
            self._set_status(f"Échec capture : {e}", error=True)

    def _on_image_saved(self, _id: int, path: str) -> None:
        self._set_status(f"Capturé : {os.path.basename(path)}")
        persistence.set_("camera/capture_dir", str(Path(path).parent))
        self.snapshot_taken.emit(path)

    # ---------- Helpers ----------

    def _set_status(self, msg: str, error: bool = False) -> None:
        if hasattr(self, "lbl_status"):
            color = COLORS["danger"] if error else COLORS["text_muted"]
            self.lbl_status.setStyleSheet(f"color: {color}; font-style: italic;")
            self.lbl_status.setText(msg)

    def _on_osd_toggle(self, checked: bool) -> None:
        if hasattr(self, "osd"):
            self.osd.setVisible(checked)
            persistence.set_("camera/osd_visible", checked)

    def shutdown(self) -> None:
        if self._running:
            self._stop()
