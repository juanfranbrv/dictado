from __future__ import annotations

from pathlib import Path

import httpx
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import Config, save_config
from app.storage.vocabulary import VocabularyStore
from app.utils.audio_devices import list_input_devices
from app.ui.widgets.hotkey_input import HotkeyInput
from app.ui.widgets.profile_editor import ProfileEditor
from app.utils.paths import whisper_models_dir


class ConfigWindow(QMainWindow):
    config_saved = pyqtSignal(object)

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config
        self._vocabulary = VocabularyStore()
        self._profile_editors_dirty = False

        self.setWindowTitle("dictado - Configuracion")
        self.resize(760, 620)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_general_tab(), "General")
        self._tabs.addTab(self._build_hotkeys_tab(), "Hotkeys")
        self._tabs.addTab(self._build_profiles_tab(), "Perfiles")
        self._tabs.addTab(self._build_models_tab(), "Modelos")
        self._tabs.addTab(self._build_dictionary_tab(), "Diccionario")
        self._tabs.addTab(_placeholder("El historial se conectara a SQLite en Fase 8."), "Historial")
        self._tabs.addTab(self._build_about_tab(), "Acerca de")

        save_button = QPushButton("Guardar")
        save_button.clicked.connect(self._save)
        reload_button = QPushButton("Recargar")
        reload_button.clicked.connect(lambda: self.load_config(self._config))

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(reload_button)
        buttons.addWidget(save_button)

        layout = QVBoxLayout()
        layout.addWidget(self._tabs)
        layout.addLayout(buttons)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
        self.load_config(config)

    def load_config(self, config: Config) -> None:
        self._config = config
        self._active_profile.clear()
        self._active_profile.addItems(sorted(config.profiles))
        self._active_profile.setCurrentText(config.app.active_profile)
        self._overlay_enabled.setChecked(config.overlay.enabled)
        self._reload_audio_devices(config.audio.device)
        self._injection_method.setCurrentText(config.injection.method)
        self._update_injection_help(self._injection_method.currentText())

        self._record_hotkey.setText(config.hotkey.combo)
        self._force_es_hotkey.setText(config.hotkey.force_language_es)
        self._force_en_hotkey.setText(config.hotkey.force_language_en)

        self._profile_selector.clear()
        self._profile_selector.addItems(sorted(config.profiles))
        self._profile_selector.setCurrentText(config.app.active_profile)
        self._load_selected_profile()
        self._refresh_vocabulary_terms()

    def _build_general_tab(self) -> QWidget:
        self._active_profile = QComboBox()
        self._overlay_enabled = QCheckBox("Mostrar overlay")
        self._audio_device = QComboBox()
        self._audio_device_help = QLabel(
            "Microfono: si dejas `Predeterminado del sistema`, la app usara el micro activo de Windows. "
            "Si eliges uno concreto, quedara fijado solo para esta instalacion mientras exista ese dispositivo."
        )
        self._audio_device_help.setWordWrap(True)
        self._injection_method = QComboBox()
        self._injection_method.addItems(["sendinput", "clipboard"])
        self._injection_method.currentTextChanged.connect(self._update_injection_help)
        self._injection_help = QLabel()
        self._injection_help.setWordWrap(True)

        layout = QFormLayout()
        layout.addRow("Perfil activo", self._active_profile)
        layout.addRow("", self._overlay_enabled)
        layout.addRow("Microfono", self._audio_device)
        layout.addRow("", self._audio_device_help)
        layout.addRow("Metodo de inyeccion", self._injection_method)
        layout.addRow("", self._injection_help)

        tab = QWidget()
        tab.setLayout(layout)
        return tab

    def _build_hotkeys_tab(self) -> QWidget:
        self._record_hotkey = HotkeyInput()
        self._force_es_hotkey = HotkeyInput()
        self._force_en_hotkey = HotkeyInput()

        layout = QFormLayout()
        layout.addRow("Grabar", self._record_hotkey)
        layout.addRow("Forzar ES", self._force_es_hotkey)
        layout.addRow("Forzar EN", self._force_en_hotkey)

        tab = QWidget()
        tab.setLayout(layout)
        return tab

    def _build_profiles_tab(self) -> QWidget:
        self._profile_selector = QComboBox()
        self._profile_selector.currentTextChanged.connect(self._load_selected_profile)
        self._profile_editor = ProfileEditor()
        note = QLabel(
            "Cada perfil define como escucha Whisper y, opcionalmente, como se pule el texto. "
            "Usa un perfil rapido para dictado inmediato y otro mas fino para textos largos o tecnicos."
        )
        note.setWordWrap(True)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Perfil"))
        layout.addWidget(self._profile_selector)
        layout.addWidget(note)
        layout.addWidget(self._profile_editor)

        tab = QWidget()
        tab.setLayout(layout)
        return tab

    def _build_models_tab(self) -> QWidget:
        self._ollama_models = QListWidget()
        self._whisper_models = QListWidget()

        refresh_ollama = QPushButton("Actualizar Ollama")
        refresh_ollama.clicked.connect(self._refresh_ollama_models)
        refresh_whisper = QPushButton("Actualizar Whisper local")
        refresh_whisper.clicked.connect(self._refresh_whisper_models)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Modelos Ollama"))
        layout.addWidget(self._ollama_models)
        layout.addWidget(refresh_ollama)
        layout.addWidget(QLabel("Modelos Whisper descargados"))
        layout.addWidget(self._whisper_models)
        layout.addWidget(refresh_whisper)

        tab = QWidget()
        tab.setLayout(layout)
        return tab

    def _build_dictionary_tab(self) -> QWidget:
        self._vocab_table = QTableWidget(0, 5)
        self._vocab_table.setHorizontalHeaderLabels(["ID", "Termino", "Idioma", "Peso", "Activo"])
        self._vocab_table.setColumnHidden(0, True)
        self._vocab_table.itemSelectionChanged.connect(self._load_selected_vocabulary_term)

        self._vocab_term = QLineEdit()
        self._vocab_language = QComboBox()
        self._vocab_language.addItems(["auto", "es", "en"])
        self._vocab_weight = QSpinBox()
        self._vocab_weight.setRange(1, 100)
        self._vocab_weight.setValue(10)
        self._vocab_enabled = QCheckBox("Activo")
        self._vocab_enabled.setChecked(True)

        add_button = QPushButton("Añadir")
        add_button.clicked.connect(self._add_vocabulary_term)
        update_button = QPushButton("Actualizar")
        update_button.clicked.connect(self._update_vocabulary_term)
        delete_button = QPushButton("Eliminar")
        delete_button.clicked.connect(self._delete_vocabulary_term)
        refresh_button = QPushButton("Recargar")
        refresh_button.clicked.connect(self._refresh_vocabulary_terms)

        form = QFormLayout()
        form.addRow("Termino", self._vocab_term)
        form.addRow("Idioma", self._vocab_language)
        form.addRow("Peso", self._vocab_weight)
        form.addRow("", self._vocab_enabled)

        buttons = QHBoxLayout()
        buttons.addWidget(add_button)
        buttons.addWidget(update_button)
        buttons.addWidget(delete_button)
        buttons.addStretch(1)
        buttons.addWidget(refresh_button)

        note = QLabel("Los terminos se pasan como hints a Whisper antes de transcribir. No bloquean la inyeccion.")
        note.setWordWrap(True)

        layout = QVBoxLayout()
        layout.addWidget(note)
        layout.addWidget(self._vocab_table)
        layout.addLayout(form)
        layout.addLayout(buttons)

        tab = QWidget()
        tab.setLayout(layout)
        return tab

    def _build_about_tab(self) -> QWidget:
        intro = QLabel(
            "dictado es una herramienta gratuita y open source de dictado por voz para Windows. "
            "La idea es ofrecer un flujo local-first, configurable y util para escribir con voz sin depender "
            "de soluciones cerradas."
        )
        intro.setWordWrap(True)

        details = QLabel(
            "El programa se distribuye tal cual, sin garantias, y puede combinar componentes locales "
            "y servicios externos opcionales segun la configuracion que elijas."
        )
        details.setWordWrap(True)

        author = QLabel(
            'Autor: Juan Francisco Briva Casas<br>'
            'Twitter / X: <a href="https://x.com/juanfranbrv">https://x.com/juanfranbrv</a>'
        )
        author.setWordWrap(True)
        author.setOpenExternalLinks(True)

        thanks = QLabel(
            "Si la herramienta te resulta util, puedes seguir el proyecto, compartirlo o contribuir con ideas y mejoras."
        )
        thanks.setWordWrap(True)

        layout = QVBoxLayout()
        layout.addWidget(intro)
        layout.addWidget(details)
        layout.addWidget(author)
        layout.addWidget(thanks)
        layout.addStretch(1)

        tab = QWidget()
        tab.setLayout(layout)
        return tab

    def _load_selected_profile(self) -> None:
        profile_name = self._profile_selector.currentText()
        if not profile_name or profile_name not in self._config.profiles:
            return
        self._profile_editor.set_profile(self._config.profiles[profile_name])

    def _save_current_profile(self, profiles: dict) -> bool:
        profile_name = self._profile_selector.currentText()
        edited = self._profile_editor.profile()
        if not profile_name or edited is None:
            return edited is not None
        profiles[profile_name] = edited
        return True

    def _save(self) -> None:
        profiles = dict(self._config.profiles)
        if not self._save_current_profile(profiles):
            return

        app = self._config.app.model_copy(
            update={
                "active_profile": self._active_profile.currentText(),
            }
        )
        hotkey = self._config.hotkey.model_copy(
            update={
                "combo": self._record_hotkey.text().strip(),
                "force_language_es": self._force_es_hotkey.text().strip(),
                "force_language_en": self._force_en_hotkey.text().strip(),
            }
        )
        overlay = self._config.overlay.model_copy(update={"enabled": self._overlay_enabled.isChecked()})
        audio = self._config.audio.model_copy(update={"device": self._selected_audio_device()})
        injection = self._config.injection.model_copy(update={"method": self._injection_method.currentText()})
        updated = self._config.model_copy(
            update={
                "app": app,
                "hotkey": hotkey,
                "audio": audio,
                "overlay": overlay,
                "injection": injection,
                "profiles": profiles,
            }
        )
        updated._config_path = self._config._config_path
        save_config(updated)
        self._config = updated
        self.config_saved.emit(updated)
        QMessageBox.information(self, "Configuracion guardada", "Cambios guardados. Las hotkeys se aplicaran al reiniciar.")

    def _refresh_ollama_models(self) -> None:
        self._ollama_models.clear()
        endpoint = "http://localhost:11434"
        profile = self._config.profiles.get(self._active_profile.currentText())
        if profile and profile.llm_config:
            endpoint = str(profile.llm_config.get("endpoint", endpoint))

        try:
            response = httpx.get(f"{endpoint.rstrip('/')}/api/tags", timeout=2.0)
            response.raise_for_status()
            models = response.json().get("models", [])
        except Exception as exc:
            self._ollama_models.addItem(f"No se pudo consultar Ollama: {exc}")
            return

        if not models:
            self._ollama_models.addItem("No hay modelos Ollama disponibles.")
            return
        for model in models:
            self._ollama_models.addItem(str(model.get("name", model)))

    def _refresh_whisper_models(self) -> None:
        self._whisper_models.clear()
        cache_dir = whisper_models_dir()
        if not cache_dir.exists():
            self._whisper_models.addItem(f"No existe directorio local: {cache_dir}")
            return
        matches = sorted(path.name for path in cache_dir.iterdir() if path.is_dir())
        if not matches:
            self._whisper_models.addItem("No se encontraron modelos Whisper descargados.")
            return
        self._whisper_models.addItems(matches)

    def _refresh_vocabulary_terms(self) -> None:
        if not hasattr(self, "_vocab_table"):
            return

        terms = self._vocabulary.list_terms(include_disabled=True)
        self._vocab_table.setRowCount(len(terms))
        for row_index, term in enumerate(terms):
            values = [
                str(term.id),
                term.term,
                term.language,
                str(term.weight),
                "si" if term.enabled else "no",
            ]
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                self._vocab_table.setItem(row_index, column_index, item)
        self._vocab_table.resizeColumnsToContents()

    def _selected_vocabulary_id(self) -> int | None:
        row = self._vocab_table.currentRow()
        if row < 0:
            return None
        item = self._vocab_table.item(row, 0)
        if item is None:
            return None
        return int(item.text())

    def _load_selected_vocabulary_term(self) -> None:
        row = self._vocab_table.currentRow()
        if row < 0:
            return
        term_item = self._vocab_table.item(row, 1)
        language_item = self._vocab_table.item(row, 2)
        weight_item = self._vocab_table.item(row, 3)
        enabled_item = self._vocab_table.item(row, 4)
        if term_item is None or language_item is None or weight_item is None or enabled_item is None:
            return

        self._vocab_term.setText(term_item.text())
        self._vocab_language.setCurrentText(language_item.text())
        self._vocab_weight.setValue(int(weight_item.text()))
        self._vocab_enabled.setChecked(enabled_item.text() == "si")

    def _add_vocabulary_term(self) -> None:
        self._vocabulary.add_term(
            self._vocab_term.text(),
            self._vocab_language.currentText(),
            self._vocab_weight.value(),
            self._vocab_enabled.isChecked(),
        )
        self._refresh_vocabulary_terms()

    def _update_vocabulary_term(self) -> None:
        term_id = self._selected_vocabulary_id()
        if term_id is None:
            return
        self._vocabulary.update_term(
            term_id,
            self._vocab_term.text(),
            self._vocab_language.currentText(),
            self._vocab_weight.value(),
            self._vocab_enabled.isChecked(),
        )
        self._refresh_vocabulary_terms()

    def _delete_vocabulary_term(self) -> None:
        term_id = self._selected_vocabulary_id()
        if term_id is None:
            return
        self._vocabulary.delete_term(term_id)
        self._refresh_vocabulary_terms()

    def _update_injection_help(self, method: str) -> None:
        messages = {
            "sendinput": (
                "Metodo de inyeccion 1: `sendinput`. Escribe caracter a caracter como si fueras tecleando. "
                "Suele ser el metodo mas rapido y natural para Notepad, VSCode o campos de texto normales."
            ),
            "clipboard": (
                "Metodo de inyeccion 2: `clipboard`. Copia temporalmente el texto al portapapeles y pega con `Ctrl+V`. "
                "Es mas compatible en apps donde la escritura simulada falla, pero puede resultar algo menos elegante."
            ),
        }
        self._injection_help.setText(messages.get(method, "Selecciona como quieres insertar el texto en la app activa."))

    def _reload_audio_devices(self, configured_device: str) -> None:
        current_data = self._audio_device.currentData()
        expected = configured_device.strip() if configured_device.strip() else current_data
        self._audio_device.clear()
        self._audio_device.addItem("Predeterminado del sistema", "")
        matched_index = 0
        for device in list_input_devices():
            self._audio_device.addItem(device.label, device.label)
            if device.label == expected or device.name == expected:
                matched_index = self._audio_device.count() - 1
        self._audio_device.setCurrentIndex(matched_index)

    def _selected_audio_device(self) -> str:
        data = self._audio_device.currentData()
        if isinstance(data, str):
            return data
        return ""


def _placeholder(text: str) -> QWidget:
    layout = QVBoxLayout()
    label = QLabel(text)
    label.setWordWrap(True)
    layout.addWidget(label)
    layout.addStretch(1)
    tab = QWidget()
    tab.setLayout(layout)
    return tab
