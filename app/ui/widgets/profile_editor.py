from __future__ import annotations

from dataclasses import replace

from PyQt6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QLabel, QLineEdit, QSpinBox, QWidget

from app.models import Profile


class ProfileEditor(QWidget):
    """Edit one profile with user-facing controls instead of raw JSON."""

    def __init__(self) -> None:
        super().__init__()
        self._profile: Profile | None = None

        self._stt_provider = QComboBox()
        self._stt_provider.addItems(["faster-whisper"])
        self._stt_provider.setToolTip("Motor de transcripcion de voz. Ahora mismo la app usa faster-whisper.")
        self._stt_model = QComboBox()
        self._stt_model.setEditable(True)
        self._stt_model.addItems(["large-v3-turbo", "large-v3", "medium", "small"])
        self._stt_model.setToolTip("Modelo Whisper. Los grandes entienden mejor, los pequeños suelen ser mas rapidos.")
        self._stt_device = QComboBox()
        self._stt_device.addItems(["cuda", "cpu"])
        self._stt_device.setToolTip("Dónde corre Whisper. `cuda` usa GPU NVIDIA; `cpu` usa procesador.")
        self._stt_compute_type = QComboBox()
        self._stt_compute_type.addItems(["float16", "int8_float16", "int8", "float32"])
        self._stt_compute_type.setToolTip(
            "Precision numerica. `float16` suele dar buena calidad en GPU. `int8` reduce consumo con algo menos de precision."
        )
        self._stt_beam_size = QSpinBox()
        self._stt_beam_size.setRange(1, 10)
        self._stt_beam_size.setToolTip(
            "Beam size = cuantas alternativas explora Whisper antes de decidir. "
            "Mas alto mejora estabilidad, mas bajo suele ser mas rapido."
        )
        self._stt_local_only = QCheckBox("Usar solo modelos locales")
        self._stt_local_only.setToolTip("Si esta activo, Whisper no intenta descargar modelos en tiempo de ejecucion.")
        self._stt_warmup = QCheckBox("Calentar modelo al arrancar")
        self._stt_warmup.setToolTip("Carga el modelo al iniciar la app para que el primer dictado no sea tan lento.")

        self._style = QComboBox()
        self._style.addItems(["default", "casual", "technical", "code"])
        self._style.setToolTip("Indica el tono de microcorreccion que aplicara el pulido.")
        self._profile_polish = QCheckBox("Activar pulido en este perfil")
        self._profile_polish.toggled.connect(self._update_polish_fields)
        self._profile_polish.setToolTip("Si lo activas, tras la transcripcion se intenta limpiar puntuacion y errores obvios.")

        self._llm_provider = QComboBox()
        self._llm_provider.setEditable(True)
        self._llm_provider.addItems(["", "groq", "gemini", "ollama"])
        self._llm_provider.setToolTip("Proveedor del modelo que pule el texto despues de Whisper.")
        self._llm_model = QLineEdit()
        self._llm_model.setToolTip("Nombre exacto del modelo dentro del proveedor elegido.")
        self._llm_api_key = QLineEdit()
        self._llm_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._llm_api_key.setToolTip("Clave API del proveedor. Se guarda en tu config local.")
        self._llm_timeout = QDoubleSpinBox()
        self._llm_timeout.setRange(1.0, 60.0)
        self._llm_timeout.setSingleStep(0.5)
        self._llm_timeout.setToolTip(
            "Tiempo maximo de espera para el pulido. Si el modelo tarda mas, se cancela y se usa el texto crudo."
        )

        self._fallback_provider = QComboBox()
        self._fallback_provider.setEditable(True)
        self._fallback_provider.addItems(["", "gemini", "groq", "ollama"])
        self._fallback_provider.setToolTip("Proveedor de reserva si falla el LLM principal.")
        self._fallback_model = QLineEdit()
        self._fallback_model.setToolTip("Modelo de reserva.")
        self._fallback_api_key = QLineEdit()
        self._fallback_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._fallback_api_key.setToolTip("Clave API para el proveedor de fallback.")
        self._fallback_timeout = QDoubleSpinBox()
        self._fallback_timeout.setRange(1.0, 60.0)
        self._fallback_timeout.setSingleStep(0.5)
        self._fallback_timeout.setToolTip("Tiempo maximo de espera para el modelo de reserva.")
        self._fallback_enabled = QCheckBox("Fallback activo")
        self._fallback_enabled.setToolTip("Si esta activo, se podra usar un segundo modelo cuando falle el principal.")

        self._stt_help = QLabel(
            "Whisper convierte tu voz en texto. Aqui ajustas velocidad, calidad y uso de GPU/CPU."
        )
        self._stt_help.setWordWrap(True)
        self._llm_help = QLabel(
            "El LLM pule la transcripcion: puntuacion, mayusculas y errores obvios. "
            "Si no lo necesitas, puedes desactivarlo en este perfil."
        )
        self._llm_help.setWordWrap(True)

        layout = QFormLayout()
        layout.addRow("", self._stt_help)
        layout.addRow("STT provider", self._stt_provider)
        layout.addRow("Modelo Whisper", self._stt_model)
        layout.addRow("Dispositivo", self._stt_device)
        layout.addRow("Precision", self._stt_compute_type)
        layout.addRow("Beam size", self._stt_beam_size)
        layout.addRow("", self._stt_local_only)
        layout.addRow("", self._stt_warmup)
        layout.addRow("Estilo", self._style)
        layout.addRow("", self._profile_polish)
        layout.addRow("", self._llm_help)
        layout.addRow("LLM principal", self._llm_provider)
        layout.addRow("Modelo LLM", self._llm_model)
        layout.addRow("API key", self._llm_api_key)
        layout.addRow("Timeout LLM", self._llm_timeout)
        layout.addRow("LLM fallback", self._fallback_provider)
        layout.addRow("Modelo fallback", self._fallback_model)
        layout.addRow("API key fallback", self._fallback_api_key)
        layout.addRow("Timeout fallback", self._fallback_timeout)
        layout.addRow("", self._fallback_enabled)
        self.setLayout(layout)

    def set_profile(self, profile: Profile) -> None:
        self._profile = profile
        stt_config = profile.stt_config
        llm_config = profile.llm_config or {}
        fallback_config = profile.llm_fallback_config or {}

        _set_combo_text(self._stt_provider, profile.stt_provider)
        _set_combo_text(self._stt_model, str(stt_config.get("model", "large-v3-turbo")))
        _set_combo_text(self._stt_device, str(stt_config.get("device", "cuda")))
        _set_combo_text(self._stt_compute_type, str(stt_config.get("compute_type", "float16")))
        self._stt_beam_size.setValue(int(stt_config.get("beam_size", 5)))
        self._stt_local_only.setChecked(bool(stt_config.get("local_files_only", True)))
        self._stt_warmup.setChecked(bool(stt_config.get("warmup_on_startup", True)))

        self._style.setCurrentText(profile.style)
        self._profile_polish.setChecked(profile.polish_enabled)
        _set_combo_text(self._llm_provider, profile.llm_provider or "")
        self._llm_model.setText(str(llm_config.get("model", "")))
        self._llm_api_key.setText(str(llm_config.get("api_key", "")))
        self._llm_timeout.setValue(float(llm_config.get("timeout", 6.0)))

        _set_combo_text(self._fallback_provider, profile.llm_fallback_provider or "")
        self._fallback_model.setText(str(fallback_config.get("model", "")))
        self._fallback_api_key.setText(str(fallback_config.get("api_key", "")))
        self._fallback_timeout.setValue(float(fallback_config.get("timeout", 10.0)))
        self._fallback_enabled.setChecked(bool(fallback_config.get("enabled", bool(profile.llm_fallback_provider))))
        self._update_polish_fields(profile.polish_enabled)

    def profile(self) -> Profile | None:
        if self._profile is None:
            return None

        stt_config = {
            "model": self._stt_model.currentText().strip() or "large-v3-turbo",
            "device": self._stt_device.currentText().strip() or "cuda",
            "compute_type": self._stt_compute_type.currentText().strip() or "float16",
            "local_files_only": self._stt_local_only.isChecked(),
            "warmup_on_startup": self._stt_warmup.isChecked(),
            "beam_size": self._stt_beam_size.value(),
        }
        llm_provider = self._llm_provider.currentText().strip() or None
        fallback_provider = self._fallback_provider.currentText().strip() or None
        llm_config = _llm_config(self._llm_model.text(), self._llm_api_key.text(), self._llm_timeout.value())
        fallback_config = _llm_config(
            self._fallback_model.text(),
            self._fallback_api_key.text(),
            self._fallback_timeout.value(),
            enabled=self._fallback_enabled.isChecked(),
        )

        return replace(
            self._profile,
            stt_provider=self._stt_provider.currentText().strip() or "faster-whisper",
            llm_provider=llm_provider,
            llm_fallback_provider=fallback_provider,
            style=self._style.currentText(),
            polish_enabled=self._profile_polish.isChecked(),
            inject_raw_first=False,
            stt_config=stt_config,
            llm_config=llm_config if llm_provider else None,
            llm_fallback_config=fallback_config if fallback_provider else None,
        )

    def _update_polish_fields(self, enabled: bool) -> None:
        for widget in (
            self._llm_provider,
            self._llm_model,
            self._llm_api_key,
            self._llm_timeout,
            self._fallback_provider,
            self._fallback_model,
            self._fallback_api_key,
            self._fallback_timeout,
            self._fallback_enabled,
        ):
            widget.setEnabled(enabled)


def _set_combo_text(combo: QComboBox, value: str) -> None:
    index = combo.findText(value)
    if index >= 0:
        combo.setCurrentIndex(index)
    else:
        combo.setCurrentText(value)


def _llm_config(model: str, api_key: str, timeout: float, enabled: bool | None = None) -> dict:
    config = {"model": model.strip(), "timeout": float(timeout)}
    if api_key.strip():
        config["api_key"] = api_key.strip()
    if enabled is not None:
        config["enabled"] = enabled
    return config
