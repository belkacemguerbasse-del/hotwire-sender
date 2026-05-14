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
    QFrame,
    QScrollArea,
    QStatusBar,
    QStyle,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core import persistence
from core.grbl_link import GrblLink, GrblStatus
from core.job_history import JobHistory, make_entry
from core.job_runner import JobRunner
from core.macros import MacroStore
from core.machine_state import MachineState
from core.simulator import GcodeSimulator
from gcode.parser import estimate_program, parse_program
from ui.i18n import tr
from ui.theme import card_shadow
from ui.widgets.preferences_panel import load_prefs

from .widgets.connection_bar import ConnectionBar
from .widgets.control_panel import ControlPanel
from .widgets.dro import Dro
from .widgets.gcode_panel import GcodePanel
from .widgets.header_bar import HeaderBar
from .widgets.fan_panel import FanPanel
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
        self.history = JobHistory(parent=self)
        self.macros_store = MacroStore(parent=self)

        # System tray icon pour les notifications (Windows toast / Linux notify)
        self.tray_icon = QSystemTrayIcon(self)
        try:
            self.tray_icon.setIcon(
                self.style().standardIcon(QStyle.SP_ComputerIcon)
            )
        except Exception:
            pass
        self.tray_icon.setToolTip("HotWire Sender")
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon.show()
        # Tracking du job courant pour créer une HistoryEntry à la fin
        self._current_job_started_at = None
        self._current_job_path = ""
        self._current_job_lines = 0
        self._pending_finish_status = "ok"  # majoré par stop/abort handlers

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
        self.fan = FanPanel()
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

        # Colonne 2 : DRO / jog / fil chaud / ventilateur / overrides / MDI
        # Contenu enveloppé dans un QScrollArea car la somme des hauteurs des
        # widgets dépasse l'espace dispo sur des écrans de hauteur modérée
        # (le MDI était coupé en bas en 1080p / 1440p selon les configs).
        col2_inner = QWidget()
        v2 = QVBoxLayout(col2_inner)
        v2.setContentsMargins(4, 4, 4, 4)
        v2.addWidget(self.dro)
        v2.addWidget(self.jog)
        v2.addWidget(self.hotwire)
        v2.addWidget(self.fan)
        v2.addWidget(self.overrides)
        v2.addWidget(self.mdi)
        v2.addStretch(1)

        col2 = QScrollArea()
        col2.setWidget(col2_inner)
        col2.setWidgetResizable(True)
        col2.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        col2.setFrameShape(QFrame.NoFrame)

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
        tabs.addTab(splitter, tr("Pilotage"))
        tabs.addTab(self.path_3d, tr("Vue 3D"))
        tabs.addTab(self._build_settings_tab(), tr("Réglages"))
        tabs.addTab(self._build_macros_tab(), tr("Macros"))

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

        # Raccourci F1 pour afficher l'aide-mémoire des raccourcis
        sc_help = QShortcut(QKeySequence("F1"), self)
        sc_help.activated.connect(self._show_cheat_sheet)

    def _build_settings_tab(self) -> QWidget:
        return self.settings

    def _build_macros_tab(self) -> QWidget:
        from ui.widgets.macros_tab import MacrosTab
        self.macros = MacrosTab(self.macros_store)
        self.macros.send_lines_requested.connect(self._on_macro_run)
        return self.macros

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

        # Caméra OSD : alimenté en live par les signaux machine
        if hasattr(self.webcam, "osd"):
            self.state.state_changed.connect(self.webcam.osd.on_state)
            self.state.mpos_changed.connect(self.webcam.osd.on_mpos)

        # État machine
        self.link.status_received.connect(self.state.update_from_status)
        # Watchdog : timestamp à chaque status reçu
        self.link.status_received.connect(self._on_status_for_watchdog)
        # Synchro état ventilateur ↔ matériel via le champ `A:` du status
        self.link.status_received.connect(self._on_status_for_fan)
        # Stop auto du job si on entre en Alarm
        self.state.state_changed.connect(self._on_state_changed_safety)
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
        self.fan.fan_on_requested.connect(self._on_fan_on)
        self.fan.fan_off_requested.connect(self._on_fan_off)
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
        self.gcode.history_requested.connect(self._on_history)

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
        self.job.finished.connect(self._on_job_finished)
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
            self._pending_finish_status = "aborted"
            self.job.stop()

    def _toggle_camera(self) -> None:
        self.dock_camera.setVisible(not self.dock_camera.isVisible())

    def _show_cheat_sheet(self) -> None:
        """Ouvre le dialog d'aide-mémoire des raccourcis (F1)."""
        from ui.widgets.cheat_sheet import CheatSheetDialog
        dlg = CheatSheetDialog(self)
        dlg.exec()

    def _on_history(self) -> None:
        """Ouvre le dialog d'historique des coupes."""
        from ui.widgets.history_dialog import HistoryDialog
        dlg = HistoryDialog(self.history, self)
        dlg.reload_requested.connect(self._on_history_reload)
        dlg.exec()

    def _on_history_reload(self, path: str) -> None:
        """Recharge un fichier sélectionné depuis l'historique."""
        if path and path != "<slicer>":
            self.gcode.load_file(path)

    def _on_macro_run(self, lines: list) -> None:
        """Envoie les lignes d'une macro au firmware, une par une."""
        if not self.link.is_open():
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "Pas de connexion",
                "Connecte-toi au firmware avant d'exécuter une macro."
            )
            return
        if self.job.is_running():
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "Job en cours",
                "Un programme est en cours d'exécution. Stop avant d'exécuter "
                "une macro pour éviter les interférences."
            )
            return
        for line in lines:
            line = line.strip()
            if line:
                self.link.send_line(line)
        self.status.append_info(f"Macro envoyée ({len(lines)} lignes).")

    def _on_prefs_applied(self, prefs: dict) -> None:
        """Appelé quand l'utilisateur clique « Appliquer » sur les préférences."""
        self._pause_on_error = prefs["pause_on_error"]
        self._watchdog_enabled = prefs["watchdog"]
        self._watchdog_threshold_s = prefs["watchdog_s"]
        self.link.set_status_period_ms(prefs["poll_ms"])
        self.link.set_boot_delay_s(prefs["boot_delay_s"])
        # Hot-swap du thème (clair / sombre)
        from PySide6.QtWidgets import QApplication
        from ui.theme import apply_theme, current_mode
        new_theme = prefs.get("theme", "light")
        if new_theme != current_mode():
            apply_theme(QApplication.instance(), mode=new_theme)
        # Langue : nécessite restart
        from ui.i18n import current_language
        if prefs.get("language", "fr") != current_language():
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "Langue",
                "Le changement de langue prendra effet au prochain "
                "redémarrage de l'application."
            )
        self.status.append_info("Préférences appliquées.")

    def _on_state_changed_safety(self, state: str) -> None:
        """Si la machine entre en Alarm pendant un job, on stoppe net.
        Évite la cascade d'errors quand le firmware refuse toutes les
        commandes suivantes."""
        if state != "Alarm":
            return
        if not self.job.is_running():
            return
        self._pending_finish_status = "aborted"
        self.link.stop_streaming()
        self.hotwire.force_off()
        self.job.abort()
        msg = (
            "ALARME firmware détectée — fil coupé, job stoppé. "
            "Vérifie la cause (limite, probe, etc.), Débloq pour libérer."
        )
        self.status.append_info(msg)
        self.statusBar().showMessage(msg, 0)

    def _on_status_for_fan(self, status) -> None:
        """Synchronise l'état UI du ventilateur avec la réalité matérielle.

        Grbl 1.1 rapporte les accessoires actifs dans le champ `A:` du status :
          - 'F' = flood actif
          - 'M' = mist actif
          - 'S'/'C' = spindle CW/CCW
        Ex: `<Idle|MPos:..|FS:..|A:SF>` → spindle ON et flood ON.

        On lit cette info à chaque status report et on cale le bouton du
        ventilateur dessus, ce qui garantit qu'aucun désync ne peut s'installer
        (même en cas de M8/M9 dans le g-code, soft reset, ou changement
        manuel via MDI)."""
        flood_on = "F" in (status.accessory or "")
        self.fan.set_on_silent(flood_on)

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
        """Stop auto du job si une erreur Grbl arrive pendant l'exécution.

        On NE peut PAS juste pauser le runner : la file interne de GrblLink
        peut contenir des centaines de lignes qui vont continuer à partir
        et générer une cascade d'errors. On vide donc la file d'envoi
        immédiatement et on stoppe net (sans soft-reset car le firmware
        est probablement déjà en alarme et il garde un état utile)."""
        if not self._pause_on_error:
            return
        if not self.job.is_running():
            return
        if line.startswith("error:") or line.lower().startswith("alarm"):
            # 1. Coupe la cascade : vide la file link
            self.link.stop_streaming()
            # 2. Coupe le fil chaud par sécurité
            self.hotwire.force_off()
            # 3. Stop net du runner (sans toucher firmware)
            self._pending_finish_status = "error"
            self.job.abort()
            msg = (
                f"STOP AUTO sur {line} — fil coupé, file vidée. "
                "Vérifie la cause, clique Débloq pour libérer l'alarme, "
                "puis relance."
            )
            self.status.append_info(msg)
            self.statusBar().showMessage(msg, 0)

    def _on_job_finished(self) -> None:
        """Appelé via job.finished — fin normale, stop manuel, ou abort."""
        self.statusBar().showMessage("Programme terminé", 5000)
        # Réactive btn_play uniquement si on est toujours connecté
        connected = self.link.is_open()
        self.gcode.btn_play.setEnabled(connected)
        self.gcode.btn_pause.setEnabled(False)  # rien à pauser
        # Efface le surlignage de la ligne courante
        self.gcode.clear_active_highlight()
        # Enregistre dans l'historique si on avait un job actif
        if self._current_job_started_at is not None:
            import time
            duration = time.monotonic() - self._current_job_started_mono
            entry = make_entry(
                started_at=self._current_job_started_at,
                duration_s=duration,
                file_path=self._current_job_path,
                lines_count=self._current_job_lines,
                status=self._pending_finish_status,
            )
            self.history.add(entry)
            # Notification Windows / système
            self._notify_job_end(entry)
            self._current_job_started_at = None

    def _notify_job_end(self, entry) -> None:
        """Affiche une notification système après fin de job (Windows toast)."""
        if not (QSystemTrayIcon.isSystemTrayAvailable()
                and self.tray_icon.supportsMessages()):
            return
        from ui.widgets.history_dialog import _fmt_duration, STATUS_COLORS
        _, status_label = STATUS_COLORS.get(
            entry.status, ("#637381", entry.status.upper())
        )
        icon = {
            "ok":      QSystemTrayIcon.Information,
            "stopped": QSystemTrayIcon.Information,
            "aborted": QSystemTrayIcon.Warning,
            "error":   QSystemTrayIcon.Critical,
        }.get(entry.status, QSystemTrayIcon.Information)
        title = f"HotWire Sender — {status_label}"
        body = (
            f"Programme : {entry.file_name}\n"
            f"Durée : {_fmt_duration(entry.duration_s)}\n"
            f"Lignes : {entry.lines_count}"
        )
        self.tray_icon.showMessage(title, body, icon, 6000)

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
        """Charge un G-code généré par le slicer directement dans l'app."""
        text = "\n".join(lines)
        self.gcode._lines = list(lines)
        self.gcode._current_path = "<slicer>"
        # Bulk populate (rapide même pour 1000+ lignes)
        self.gcode._populate_table(lines)
        self.gcode.lbl_progress.setText(f"0 de {len(lines)}")
        parsed = parse_program(text)
        self.path.set_program(parsed)
        self.path_3d.set_wire_span(persistence.get_float("slicer/wire_span", 1000.0))
        self.path_3d.set_program(parsed)
        self.job.load(lines)
        self.gcode.set_estimates(estimate_program(parsed))
        self.status.append_info(f"Slicer : {len(lines)} lignes générées et chargées.")

    def _on_link_closed(self) -> None:
        self.statusBar().showMessage("Déconnecté")
        self.status.append_info("Déconnecté")
        self._set_connected_ui(False)
        self.hotwire.set_on(False)
        self.fan.set_on(False)
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
        # btn_play : actif si connecté (sera désactivé pendant l'exécution)
        self.gcode.btn_play.setEnabled(connected)
        # btn_stop : actif si connecté (no-op si pas de job, mais clean)
        self.gcode.btn_stop.setEnabled(connected)
        # btn_pause : actif uniquement quand un job tourne (géré par _on_play)
        # Ici on désactive par défaut, _on_play l'active quand le job démarre.
        if not (self.job.is_running() and not self.job._paused):
            self.gcode.btn_pause.setEnabled(False)

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
        if hasattr(self.webcam, "osd"):
            self.webcam.osd.on_hotwire(True, value)

    def _on_hotwire_off(self) -> None:
        self.link.send_line("M5")
        self.hotwire.set_on(False)
        if hasattr(self.webcam, "osd"):
            self.webcam.osd.on_hotwire(False, 0)

    def _on_hotwire_power(self, value: int) -> None:
        self.link.send_line(f"S{value}")
        if hasattr(self.webcam, "osd"):
            self.webcam.osd.on_hotwire(True, value)

    def _on_fan_on(self) -> None:
        # M8 = coolant flood ON, set explicite (pas un toggle). Idempotent :
        # ré-envoyer M8 alors que c'est déjà ON ne fait rien de mauvais.
        # Grbl exécute le changement de coolant en synchro avec le planner
        # via mc_coolant() → protocol_buffer_synchronize() → coolant_set_state(),
        # donc l'effet est immédiat en IDLE (buffer vide).
        # L'état UI sera de toute façon recalé par _on_status (champ A:F).
        self.link.send_line("M8")
        self.fan.set_on(True)

    def _on_fan_off(self) -> None:
        self.link.send_line("M9")
        self.fan.set_on(False)

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
        self.gcode.set_estimates(estimate_program(parsed))

    def _on_play(self) -> None:
        if not self.link.is_open():
            self.status.append_info("Pas de connexion : impossible de démarrer.")
            return
        # Cas 1 : reprise depuis une pause manuelle utilisateur.
        # Le job est encore "running" mais "paused" → on un-pause sans
        # toucher au cursor, et on envoie cycle_start au firmware.
        if self.job.is_running() and self.job._paused:
            self.gcode.btn_play.setEnabled(False)
            self.gcode.btn_pause.setEnabled(True)
            self.statusBar().showMessage("Reprise…")
            self.job.resume()
            return
        # Cas 2 : démarrage depuis zéro
        if not self.job._lines and not self.gcode.lines():
            self.status.append_info("Aucun programme chargé.")
            return
        # Démarrage automatique du ventilateur de refroidissement RAMPS
        # avant de lancer la coupe. _on_fan_on() envoie M8 (idempotent), et
        # le status report `A:F` recalera l'UI si elle n'était pas encore en
        # sync. Si l'utilisateur l'avait déjà allumé manuellement, M8 ne fait
        # qu'un no-op côté firmware.
        if not self.fan._on:
            self._on_fan_on()
        # Désactive temporairement le bouton et donne du feedback visuel.
        # Defer le travail au prochain tick de l'event loop pour que
        # l'UI se peigne immédiatement (sans attendre le pump).
        self.gcode.btn_play.setEnabled(False)
        self.gcode.btn_pause.setEnabled(True)
        self.statusBar().showMessage("Démarrage…")
        from PySide6.QtCore import QTimer as _QT
        _QT.singleShot(0, self._do_play)

    def _do_play(self) -> None:
        """Travail effectif du démarrage, exécuté après que l'UI a eu le
        temps de répondre au clic."""
        import time
        from datetime import datetime
        t0 = time.monotonic()
        self.gcode.reset_marks()
        t1 = time.monotonic()
        self.job.load(self.gcode.lines())
        t2 = time.monotonic()
        # Reset le timestamp du watchdog
        self._last_status_ts = time.monotonic()
        self._watchdog_triggered = False
        # Tracking pour l'historique
        self._current_job_started_at = datetime.now()
        self._current_job_started_mono = time.monotonic()
        self._current_job_path = self.gcode._current_path or ""
        self._current_job_lines = len(self.gcode.lines())
        self._pending_finish_status = "ok"
        self.job.start()
        t3 = time.monotonic()
        # Logging diag : si l'une des étapes dépasse 100ms on l'affiche
        total_ms = (t3 - t0) * 1000
        if total_ms > 100:
            self.status.append_info(
                f"_do_play : reset={ (t1-t0)*1000:.0f}ms "
                f"load={(t2-t1)*1000:.0f}ms start={(t3-t2)*1000:.0f}ms "
                f"total={total_ms:.0f}ms"
            )
        self.statusBar().showMessage("En cours…")
        # btn_play RESTE grisé tant que le job tourne. Re-activé via
        # _on_job_finished (job.finished.emit lorsque stop/abort/finish).

    def _on_pause(self) -> None:
        self.job.pause()
        # Pause = autorise la reprise via btn_play
        self.gcode.btn_play.setEnabled(True)
        self.gcode.btn_pause.setEnabled(False)
        self.statusBar().showMessage("En pause — clique Lancer pour reprendre")

    def _on_stop(self) -> None:
        self.hotwire.force_off()
        self._pending_finish_status = "stopped"
        self.job.stop()
        # job.stop() emet finished -> _on_job_finished re-active btn_play

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
