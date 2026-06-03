from __future__ import annotations

from pathlib import Path

import qtawesome as qta
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon


class TrayController(QObject):
    pause_toggled = pyqtSignal(bool)
    open_config_requested = pyqtSignal()
    exit_requested = pyqtSignal()
    profile_selected = pyqtSignal(str)

    def __init__(self, icon_path: Path) -> None:
        super().__init__()
        self._normal_icon = self._load_icon(icon_path)
        self._generated_llm_icon = qta.icon("fa5s.exclamation-triangle", color="#d08a00")
        self._unavailable_llm_icon = qta.icon("fa5s.exclamation-circle", color="#c8322a")
        self._tray = QSystemTrayIcon(self._normal_icon)
        self._menu = QMenu()
        self._paused = False
        self._llm_status = "not-configured"

        self._pause_action = QAction("Pausa", self._menu)
        self._pause_action.setCheckable(True)
        self._pause_action.toggled.connect(self.pause_toggled.emit)

        self._llm_status_action = QAction("LLM: sin configurar", self._menu)
        self._llm_status_action.setEnabled(False)

        self._profiles_menu = QMenu("Perfil", self._menu)
        self._profile_actions: dict[str, QAction] = {}

        self._config_action = QAction("Configuracion", self._menu)
        self._config_action.triggered.connect(self.open_config_requested.emit)

        self._exit_action = QAction("Salir", self._menu)
        self._exit_action.triggered.connect(self.exit_requested.emit)

        self._menu.addAction(self._pause_action)
        self._menu.addAction(self._llm_status_action)
        self._menu.addMenu(self._profiles_menu)
        self._menu.addSeparator()
        self._menu.addAction(self._config_action)
        self._menu.addSeparator()
        self._menu.addAction(self._exit_action)

        self._tray.setContextMenu(self._menu)
        self._tray.setToolTip("dictado")
        self._tray.activated.connect(self._handle_activated)

    def show(self) -> None:
        self._tray.show()

    def hide(self) -> None:
        self._tray.hide()

    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        self._pause_action.blockSignals(True)
        self._pause_action.setChecked(paused)
        self._pause_action.blockSignals(False)
        self._refresh_status_display()

    def set_llm_status(self, status: str) -> None:
        self._llm_status = status
        self._refresh_status_display()

    def set_profiles(self, profiles: list[str], active_profile: str) -> None:
        self._profiles_menu.clear()
        self._profile_actions.clear()
        for profile in profiles:
            action = QAction(profile, self._profiles_menu)
            action.setCheckable(True)
            action.setChecked(profile == active_profile)
            action.triggered.connect(lambda checked, profile_name=profile: self.profile_selected.emit(profile_name))
            self._profiles_menu.addAction(action)
            self._profile_actions[profile] = action

    def set_active_profile(self, profile: str) -> None:
        for name, action in self._profile_actions.items():
            action.blockSignals(True)
            action.setChecked(name == profile)
            action.blockSignals(False)

    def _handle_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.open_config_requested.emit()

    def _refresh_status_display(self) -> None:
        if self._llm_status == "configured":
            llm_text = "LLM: configurado"
            icon = self._normal_icon
        elif self._llm_status == "unavailable":
            llm_text = "LLM: no operativo"
            icon = self._unavailable_llm_icon
        else:
            llm_text = "LLM: sin configurar"
            icon = self._unavailable_llm_icon

        if icon.isNull():
            icon = self._normal_icon

        paused_text = " (pausado)" if self._paused else ""
        self._tray.setIcon(icon)
        self._tray.setToolTip(f"dictado{paused_text} - {llm_text}")
        self._llm_status_action.setText(llm_text)

    def _load_icon(self, icon_path: Path) -> QIcon:
        if icon_path.exists():
            return QIcon(str(icon_path))

        fallback = qta.icon("fa5s.microphone", color="#d33a2c")
        if not fallback.isNull():
            return fallback

        app = QApplication.instance()
        if app is not None:
            return app.style().standardIcon(QStyle.StandardPixmap.SP_MediaVolume)
        return QIcon(QPixmap(16, 16))
