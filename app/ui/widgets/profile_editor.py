from __future__ import annotations

from dataclasses import replace

from PyQt6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox, QWidget

from app.models import Profile


LLM_CHAIN_ROWS = 4


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

        self._llm_providers: list[QComboBox] = []
        self._llm_models: list[QComboBox] = []
        self._llm_api_keys: list[QLineEdit] = []
        self._llm_timeouts: list[QDoubleSpinBox] = []
        self._llm_enabled: list[QCheckBox] = []

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
        for index in range(LLM_CHAIN_ROWS):
            layout.addRow(f"LLM {index + 1}", self._build_llm_row())
        self.setLayout(layout)

    def set_profile(self, profile: Profile) -> None:
        self._profile = profile
        stt_config = profile.stt_config
        llm_chain = _profile_llm_chain(profile)

        _set_combo_text(self._stt_provider, profile.stt_provider)
        _set_combo_text(self._stt_model, str(stt_config.get("model", "large-v3-turbo")))
        _set_combo_text(self._stt_device, str(stt_config.get("device", "cuda")))
        _set_combo_text(self._stt_compute_type, str(stt_config.get("compute_type", "float16")))
        self._stt_beam_size.setValue(int(stt_config.get("beam_size", 5)))
        self._stt_local_only.setChecked(bool(stt_config.get("local_files_only", True)))
        self._stt_warmup.setChecked(bool(stt_config.get("warmup_on_startup", True)))

        self._style.setCurrentText(profile.style)
        self._profile_polish.setChecked(profile.polish_enabled)
        for index in range(LLM_CHAIN_ROWS):
            item = llm_chain[index] if index < len(llm_chain) else {}
            provider = str(item.get("provider", ""))
            _set_combo_text(self._llm_providers[index], provider)
            _set_model_options(self._llm_models[index], provider)
            _set_combo_text(self._llm_models[index], str(item.get("model", "")))
            self._llm_api_keys[index].setText(str(item.get("api_key", "")))
            self._llm_timeouts[index].setValue(float(item.get("timeout", 10.0)))
            self._llm_enabled[index].setChecked(bool(item.get("enabled", bool(provider))))
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
        llm_chain = self._llm_chain()

        return replace(
            self._profile,
            stt_provider=self._stt_provider.currentText().strip() or "faster-whisper",
            llm_provider=None,
            llm_fallback_provider=None,
            style=self._style.currentText(),
            polish_enabled=self._profile_polish.isChecked(),
            inject_raw_first=False,
            stt_config=stt_config,
            llm_config=None,
            llm_fallback_config=None,
            llm_chain=llm_chain,
        )

    def _build_llm_row(self) -> QWidget:
        provider = QComboBox()
        provider.setEditable(True)
        provider.addItems(["", "fireworks", "google", "groq"])

        model = QComboBox()
        model.setEditable(True)

        api_key = QLineEdit()
        api_key.setEchoMode(QLineEdit.EchoMode.Password)
        api_key.setPlaceholderText("API key")

        timeout = QDoubleSpinBox()
        timeout.setRange(1.0, 60.0)
        timeout.setSingleStep(0.5)
        timeout.setValue(10.0)

        enabled = QCheckBox("Activo")

        provider.currentTextChanged.connect(lambda text, combo=model: _set_model_options(combo, text))
        _set_model_options(model, "")

        self._llm_providers.append(provider)
        self._llm_models.append(model)
        self._llm_api_keys.append(api_key)
        self._llm_timeouts.append(timeout)
        self._llm_enabled.append(enabled)

        layout = QHBoxLayout()
        layout.addWidget(provider, 1)
        layout.addWidget(model, 2)
        layout.addWidget(api_key, 2)
        layout.addWidget(timeout)
        layout.addWidget(enabled)
        row = QWidget()
        row.setLayout(layout)
        return row

    def _llm_chain(self) -> list[dict]:
        chain = []
        for provider, model, api_key, timeout, enabled in zip(
            self._llm_providers,
            self._llm_models,
            self._llm_api_keys,
            self._llm_timeouts,
            self._llm_enabled,
        ):
            provider_name = provider.currentText().strip()
            if not provider_name:
                continue
            item = {
                "provider": provider_name,
                "model": model.currentText().strip(),
                "api_key": api_key.text().strip(),
                "timeout": float(timeout.value()),
                "enabled": enabled.isChecked(),
            }
            chain.append(item)
        return chain

    def _update_polish_fields(self, enabled: bool) -> None:
        for widget in [*self._llm_providers, *self._llm_models, *self._llm_api_keys, *self._llm_timeouts, *self._llm_enabled]:
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


def _profile_llm_chain(profile: Profile) -> list[dict]:
    if profile.llm_chain:
        return [dict(item) for item in profile.llm_chain]
    chain = []
    if profile.llm_provider:
        item = dict(profile.llm_config or {})
        item["provider"] = profile.llm_provider
        item.setdefault("enabled", True)
        chain.append(item)
    if profile.llm_fallback_provider:
        item = dict(profile.llm_fallback_config or {})
        item["provider"] = profile.llm_fallback_provider
        item.setdefault("enabled", True)
        chain.append(item)
    return chain


def _set_model_options(combo: QComboBox, provider: str) -> None:
    current = combo.currentText()
    combo.clear()
    options = {
        "fireworks": ["accounts/fireworks/models/minimax-m2p7", "accounts/fireworks/models/gpt-oss-120b"],
        "google": ["gemini-flash-lite-latest", "gemini-flash-latest"],
        "groq": ["qwen/qwen3-32b"],
    }
    combo.addItems(options.get(provider.strip(), []))
    if current:
        _set_combo_text(combo, current)
