"""Fenêtre principale : assemble tous les widgets et câble les signaux/slots."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core import persistence
from core.grbl_link import GrblLink, GrblStatus
from core.job_runner import JobRunner
from core.machine_state import MachineState
from core.simulator import GcodeSimulator
from gcode.parser import parse_program
from ui.theme import card_shadow
from ui.widgets.preferences_panel import load_prefs

from .widgets.connection_bar import ConnectionBar
from .widgets.control_panel import ControlPanel
from .widgets.dro import Dro
from .widgets.gcode_panel import GcodePanel
from .widgets.header_bar import HeaderBar
from .widgets.hotwire_panel import HotWirePanel
from .widgets.jog_pad import JogPanel
from .widgets.mdi import MdiPanel
from .widgets.overrides_panel import OverridesPanel
from .widgets.path_view import PathView
from .widgets.path_view_3d import PathView3D
from .widgets.settings_tab import SettingsTab
from .widgets.slicer_window import SlicerWindow
from .widgets.status_panel import StatusPanel
from .widgets.webcam_panel import WebcamPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HotWire Sender — XYZA")
        self.resize(1600, 980)

        prefs = load_prefs()
        self._pause_on_error = prefs["pause_on_error"]
        self._watchdog_enabled = prefs["watchdog"]
        self._watchdog_threshold_s = prefs["watchdog_s"]
        self._last_status_ts: float = 0.0
        self._watchdog_triggered: bool = False
        self.link = GrblLink(
            status_period_ms=prefs["poll_ms"],
            boot_delay_s=prefs["boot_delay_s"],
        )
        self.state = MachineState(axis_count=4, axis_names=("X", "Y", "Z", "A"))
        self.job = JobRunner(self.link, self)
        self.simulator = GcodeSimulator(self)

        # Watchdog : tick toutes les 500 ms pour vérifier l'activité
        from PySide6.QtCore import QTimer as _QT
        self._watchdog_timer = _QT(self)
        self._watchdog_timer.setInterval(500)
        self._watchdog_timer.timeout.connect(self._watchdog_tick)
        self._watchdog_timer.start()

        # ---- Widgets ----
        self.header = HeaderBar()
        self.connection = ConnectionBar()
        self.control = ControlPanel()
        self.status = StatusPanel()
        self.gcode = GcodePanel()
        self.dro = Dro()
        self.jog = JogPanel()
        self.hotwire = HotWirePanel(max_value=1000)
        self.overrides = OverridesPanel()
        self.mdi = MdiPanel()
        self.path = PathView()
        self.path_3d = PathView3D(wire_span_default=persistence.get_float("slicer/wire_span", 1000.0))
        self.settings = SettingsTab()
        self.webcam = WebcamPanel()

        self._build_layout()
        self._apply_shadows()
        self._wire_signals()
        self._set_connected_ui(False)
        self._restore_state()
        self._maybe_autoconnect()

    # ---------- Layout ----------

    def _build_layout(self) -> None:
        # Colonne 1 : connexion / contrôle / statut / gcode
        col1 = QWidget()
        v1 = QVBoxLayout(col1)
        v1.setContentsMargins(4, 4, 4, 4)
        v1.addWidget(self.connection)
        v1.addWidget(self.control)
        v1.addWidget(self.status, 1)
        v1.addWidget(self.gcode, 2)

        # Colonne 2 : DRO / jog / fil chaud / overrides / MDI
        col2 = QWidget()
        v2 = QVBoxLayout(col2)
        v2.setContentsMargins(4, 4, 4, 4)
        v2.addWidget(self.dro)
        v2.addWidget(self.jog)
        v2.addWidget(self.hotwire)
        v2.addWidget(self.overrides)
        v2.addWidget(self.mdi)
        v2.addStretch(1)

        # Colonne 3 : visualisations
        col3 = self.path

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(col1)
        splitter.addWidget(col2)
        splitter.addWidget(col3)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 0)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([320, 460, 820])

        # Onglets : Pilotage / Vue 3D / Réglages / Macros
        tabs = QTabWidget()
        tabs.addTab(splitter, "Pilotage")
        tabs.addTab(self.path_3d, "Vue 3D")
        tabs.addTab(self._build_settings_tab(), "Réglages")
        tabs.addTab(self._build_macros_tab(), "Macros")

        # Container central : header + tabs
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.header)
        outer.addWidget(tabs, 1)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Prêt")

        # --- Dock caméra (à droite, caché par défaut) ---
        self.dock_camera = QDockWidget("Caméra", self)
        self.dock_camera.setObjectName("dockCamera")
        self.dock_camera.setAllowedAreas(
            Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea | Qt.BottomDockWidgetArea
        )
        self.dock_camera.setFeatures(
            QDockWidget.DockWidgetMovable
            | QDockWidget.DockWidgetFloatable
            | QDockWidget.DockWidgetClosable
        )
        self.dock_camera.setWidget(self.webcam)
        self.dock_camera.setMinimumWidth(320)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_camera)
        self.dock_camera.hide()
        # Le bouton du header reflète l'état du dock
        self.dock_camera.visibilityChanged.connect(self._on_camera_visibility)

        # Raccourci F9 pour basculer la caméra
        sc = QShortcut(QKeySequence("F9"), self)
        sc.activated.connect(self._toggle_camera)

    def _build_settings_tab(self) -> QWidget:
        return self.settings

    def _build_macros_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("Macros utilisateur — à implémenter en P2."))
        v.addStretch(1)
        return w

    # ---------- Signal wiring ----------

    def _wire_signals(self) -> None:
        # Connexion
        self.connection.connect_requested.connect(self._on_connect)
        self.connection.disconnect_requested.connect(self._on_disconnect)

        self.link.connected.connect(self._on_link_opened)
        self.link.disconnected.connect(self._on_link_closed)
        self.link.error_text.connect(lambda msg: self.status.append_info(msg))

        # Logs verbeux
        self.link.line_received.connect(self.status.append_rx)
        self.link.sent.connect(self.status.append_tx)

        # Onglet Réglages : capture des `$N=value`, `[VER:]`, `[OPT:]`, `[G54:]` etc.
        self.link.line_received.connect(self.settings.maybe_consume_line)
        self.settings.reload_requested.connect(self._on_settings_reload)
        self.settings.write_setting_requested.connect(self.link.send_line)
        self.settings.send_line_requested.connect(self.link.send_line)
        self.settings.preferences.settings_applied.connect(self._on_prefs_applied)

        # Pause auto sur error: surveille les lignes RX
        self.link.line_received.connect(self._on_line_for_error_pause)

        # Header (toujours visible)
        self.link.connected.connect(self.header.on_connected)
        self.link.disconnected.connect(self.header.on_disconnected)
        self.header.estop_requested.connect(self._on_estop)
        self.header.camera_toggle_requested.connect(self._toggle_camera)

        # État machine
        self.link.status_received.connect(self.state.update_from_status)
        # Watchdog : timestamp à chaque status reçu
        self.link.status_received.connect(self._on_status_for_watchdog)
        self.state.state_changed.connect(self.header.on_state)
        self.state.mpos_changed.connect(self.dro.set_mpos)
        self.state.wpos_changed.connect(self.dro.set_wpos)
        self.state.mpos_changed.connect(self.path.on_mpos)
        self.state.mpos_changed.connect(self.path_3d.on_mpos)
        self.state.overrides_changed.connect(self.overrides.on_overrides)

        # Contrôle
        self.control.home_requested.connect(lambda: self.link.send_line("$H"))
        self.control.unlock_requested.connect(lambda: self.link.send_line("$X"))
        self.control.reset_requested.connect(self.link.soft_reset)
        self.control.hold_requested.connect(self.link.feed_hold)
        self.control.resume_requested.connect(self.link.cycle_start)
        self.control.check_toggle_requested.connect(lambda: self.link.send_line("$C"))

        # Jog
        self.jog.jog_axis.connect(self._on_jog_axis)
        self.jog.jog_pair.connect(self._on_jog_pair)
        self.jog.zero_axes.connect(self._on_zero_axes)
        self.jog.goto_zero_axes.connect(self._on_goto_zero_axes)

        # Fil chaud
        self.hotwire.turn_on_requested.connect(self._on_hotwire_on)
        self.hotwire.turn_off_requested.connect(self._on_hotwire_off)
        self.hotwire.set_power_requested.connect(self._on_hotwire_power)

        # Overrides realtime
        self.overrides.cmd_requested.connect(self.link.send_realtime)

        # MDI
        self.mdi.line_submitted.connect(self.link.send_line)
        self.mdi.slice_requested.connect(self._open_slicer)

        # G-code
        self.gcode.file_loaded.connect(self._on_gcode_loaded)
        self.gcode.play_requested.connect(self._on_play)
        self.gcode.pause_requested.connect(self._on_pause)
        self.gcode.stop_requested.connect(self._on_stop)
        self.gcode.reload_requested.connect(self._on_reload)
        self.gcode.simulate_requested.connect(self._on_simulate)

        # Simulation : positions du simulateur -> vue 3D
        self.simulator.position_updated.connect(self.path_3d.on_sim_position)
        self.simulator.progress_changed.connect(self.path_3d.on_sim_progress)
        self.simulator.elapsed_changed.connect(self.path_3d.on_sim_elapsed)
        self.simulator.state_changed.connect(self.path_3d.on_sim_state)

        # Boutons de la barre de simulation -> simulator
        self.path_3d.sim_play_requested.connect(self.simulator.play)
        self.path_3d.sim_pause_requested.connect(self.simulator.pause)
        self.path_3d.sim_stop_requested.connect(self.simulator.stop)
        self.path_3d.sim_speed_changed.connect(self.simulator.set_speed)

        self.job.line_sent.connect(lambda i: self.gcode.mark_line(i, "→"))
        self.job.line_acked.connect(
            lambda i, ok: self.gcode.mark_line(i, "ok" if ok else "err")
        )
        self.job.elapsed_tick.connect(self.gcode.set_elapsed)
        self.job.finished.connect(lambda: self.statusBar().showMessage("Programme terminé"))
        self.job.pause_with_message.connect(self._on_job_pause)

    # ---------- Slots ----------

    def _on_connect(self, port: str, baud: int) -> None:
        self.status.append_info(f"Ouverture {port} @ {baud}…")
        self.link.open(port, baud)

    def _on_disconnect(self) -> None:
        self.hotwire.force_off()
        self.link.close()

    def _on_estop(self) -> None:
        """Bouton ARRÊT D'URGENCE du header : coupe fil + soft reset firmware."""
        self.hotwire.force_off()
        if self.link.is_open():
            self.link.soft_reset()
        self.status.append_info("ARRÊT D'URGENCE déclenché")
        if self.job.is_running():
            self.job.stop()

    def _toggle_camera(self) -> None:
        self.dock_camera.setVisible(not self.dock_camera.isVisible())

    def _on_prefs_applied(self, prefs: dict) -> None:
        """Appelé quand l'utilisateur clique « Appliquer » sur les préférences."""
        self._pause_on_error = prefs["pause_on_error"]
        self._watchdog_enabled = prefs["watchdog"]
        self._watchdog_threshold_s = prefs["watchdog_s"]
        self.link.set_status_period_ms(prefs["poll_ms"])
        self.link.set_boot_delay_s(prefs["boot_delay_s"])
        self.status.append_info("Préférences appliquées.")

    def _on_status_for_watchdog(self, _status) -> None:
        import time
        self._last_status_ts = time.monotonic()
        if self._watchdog_triggered:
            # Le firmware reparle : on désarme l'alerte visuelle
            self._watchdog_triggered = False
            self.statusBar().showMessage("Connexion firmware rétablie")

    def _watchdog_tick(self) -> None:
        """Vérifie l'activité firmware. Coupe le fil + pause si inactif trop
        longtemps pendant qu'un job tourne."""
        if not self._watchdog_enabled:
            return
        if not self.link.is_open():
            return
        if not self.job.is_running():
            return
        if self._watchdog_triggered:
            return
        if self._last_status_ts == 0.0:
            return
        import time
        delta = time.monotonic() - self._last_status_ts
        if delta < self._watchdog_threshold_s:
            return
        # ALERTE — on évite tout popup modal qui bloquerait l'event loop.
        # Le user voit l'alerte dans le header, le log et la status bar.
        self._watchdog_triggered = True
        self.hotwire.force_off()
        self.job.pause()
        msg = (
            f"⚠ WATCHDOG : aucun status report depuis {delta:.1f} s. "
            "Fil coupé, job en pause. Vérifie le câble USB et le firmware."
        )
        self.status.append_info(msg)
        self.statusBar().showMessage(msg, 10000)
        # Force le state header en "Alarm" visuel
        self.header.on_state("Alarm")

    def _on_line_for_error_pause(self, line: str) -> None:
        """Pause auto du job si une erreur Grbl arrive pendant l'exécution."""
        if not self._pause_on_error:
            return
        if not self.job.is_running():
            return
        if line.startswith("error:") or line.lower().startswith("alarm"):
            self.job.pause()
            self.status.append_info(f"Job en pause : {line}")

    def _on_job_pause(self, message: str) -> None:
        """Affiché quand le runner rencontre un `; @HW_PAUSE:` (entre panneaux
        d'une aile multi-panneaux). Coupe le fil chaud par sécurité, attend
        la confirmation user, puis reprend."""
        from PySide6.QtWidgets import QMessageBox

        # Sécurité : coupe le fil chaud pendant la pause
        self.hotwire.force_off()
        self.status.append_info(f"PAUSE — {message}")
        self.statusBar().showMessage("Programme en pause — repositionne et continue")

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle("Pause programme")
        box.setText("⏸  Programme en pause")
        box.setInformativeText(
            f"{message}\n\n"
            "• Le fil chaud a été coupé par sécurité.\n"
            "• Vérifie que la machine est bien à l'arrêt.\n"
            "• Repositionne le bloc de mousse.\n"
            "• Clique sur Continuer pour lancer le panneau suivant.\n"
            "• Clique sur Annuler pour stopper complètement le programme."
        )
        btn_continue = box.addButton("Continuer", QMessageBox.AcceptRole)
        btn_cancel = box.addButton("Annuler", QMessageBox.RejectRole)
        box.setDefaultButton(btn_continue)
        box.exec()

        if box.clickedButton() is btn_cancel:
            self.status.append_info("Programme annulé par l'utilisateur.")
            self.job.stop()
            return

        self.status.append_info("Reprise du programme.")
        self.statusBar().showMessage("En cours…")
        self.job.resume_from_logical_pause()

    def _on_camera_visibility(self, visible: bool) -> None:
        # Synchronise l'état checked du bouton header avec le dock
        self.header.btn_camera.setChecked(visible)

    def _on_link_opened(self, port: str) -> None:
        self.statusBar().showMessage(f"Connecté à {port}")
        self.status.append_info(f"Connecté à {port}")
        self._set_connected_ui(True)
        self.settings.set_port(port)
        # Charge automatiquement réglages, infos firmware et décalages
        # peu après la connexion (laisser le banner+[VER]+[OPT] passer).
        from PySide6.QtCore import QTimer as _QT
        _QT.singleShot(1500, self._on_settings_reload)
        _QT.singleShot(1700, lambda: self.link.send_line("$I"))
        _QT.singleShot(1900, lambda: self.link.send_line("$#"))

    def _on_settings_reload(self) -> None:
        if not self.link.is_open():
            return
        self.settings.clear()
        self.link.send_line("$$")

    def _open_slicer(self) -> None:
        win = SlicerWindow(self)
        win.gcode_generated.connect(self._on_slicer_output)
        win.exec()

    def _on_slicer_output(self, lines: list) -> None:
        # Charge le G-code généré directement dans le panneau gcode et la viz.
        from gcode.parser import parse_program
        text = "\n".join(lines)
        self.gcode._lines = list(lines)
        self.gcode._current_path = "<slicer>"
        self.gcode.table.setRowCount(0)
        for i, ln in enumerate(lines, start=1):
            row = self.gcode.table.rowCount()
            self.gcode.table.insertRow(row)
            from PySide6.QtWidgets import QTableWidgetItem
            self.gcode.table.setItem(row, 0, QTableWidgetItem(""))
            self.gcode.table.setItem(row, 1, QTableWidgetItem(str(i)))
            self.gcode.table.setItem(row, 2, QTableWidgetItem(ln))
        self.gcode.lbl_progress.setText(f"0 de {len(lines)}")
        parsed = parse_program(text)
        self.path.set_program(parsed)
        self.path_3d.set_wire_span(persistence.get_float("slicer/wire_span", 1000.0))
        self.path_3d.set_program(parsed)
        self.job.load(lines)
        self.status.append_info(f"Slicer : {len(lines)} lignes générées et chargées.")

    def _on_link_closed(self) -> None:
        self.statusBar().showMessage("Déconnecté")
        self.status.append_info("Déconnecté")
        self._set_connected_ui(False)
        self.hotwire.set_on(False)
        self.settings.clear()
        self.settings.set_port("")

    def _set_connected_ui(self, connected: bool) -> None:
        self.connection.set_open(connected)
        for w in (
            self.control,
            self.dro,
            self.jog,
            self.hotwire,
            self.overrides,
            self.mdi,
        ):
            w.setEnabled(connected)
        # Le panneau GCode reste utilisable même hors connexion :
        # `Ouvrir`, `Simuler`, `Recharger` n'ont pas besoin du firmware.
        # Seuls `Lancer` / `Pause` / `Stop` requièrent une machine connectée.
        self.gcode.setEnabled(True)
        for b in (self.gcode.btn_play, self.gcode.btn_pause, self.gcode.btn_stop):
            b.setEnabled(connected)

    def _on_jog_axis(self, axis: str, distance: float, feed: float) -> None:
        cmd = f"$J=G91 G21 {axis}{distance:.3f} F{int(feed)}"
        self.link.send_line(cmd)

    def _on_jog_pair(self, a1: str, a2: str, d1: float, d2: float, feed: float) -> None:
        cmd = f"$J=G91 G21 {a1}{d1:.3f} {a2}{d2:.3f} F{int(feed)}"
        self.link.send_line(cmd)

    def _on_zero_axes(self, axes: tuple) -> None:
        # Fixe le WCO courant à 0 sur les axes donnés via G10 L20 P1.
        parts = [f"{ax}0" for ax in axes]
        self.link.send_line("G10 L20 P1 " + " ".join(parts))

    def _on_goto_zero_axes(self, axes: tuple) -> None:
        parts = [f"{ax}0" for ax in axes]
        self.link.send_line("G90 G0 " + " ".join(parts))

    def _on_hotwire_on(self, value: int) -> None:
        self.link.send_line(f"M3 S{value}")
        self.hotwire.set_on(True)

    def _on_hotwire_off(self) -> None:
        self.link.send_line("M5")
        self.hotwire.set_on(False)

    def _on_hotwire_power(self, value: int) -> None:
        self.link.send_line(f"S{value}")

    def _on_simulate(self) -> None:
        """Lance la simulation du G-code chargé dans la vue 3D."""
        from PySide6.QtWidgets import QMessageBox, QTabWidget

        lines = self.gcode.lines()
        if not lines:
            QMessageBox.information(
                self, "Simulation",
                "Aucun programme chargé. Ouvre un fichier G-code ou génère "
                "un programme via le slicer avant de simuler."
            )
            return

        # Bascule sur l'onglet Vue 3D
        tabs = self.findChild(QTabWidget)
        if tabs is not None:
            for i in range(tabs.count()):
                if tabs.tabText(i).strip().lower().startswith("vue 3d"):
                    tabs.setCurrentIndex(i)
                    break

        self.simulator.load(lines)
        self.simulator.set_speed(self.path_3d.cb_sim_speed.currentData() or 5.0)
        self.simulator.play()
        self.statusBar().showMessage("Simulation en cours…")

    def _on_gcode_loaded(self, path: str, lines: list) -> None:
        self.statusBar().showMessage(f"{path} chargé ({len(lines)} lignes)")
        text = "\n".join(lines)
        parsed = parse_program(text)
        self.path.set_program(parsed)
        self.path_3d.set_wire_span(persistence.get_float("slicer/wire_span", 1000.0))
        self.path_3d.set_program(parsed)
        self.job.load(lines)

    def _on_play(self) -> None:
        if not self.link.is_open():
            self.status.append_info("Pas de connexion : impossible de démarrer.")
            return
        if not self.job._lines:
            self.status.append_info("Aucun programme chargé.")
            return
        self.gcode.reset_marks()
        self.job.load(self.gcode.lines())
        # Reset le timestamp du watchdog : on ne veut pas qu'il déclenche
        # immédiatement parce que le dernier status date de quelques secondes
        # (cas typique : utilisateur idle puis clique Lancer).
        import time
        self._last_status_ts = time.monotonic()
        self._watchdog_triggered = False
        self.job.start()

    def _on_pause(self) -> None:
        self.job.pause()

    def _on_stop(self) -> None:
        self.hotwire.force_off()
        self.job.stop()

    def _on_reload(self) -> None:
        if self.gcode._current_path:
            self.gcode.load_file(self.gcode._current_path)

    # ---------- Effets visuels ----------

    def _apply_shadows(self) -> None:
        """Pose une ombre portée douce sur les cartes principales pour donner
        l'impression qu'elles flottent. À appeler une seule fois après build."""
        from PySide6.QtWidgets import QGroupBox

        # Cartes "racines" du Pilotage
        for w in (self.connection, self.status, self.gcode, self.dro,
                  self.hotwire, self.mdi):
            card_shadow(w, blur=14, offset_y=2, alpha=28)

        # JogPanel : 3 pavés + le cadre Settings
        for w in (self.jog.left, self.jog.right, self.jog.sync, self.jog.settings):
            card_shadow(w, blur=14, offset_y=2, alpha=28)

        # ControlPanel : sous-groupes Référencement / Contrôle
        for gb in self.control.findChildren(QGroupBox):
            card_shadow(gb, blur=14, offset_y=2, alpha=28)

        # Overrides : 2 lignes
        for w in (self.overrides.feed, self.overrides.spindle):
            card_shadow(w, blur=14, offset_y=2, alpha=28)

        # Header : ombre plus marquée pour l'effet "barre fixée"
        card_shadow(self.header, blur=22, offset_y=3, alpha=55)

        # Bouton ARRÊT : ombre rouge soutenue
        card_shadow(self.header.btn_estop, blur=18, offset_y=3,
                    alpha=120, color="#d6363d")

    # ---------- Persistance ----------

    def _restore_state(self) -> None:
        geom = persistence.get("ui/geometry")
        if geom is not None:
            self.restoreGeometry(geom)
        ws = persistence.get("ui/window_state")
        if ws is not None:
            self.restoreState(ws)
        # État verbeux du log
        self.status.cb_verbose.setChecked(persistence.get_bool("ui/verbose", False))
        # Visibilité du dock caméra (caché par défaut)
        cam_visible = persistence.get_bool("camera/dock_visible", False)
        self.dock_camera.setVisible(cam_visible)
        self.header.btn_camera.setChecked(cam_visible)

    def _save_state(self) -> None:
        persistence.set_("ui/geometry", self.saveGeometry())
        persistence.set_("ui/window_state", self.saveState())
        persistence.set_("ui/verbose", self.status.cb_verbose.isChecked())
        persistence.set_("camera/dock_visible", self.dock_camera.isVisible())

    def _maybe_autoconnect(self) -> None:
        """Si l'utilisateur a coché l'auto-connect, ouvre le dernier port mémorisé
        après un court délai (laisser l'UI s'afficher d'abord)."""
        if not persistence.get_bool("prefs/autoconnect", False):
            return
        port = persistence.get_str("connection/port")
        if not port:
            return
        try:
            baud = int(persistence.get_str("connection/baud", "115200"))
        except ValueError:
            baud = 115200
        from PySide6.QtCore import QTimer as _QT
        _QT.singleShot(400, lambda: self._on_connect(port, baud))

    # ---------- Cleanup ----------

    def closeEvent(self, event) -> None:
        self.hotwire.force_off()
        self.webcam.shutdown()
        self._save_state()
        self.link.shutdown()
        super().closeEvent(event)
