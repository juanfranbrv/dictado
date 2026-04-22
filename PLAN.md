# VibeDictate — Plan de Desarrollo

> Sistema de dictado por voz para Windows, local-first, multiidioma (ES/EN), con arquitectura modular de modelos intercambiables. Uso personal, filosofía VibeCoding.

---

## 1. Resumen del proyecto

**Qué**: Aplicación Windows tipo Wispr Flow. Pulsas una hotkey, hablas, se transcribe con IA local, se inyecta el texto en la ventana activa.

**Por qué local**: Privacidad total, latencia predecible, sin costes recurrentes, mejor que el dictado nativo de Windows.

**Hardware objetivo**: RTX 5070 Ti (16GB VRAM) + 64GB RAM. Todo corre en local sin problema.

**Filosofía de código**: VibeCoding — el usuario describe qué quiere, Claude genera y mantiene el código. El plan debe ser lo suficientemente específico para que Claude pueda implementar sin decisiones ambiguas.

**Idiomas**: Bilingüe ES/EN con autodetección por histéresis.

**No-objetivos (para evitar scope creep)**:
- NO comandos de voz (solo dictado)
- NO cloud por defecto (opcional como backend secundario)
- NO monetización, NO multi-usuario, NO cuentas
- NO soporte Mac/Linux en fase inicial

---

## 2. Decisiones clave

| Área | Decisión | Motivo |
|------|----------|--------|
| Lenguaje | Python 3.11+ | Ecosistema AI, simplicidad, un solo lenguaje |
| Gestión deps | `uv` | Rápido, moderno, reemplaza pip+venv+poetry |
| STT default | `faster-whisper` + Whisper Large-v3 Turbo | Mejor calidad/velocidad bilingüe en GPU |
| LLM polish | `Ollama` + Qwen2.5 7B | Local, buena calidad, fácil swap de modelos |
| UI | `PyQt6` | Pure Python, tray + overlay + config en un solo stack |
| Hotkey global | `pynput` | Multiplataforma, API limpia |
| Inyección texto | `SendInput` vía `ctypes` (Win32) | Máxima velocidad y fiabilidad |
| Audio | `sounddevice` | Simple, bajo nivel, sin dependencias pesadas |
| Config | `TOML` vía `tomllib` + `tomli-w` | Nativo Python 3.11+, legible |
| Logging | `loguru` | Zero-config, formato bonito |
| Tests (opcional) | `pytest` | Estándar |
| Empaquetado | `PyInstaller` | Produce .exe Windows |

Todas son **decisiones revisables** — la arquitectura de providers permite cambiar cualquier modelo sin tocar el core.

---

## 3. Arquitectura

### 3.1 Componentes principales

```
┌─────────────────────────────────────────────────────────────┐
│                        UI Layer                              │
│   ┌──────────┐  ┌─────────────┐  ┌──────────────────┐       │
│   │   Tray   │  │   Overlay   │  │  Config Window   │       │
│   └──────────┘  └─────────────┘  └──────────────────┘       │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                       Core Pipeline                          │
│   ┌──────┐  ┌────────┐  ┌─────────┐  ┌────────┐  ┌───────┐  │
│   │Hotkey├─▶│Recorder├─▶│Pipeline ├─▶│Polisher├─▶│Injector│  │
│   └──────┘  └────────┘  └────┬────┘  └────────┘  └───────┘  │
│                              │                               │
└──────────────────────────────┼───────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    Providers Layer                           │
│   ┌──────────────────┐        ┌──────────────────┐          │
│   │  STT Providers   │        │  LLM Providers   │          │
│   │  - faster_whisper│        │  - ollama        │          │
│   │  - groq          │        │  - openai        │          │
│   │  - openai        │        │  - anthropic     │          │
│   │  - ...           │        │  - ...           │          │
│   └──────────────────┘        └──────────────────┘          │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                      Storage Layer                           │
│   ┌──────────┐  ┌──────────────┐  ┌───────────────────┐     │
│   │  Config  │  │  Vocabulary  │  │  History/Corrections│   │
│   │  (TOML)  │  │   (SQLite)   │  │     (SQLite)      │     │
│   └──────────┘  └──────────────┘  └───────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Flujo de datos (happy path)

1. `Hotkey` detecta pulsación → emite evento `START_RECORDING`
2. `Recorder` abre stream de micro → acumula audio en buffer numpy
3. Usuario suelta hotkey (o pulsa otra vez en modo toggle) → evento `STOP_RECORDING`
4. `Pipeline` recibe audio → consulta `LanguageHysteresis` → selecciona idioma hipótesis
5. `Pipeline` llama a `STTProvider.transcribe(audio, language)` → obtiene `Transcript`
6. `Injector` inyecta **texto crudo inmediatamente** vía SendInput (latencia visible < 500ms)
7. `Pipeline` lanza en background `LLMProvider.polish(transcript)` con vocabulario + contexto
8. Cuando `polish` termina, `Injector` selecciona el texto previo y lo reemplaza (si el usuario no ha tipeado encima)
9. `History` persiste la transcripción + polish para aprendizaje

### 3.3 Interfaces (Protocols)

Usamos `typing.Protocol` — duck typing tipado, sin herencia obligatoria.

```python
# app/providers/stt/base.py
from typing import Protocol
import numpy as np
from app.models import Transcript

class STTProvider(Protocol):
    name: str

    def transcribe(
        self,
        audio: np.ndarray,       # float32, mono, 16kHz
        language: str | None,    # "es", "en", None=autodetect
        hints: list[str] | None = None,  # vocabulario personalizado
    ) -> Transcript: ...

    def warmup(self) -> None: ...
    def unload(self) -> None: ...

# app/providers/llm/base.py
class LLMProvider(Protocol):
    name: str

    def polish(
        self,
        text: str,
        language: str,
        context: PolishContext,  # app activa, estilo, vocabulario, ejemplos
    ) -> str: ...

    def warmup(self) -> None: ...
    def unload(self) -> None: ...
```

### 3.4 Registry y factory

```python
# app/providers/stt/registry.py
_STT_REGISTRY: dict[str, type[STTProvider]] = {}

def register_stt(name: str):
    def decorator(cls):
        _STT_REGISTRY[name] = cls
        return cls
    return decorator

def create_stt(name: str, **kwargs) -> STTProvider:
    if name not in _STT_REGISTRY:
        raise ValueError(f"STT provider '{name}' no registrado")
    return _STT_REGISTRY[name](**kwargs)
```

Cada provider se auto-registra:

```python
# app/providers/stt/faster_whisper.py
@register_stt("faster-whisper")
class FasterWhisperSTT:
    name = "faster-whisper"
    def __init__(self, model: str, device: str, compute_type: str):
        ...
```

Añadir un modelo nuevo = un archivo nuevo + import en `__init__.py`. Cero cambios en el core.

### 3.5 Ciclo de vida de modelos

- **Lazy init**: el provider se instancia al primer uso de su perfil
- **Warmup opcional**: al cargar, ejecuta una inferencia dummy para calentar CUDA
- **Cache en memoria**: provider actual se mantiene en VRAM entre dictados
- **Hot-swap**: al cambiar perfil → `current.unload()` → `create_stt(new)` → `new.warmup()`
- **Gestor de memoria**: si VRAM < threshold, descarga providers no usados (LRU)

---

## 4. Estructura del proyecto

```
dictado/
├── pyproject.toml              # deps con uv
├── uv.lock
├── README.md
├── PLAN.md                     # este archivo
├── config.toml                 # config usuario (generada al arrancar)
├── config.default.toml         # template con defaults
├── .gitignore
│
├── app/
│   ├── __init__.py
│   ├── main.py                 # entry point, arranca tray + servicios
│   ├── config.py               # carga/valida/guarda TOML
│   ├── models.py               # dataclasses: Transcript, Context, Profile, etc.
│   ├── events.py               # event bus ligero para desacoplar componentes
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── hotkey.py           # listener global (pynput)
│   │   ├── recorder.py         # captura audio (sounddevice)
│   │   ├── pipeline.py         # orquestador: record → stt → polish → inject
│   │   ├── injector.py         # SendInput wrapper
│   │   ├── language.py         # histéresis de idioma
│   │   └── vad.py              # Silero VAD (opcional, fase avanzada)
│   │
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── stt/
│   │   │   ├── __init__.py     # auto-import de todos los providers
│   │   │   ├── base.py         # Protocol + tipos compartidos
│   │   │   ├── registry.py     # register_stt, create_stt
│   │   │   ├── faster_whisper.py
│   │   │   ├── groq.py         # (fase 5)
│   │   │   └── openai.py       # (fase 5)
│   │   └── llm/
│   │       ├── __init__.py
│   │       ├── base.py
│   │       ├── registry.py
│   │       ├── ollama.py
│   │       ├── openai.py       # (fase 5)
│   │       └── anthropic.py    # (fase 5)
│   │
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── tray.py             # icono en bandeja del sistema
│   │   ├── overlay.py          # widget flotante al grabar
│   │   ├── config_window.py    # ventana de configuración
│   │   └── widgets/            # widgets reutilizables
│   │       ├── __init__.py
│   │       ├── hotkey_input.py
│   │       └── profile_editor.py
│   │
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── db.py               # conexión SQLite
│   │   ├── vocabulary.py       # diccionario personalizado
│   │   ├── history.py          # transcripciones pasadas
│   │   └── corrections.py      # ediciones del usuario (aprendizaje)
│   │
│   ├── learning/               # fase 8
│   │   ├── __init__.py
│   │   ├── hints.py            # construye initial_prompt para Whisper
│   │   └── rag.py              # recupera ejemplos para polish
│   │
│   └── utils/
│       ├── __init__.py
│       ├── logging.py          # setup de loguru
│       └── paths.py            # user data dir, modelos, etc.
│
├── tests/                      # opcional, solo si apetece
│   ├── test_language.py
│   └── test_providers.py
│
└── assets/
    ├── icon.png
    └── icon.ico
```

---

## 5. Stack técnico detallado

```toml
# pyproject.toml (extracto)
[project]
name = "dictado"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    # Core
    "numpy>=1.26",
    "sounddevice>=0.4.6",
    "pynput>=1.7.6",
    "pywin32>=306",            # para SendInput fallback y APIs Windows
    "loguru>=0.7",
    "tomli-w>=1.0",            # escritura TOML (lectura es nativa)
    "pydantic>=2.5",           # validación de config

    # STT default
    "faster-whisper>=1.0",
    "ctranslate2>=4.0",

    # LLM default (cliente Ollama)
    "httpx>=0.25",

    # UI
    "PyQt6>=6.6",
    "qtawesome>=1.3",          # iconos bonitos

    # Utilidades
    "platformdirs>=4.0",       # rutas estándar del SO
]

[project.optional-dependencies]
cloud = [
    "groq>=0.4",
    "openai>=1.12",
    "anthropic>=0.20",
]
vad = [
    "silero-vad>=5.0",
]
dev = [
    "pytest>=8.0",
    "ruff>=0.3",
    "pyinstaller>=6.0",
]
```

---

## 6. Modelo de datos

```python
# app/models.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

Language = Literal["es", "en", "auto"]

@dataclass
class Transcript:
    """Salida de un STTProvider."""
    text: str                          # texto crudo transcrito
    language: str                      # idioma detectado
    language_confidence: float         # 0-1
    duration_seconds: float            # duración del audio
    processing_time_seconds: float     # cuánto tardó la transcripción
    segments: list["Segment"] = field(default_factory=list)
    provider: str = ""                 # qué provider lo generó
    model: str = ""                    # qué modelo

@dataclass
class Segment:
    text: str
    start: float
    end: float

@dataclass
class PolishContext:
    """Contexto que se pasa al LLMProvider.polish()."""
    active_app: str | None             # "chrome.exe", "code.exe", etc.
    window_title: str | None
    style: str = "default"             # "default", "casual", "technical", "code"
    vocabulary: list[str] = field(default_factory=list)
    examples: list[tuple[str, str]] = field(default_factory=list)  # (raw, polished)

@dataclass
class Profile:
    """Combinación guardada de providers + parámetros."""
    name: str
    stt_provider: str
    stt_config: dict
    llm_provider: str | None           # None = sin polish
    llm_config: dict | None
    polish_enabled: bool = True
    inject_raw_first: bool = True      # two-stage display
    style: str = "default"

@dataclass
class RecordingSession:
    """Una sesión de grabación completa."""
    id: str
    started_at: datetime
    ended_at: datetime | None
    audio: "np.ndarray | None" = None
    transcript: Transcript | None = None
    polished_text: str | None = None
    injected: bool = False
    user_edited_after: str | None = None   # lo que el usuario dejó al final
```

---

## 7. Configuración (config.default.toml)

```toml
# VibeDictate — configuración por defecto
# Este archivo NO se edita directamente. Copia a config.toml y modifica.

[app]
active_profile = "default"
log_level = "INFO"
first_run = true

[hotkeys]
# Modos: "toggle" (pulsa para empezar, pulsa para parar) o "push" (mantén pulsada)
mode = "toggle"
record = "alt+space"
force_language_es = "alt+shift+s"
force_language_en = "alt+shift+e"
toggle_polish = "alt+shift+p"
open_config = "alt+shift+c"

[audio]
sample_rate = 16000
channels = 1
device = ""                    # "" = default del sistema
max_recording_seconds = 120

[language]
# Lista ordenada de preferencia. La autodetección solo elige entre estos.
preferred = ["es", "en"]
# Umbral bajo el cual se reevalua el idioma
confidence_threshold = 0.75
# Histéresis: penalización para cambiar de idioma (evita flip-flop)
switch_penalty = 0.15

[injection]
# "sendinput" (rápido, Win32) | "clipboard" (fallback, pega con Ctrl+V)
method = "sendinput"
# Si true, intenta seleccionar el texto crudo y reemplazarlo al recibir el polish
replace_after_polish = true
# Delay antes de inyectar (ms) — algunas apps necesitan un respiro
pre_inject_delay_ms = 0

[overlay]
enabled = true
position = "bottom-center"     # "top-left", "top-center", etc.
show_waveform = true
show_language = true

# ──────────── Perfiles ────────────

[profiles.default]
stt_provider = "faster-whisper"
llm_provider = "ollama"
polish_enabled = true
inject_raw_first = true
style = "default"

[profiles.default.stt_config]
model = "large-v3-turbo"
device = "cuda"
compute_type = "int8_float16"
beam_size = 5

[profiles.default.llm_config]
endpoint = "http://localhost:11434"
model = "qwen2.5:7b"
temperature = 0.2
max_tokens = 512

# Perfil rápido (sin polish)
[profiles.fast]
stt_provider = "faster-whisper"
llm_provider = ""
polish_enabled = false

[profiles.fast.stt_config]
model = "large-v3-turbo"
device = "cuda"
compute_type = "int8_float16"
beam_size = 1

# Perfil calidad (modelos grandes)
[profiles.quality]
stt_provider = "faster-whisper"
llm_provider = "ollama"
polish_enabled = true

[profiles.quality.stt_config]
model = "large-v3"
device = "cuda"
compute_type = "float16"
beam_size = 5

[profiles.quality.llm_config]
endpoint = "http://localhost:11434"
model = "qwen2.5:14b"
temperature = 0.2
```

---

## 8. Fases de desarrollo

Cada fase es un **incremento funcional** — al terminar, tienes algo que puedes ejecutar y validar. No se empieza la siguiente hasta que la anterior funciona.

### Fase 0 — Bootstrap

**Objetivo**: Proyecto inicializado, corre un `python -m app.main` que no hace nada aún, pero carga config y logs.

**Entregables**:
- `pyproject.toml` con dependencias mínimas
- Estructura de carpetas
- `app/main.py` con un `if __name__ == "__main__": print("OK")`
- `app/config.py` con carga de TOML + validación Pydantic
- `app/utils/logging.py` con loguru configurado
- `config.default.toml`
- `.gitignore`

**Criterio de aceptación**:
```bash
uv sync
uv run python -m app.main
# imprime "VibeDictate v0.1.0 — config cargada desde ..." y termina
```

---

### Fase 1 — Captura de audio con hotkey

**Objetivo**: Pulsas Alt+Space, graba hasta que vuelves a pulsar, guarda un WAV.

**Entregables**:
- `app/core/hotkey.py` con listener de `pynput` (modo toggle)
- `app/core/recorder.py` con `sounddevice`, acumula en numpy buffer
- `app/events.py` con un EventBus trivial (publisher/subscriber)
- `app/main.py` conecta hotkey → recorder → guarda WAV en `./recordings/`

**Criterio de aceptación**:
- Arrancas app, pulsas Alt+Space, dices algo, pulsas otra vez
- Aparece `recordings/YYYY-MM-DD_HH-MM-SS.wav` reproducible

**Notas**:
- Sin UI aún, solo logs en consola
- El WAV se guarda para poder debuggear transcripciones luego

---

### Fase 2 — STT básico (faster-whisper)

**Objetivo**: El audio capturado se transcribe y el texto se imprime en consola.

**Entregables**:
- `app/providers/stt/base.py` con Protocol + tipos
- `app/providers/stt/registry.py`
- `app/providers/stt/faster_whisper.py` con implementación completa
- `app/providers/stt/__init__.py` auto-importa todos los providers
- `app/core/pipeline.py` básico: recibe audio, llama STT, imprime resultado
- `app/models.py` con `Transcript`, `Segment`

**Criterio de aceptación**:
- Pulsas hotkey, hablas en español, sueltas → consola muestra el texto transcrito en <2s
- Cambias `model = "large-v3-turbo"` vs `"tiny"` en config y ves diferencia de velocidad/calidad
- Primera transcripción es lenta (carga modelo), siguientes son rápidas

**Notas**:
- Todavía sin inyección, sin idioma (lo forzamos a "es" por ahora)
- **Warmup**: al arrancar la app, carga el modelo en GPU y ejecuta una inferencia dummy con 1s de silencio

---

### Fase 3 — Inyección de texto (MVP usable)

**Objetivo**: La app es usable como dictado. Pulsas, hablas, sueltas, aparece el texto en Notepad/Chrome/donde sea.

**Entregables**:
- `app/core/injector.py` con SendInput vía ctypes
- Pipeline completa: hotkey → record → stt → inject
- Overlay mínimo en `app/ui/overlay.py` (PyQt6): círculo rojo pulsando cuando graba
- `app/ui/tray.py`: icono en bandeja con menú (Salir, Abrir config)

**Criterio de aceptación**:
- Abres Notepad, pulsas Alt+Space, dices "hola mundo", sueltas → aparece "hola mundo" en Notepad
- Overlay aparece al grabar, desaparece al inyectar
- Funciona en al menos 3 apps distintas (Notepad, Chrome, VSCode)
- Icono bandeja funciona, permite salir limpiamente

**Notas**:
- Este es el **MVP**. A partir de aquí, cada fase añade valor pero la app ya se usa.
- SendInput tiene particularidades con caracteres Unicode — hay que usar `KEYEVENTF_UNICODE`.

---

### Fase 4 — Multiidioma con histéresis

**Objetivo**: Autodetecta ES/EN con memoria (histéresis), permite override manual por hotkey.

**Entregables**:
- `app/core/language.py` con clase `LanguageHysteresis`:
  - Mantiene último idioma usado (persistido a disco)
  - Pasa ese idioma como hint a Whisper
  - Detecta switch si `language_confidence < threshold + switch_penalty`
- Hotkeys `force_language_es` / `force_language_en` para la siguiente frase
- Overlay muestra el idioma activo (banderita o "ES"/"EN")

**Criterio de aceptación**:
- Dictas 5 frases en español → todas marcadas como "es"
- Dictas 1 frase en inglés → detecta "en", mantiene "en" las siguientes
- Pulsas `force_language_es` → siguiente frase se fuerza a "es" aunque hables inglés

**Notas**:
- La histéresis es clave: Whisper a pelo con `language=None` tarda más y se equivoca en frases cortas.

---

### Fase 5 — Arquitectura de providers + perfiles + hot-swap

**Objetivo**: Refactor para tener múltiples STT y LLM providers intercambiables vía config.

**Entregables**:
- Providers STT adicionales: `groq.py`, `openai.py` (cloud, opcionales)
- Providers LLM: ya tenemos `ollama.py` (se crea aquí), `openai.py`, `anthropic.py`
- `app/models.py` añade `Profile`
- Sistema de perfiles en config
- Hot-swap: cambiar perfil en UI descarga modelo actual y carga el nuevo
- Hotkey para ciclar perfiles (`alt+shift+1`, `alt+shift+2`, etc.)

**Criterio de aceptación**:
- Defines 3 perfiles en `config.toml`
- Al cambiar perfil, se recarga el modelo sin reiniciar app
- VRAM se libera del modelo anterior (verificable con `nvidia-smi`)
- Añadir un provider nuevo = un archivo + 0 cambios en core

**Notas**:
- Aquí es donde se paga la deuda técnica de las fases anteriores. Invierte tiempo en dejar las interfaces limpias.

---

### Fase 6 — LLM post-procesado (two-stage display)

**Objetivo**: Después de transcribir y mostrar el texto crudo, un LLM lo pule y reemplaza.

**Entregables**:
- `app/providers/llm/ollama.py` completo (cliente HTTP a Ollama)
- Pipeline modificada:
  1. STT → inyecta texto crudo
  2. Background: LLM polish → selecciona texto anterior (Ctrl+Shift+Home si es al inicio, o tracking de posición) → inyecta polish
- Prompts de sistema por estilo (`default`, `casual`, `technical`, `code`) en `app/learning/prompts.py`
- Detección de app activa para inferir estilo (Slack → casual, VSCode → code)
- Hotkey `toggle_polish` para activar/desactivar en caliente

**Criterio de aceptación**:
- Dictas "pues mira yo creo que eeeh tenemos que hacer el commit ese que te dije"
- Aparece inmediatamente el texto crudo
- ~1-2s después se reemplaza por: "Creo que tenemos que hacer el commit que te dije."
- Si dictas en VSCode, aplica estilo code (snake_case en identificadores, comentarios, etc.)

**Notas**:
- Reemplazar texto ya inyectado es complicado. Opciones:
  - Trackear posición del cursor y hacer Shift+arrows para seleccionar
  - Usar Ctrl+Z + reinyección (arriesgado, a veces no deshace solo el último)
  - Simplemente mostrar el polish en overlay y que el usuario decida si acepta (menos mágico pero más fiable)
- Empieza por la opción 3 (más simple) y evoluciona.

---

### Fase 7 — UI de configuración

**Objetivo**: Ventana de configuración completa en PyQt6, sin tener que tocar TOML a mano.

**Entregables**:
- `app/ui/config_window.py` con pestañas:
  - **General**: idioma UI, nivel log, arrancar con Windows
  - **Hotkeys**: widget para capturar combos
  - **Perfiles**: list + edit + duplicate + delete
  - **Modelos**: ver modelos descargados, botón "Descargar" (Ollama pull, HF download)
  - **Diccionario**: editar vocabulario personalizado
  - **Historial**: ver transcripciones pasadas, buscar, exportar
- Widget `HotkeyInput` reutilizable
- Widget `ProfileEditor` con todos los parámetros de un perfil
- Abre desde tray icon → "Configuración" o con `open_config` hotkey

**Criterio de aceptación**:
- Todo lo que está en `config.toml` es editable vía UI
- Los cambios se guardan atómicamente (temp file + rename)
- Los cambios se aplican en caliente donde es posible (hotkeys, perfil activo)
- Restart requerido solo para cambios de dispositivo de audio

**Notas**:
- La UI escribe el TOML; no mantiene estado propio. Single source of truth.

---

### Fase 8 — Sistema de aprendizaje

**Objetivo**: La app mejora con el uso.

Tres capas, de más simple a más compleja:

#### 8.1 Diccionario personalizado

**Entregables**:
- `app/storage/vocabulary.py` con SQLite: términos, sinónimos, contexto
- `app/learning/hints.py` construye el `initial_prompt` para Whisper (es un string con palabras clave)
- UI para añadir/editar términos manualmente
- Auto-sugerir términos: si una palabra inventada aparece varias veces en transcripciones, sugerirla

**Criterio de aceptación**:
- Añades "Kubernetes", "pytest", "automatrícula" al diccionario
- Whisper los transcribe correctamente incluso si los dices rápido

#### 8.2 Historial de correcciones

**Entregables**:
- `app/storage/corrections.py`: guarda pares (raw_transcript, polished, user_final_edit)
- Cada X frases, la app ofrece revisar qué correcciones hiciste
- Las correcciones se usan como "examples" en el `PolishContext`

**Criterio de aceptación**:
- Si siempre cambias "ok" por "vale", el polish empieza a hacerlo automático

#### 8.3 RAG para polish

**Entregables**:
- `app/learning/rag.py`: busca ejemplos similares al texto actual
- Inyecta top-3 ejemplos en el prompt del LLM como few-shot
- Embeddings locales con `sentence-transformers`

**Criterio de aceptación**:
- El estilo del polish converge al tuyo con el uso
- Tests A/B: con 0 ejemplos vs con 50 ejemplos tuyos, el output es distinto

---

### Fase 9 — Optimización y empaquetado

**Objetivo**: Rendimiento pulido + instalador Windows.

**Entregables**:
- Profiling con `py-spy` → identifica bottlenecks
- Warmup paralelo (audio + STT + LLM en threads separados)
- Pre-carga de providers al arrancar (configurable)
- `PyInstaller` config para .exe standalone
- Script de build que firma digitalmente (opcional)
- Auto-updater opcional (GitHub Releases)

**Criterio de aceptación**:
- Latencia medible: hotkey release → texto inyectado <500ms p50 para 5s de audio
- `dictado.exe` funciona en máquina limpia sin Python instalado
- Tamaño razonable (modelos se descargan aparte, no van en el .exe)

---

## 9. Prompts para Claude Code

Cada prompt está diseñado para iniciar una sesión con Claude Code. Pega el prompt en una sesión limpia después de haber puesto `PLAN.md` en el directorio raíz.

### Prompt Fase 0

```
Estoy iniciando el proyecto VibeDictate — una app de dictado por voz para Windows.
Lee PLAN.md completo para entender el contexto.

Tu tarea es implementar la Fase 0 (Bootstrap):
- Crear pyproject.toml con uv y las dependencias de la sección 5
- Crear estructura de carpetas según sección 4
- Implementar app/config.py usando Pydantic v2 para validar el TOML
- Implementar app/utils/logging.py con loguru
- Crear config.default.toml con el contenido de la sección 7
- app/main.py debe cargar config, inicializar logging, imprimir versión y ruta de config, y salir

No implementes ninguna otra fase. Criterio de aceptación en sección 8, Fase 0.

Cuando termines, dame las instrucciones para probarlo (comandos uv).
```

### Prompt Fase 1

```
Continuamos VibeDictate. La Fase 0 está completa (puedes verificar que config.py y logging funcionan).
Lee PLAN.md, especialmente sección 8 Fase 1 y arquitectura general.

Implementa la Fase 1 (Captura de audio con hotkey):
- app/events.py con un EventBus minimalista (subscribe/publish, thread-safe)
- app/core/hotkey.py con pynput en modo toggle, lee combo de config
- app/core/recorder.py con sounddevice, acumula en buffer numpy, mono 16kHz
- Modifica app/main.py para conectar hotkey → recorder → guardar WAV en ./recordings/
- Usa scipy.io.wavfile o soundfile para guardar WAV

Convenciones:
- Todos los componentes se comunican vía EventBus, NO se llaman directamente
- Eventos: RECORDING_STARTED, RECORDING_STOPPED con payload {audio: np.ndarray, sample_rate: int, duration: float}
- Logs en loguru para cada evento importante

Criterio de aceptación en PLAN.md Fase 1. Dame los pasos para probarlo.
```

### Prompt Fase 2

```
Continuamos VibeDictate. Fases 0 y 1 completas.
Lee PLAN.md, especialmente secciones 3 (arquitectura), 6 (modelos), 8 Fase 2.

Implementa la Fase 2 (STT con faster-whisper):
- app/models.py con Transcript, Segment (dataclasses)
- app/providers/stt/base.py con el Protocol STTProvider
- app/providers/stt/registry.py con register_stt y create_stt
- app/providers/stt/__init__.py que importe todos los providers (auto-registro)
- app/providers/stt/faster_whisper.py con implementación completa:
  - __init__: carga modelo faster_whisper.WhisperModel con device, compute_type
  - warmup: transcribe 1 segundo de silencio
  - transcribe(audio, language, hints): devuelve Transcript
  - unload: libera modelo
- app/core/pipeline.py: escucha RECORDING_STOPPED, llama STT, emite TRANSCRIPT_READY, imprime texto

Por ahora idioma fijado a "es" (la histéresis es Fase 4).
Hints se pasan como initial_prompt a Whisper.

Criterio en PLAN.md Fase 2.
```

### Prompt Fase 3

```
Continuamos VibeDictate. Fases 0-2 completas. Ya transcribimos a consola.
Lee PLAN.md, Fase 3.

Implementa la Fase 3 (Inyección de texto + UI mínima):
- app/core/injector.py:
  - Implementación con SendInput vía ctypes, soporte Unicode (KEYEVENTF_UNICODE)
  - Fallback a clipboard + Ctrl+V si falla
  - Configurable vía config.toml [injection].method
- app/ui/overlay.py:
  - PyQt6 QWidget frameless, always-on-top, translucido
  - Círculo rojo que pulsa mientras graba
  - Se muestra en RECORDING_STARTED, se oculta en TRANSCRIPT_READY
  - Posición configurable (bottom-center default)
- app/ui/tray.py:
  - QSystemTrayIcon con menú: "Pausa", "Configuración", "Salir"
  - Usa asset assets/icon.png (puedes crear un PNG simple por ahora)
- Pipeline: TRANSCRIPT_READY → Injector.inject(text)
- app/main.py: arrancar QApplication, tray, overlay, hookear todos los servicios

IMPORTANTE: pynput y PyQt6 pueden tener conflictos de event loop. 
La solución estándar es ejecutar pynput en thread propio y hacer signal-emit a Qt.

Criterio: probar en Notepad, Chrome y VSCode.
```

### Prompt Fase 4

```
Continuamos VibeDictate. Fases 0-3 completas (MVP funciona).
Lee PLAN.md, Fase 4.

Implementa la Fase 4 (Multiidioma con histéresis):
- app/core/language.py con clase LanguageHysteresis:
  - Estado: last_language, last_confidence
  - Método choose_hint() → devuelve idioma a usar como hint
  - Método update(detected_language, confidence) → actualiza estado con histéresis
  - Persistencia a disco (JSON en user data dir)
- Modificar FasterWhisperSTT:
  - Usa la detección nativa de Whisper pero con el hint
  - Devuelve language y language_confidence en Transcript
- Pipeline consulta LanguageHysteresis antes de transcribir y la actualiza después
- Hotkeys adicionales: force_language_es, force_language_en (próxima frase solo)
- Overlay muestra idioma activo como texto pequeño ("ES" / "EN")

Matemática de histéresis (sección 7 config):
- Si detected == last_language: aceptar
- Si detected != last_language y confidence > threshold + switch_penalty: cambiar
- Si no: mantener last_language

Criterio en PLAN.md Fase 4.
```

### Prompt Fase 5

```
Continuamos VibeDictate. Fases 0-4 completas.
Lee PLAN.md, Fase 5.

Implementa la Fase 5 (Providers + perfiles + hot-swap):
1. Mover toda la lógica de STT a providers/stt/faster_whisper.py (ya lo está)
2. Crear providers/llm/ (base.py, registry.py, ollama.py como Fase 6 usará)
   - Por ahora solo la infraestructura, ollama.py puede tener solo skeleton
3. Añadir providers STT adicionales (opcionales, comentados si no hay API key):
   - groq.py (usa librería groq, requiere GROQ_API_KEY)
   - openai.py (usa openai, requiere OPENAI_API_KEY)
4. app/models.py: añadir Profile dataclass
5. app/core/pipeline.py refactor:
   - Mantiene referencia al provider actual
   - Método switch_profile(profile_name) que hace unload + create + warmup
6. Config: los perfiles ya están definidos en sección 7 del PLAN
7. Hotkeys para ciclar perfiles (alt+shift+1/2/3...)
8. Tray menu: submenú "Perfil" con lista de perfiles + marca en el activo

Verifica con nvidia-smi que la VRAM se libera al cambiar de perfil.
Criterio: añadir un provider nuevo NO debe requerir cambios fuera de providers/stt/.
```

### Prompt Fase 6

```
Continuamos VibeDictate. Fases 0-5 completas (arquitectura modular lista).
Lee PLAN.md, Fase 6 (especialmente las notas sobre reemplazo de texto).

Implementa la Fase 6 (LLM post-procesado):
- app/providers/llm/ollama.py completo:
  - Cliente HTTP a http://localhost:11434/api/chat
  - Streaming opcional (para futura fase 9)
  - Warmup con prompt dummy
- app/learning/prompts.py:
  - Define SYSTEM_PROMPTS dict: {"default": "...", "casual": "...", "technical": "...", "code": "..."}
  - Los prompts son bilingües (el LLM debe responder en el mismo idioma del input)
  - Muy claros: "Devuelve SOLO el texto pulido, sin explicaciones, sin comillas"
- app/core/pipeline.py:
  - Después de inyectar texto crudo, lanza polish en thread
  - Cuando el polish termina, usa el enfoque SIMPLE (opción 3 de las notas):
    - Muestra el polish en el overlay con un botón "aplicar" (Enter) o "descartar" (Esc)
    - Si el usuario acepta, el injector hace Ctrl+Z + inyecta polish
  - Configurable: auto-apply (arriesgado, experimental) vs manual (default)
- Detección de app activa con pywin32 (GetForegroundWindow + GetWindowText)
- Map de app → estilo en config (default: chrome→casual, code→code, slack→casual)
- Hotkey toggle_polish

Criterio PLAN.md Fase 6.
```

### Prompt Fase 7

```
Continuamos VibeDictate. Fases 0-6 completas.
Lee PLAN.md, Fase 7.

Implementa la Fase 7 (UI de configuración completa):
- app/ui/config_window.py: QMainWindow con QTabWidget
  - Pestañas según PLAN: General, Hotkeys, Perfiles, Modelos, Diccionario, Historial
- app/ui/widgets/hotkey_input.py: QLineEdit que captura combo de teclas
- app/ui/widgets/profile_editor.py: QFormLayout con todos los parámetros
- Pestaña Modelos:
  - Lista modelos de Ollama (GET /api/tags)
  - Botón "Descargar" con QProgressBar (POST /api/pull streaming)
  - Para Whisper, muestra modelos ya descargados en ~/.cache/huggingface/
- Pestaña Diccionario: QListView + add/edit/delete
- Pestaña Historial: QTableView con paginación, últimas 200 sesiones
- Guardado atómico del TOML (temp file + os.replace)
- Hot-reload: la app detecta cambios en config.toml (watchdog) y aplica lo que puede

Mantén la UI limpia, usa qtawesome para iconos, no hace falta que sea preciosa pero sí funcional.
```

### Prompt Fase 8

```
Continuamos VibeDictate. Fases 0-7 completas (app usable completa).
Lee PLAN.md, Fase 8 (tres sub-fases).

Implementa la Fase 8 (Aprendizaje). Hazlo en orden 8.1 → 8.2 → 8.3, 
no pases a la siguiente hasta que la anterior funcione y yo lo apruebe.

8.1 — Diccionario personalizado:
- app/storage/db.py: conexión SQLite en user data dir, migrations simples
- app/storage/vocabulary.py: CRUD de términos
- app/learning/hints.py: build_hint(language) → string con términos relevantes
- Integrar en pipeline: hints pasan a STTProvider.transcribe()
- UI ya existe (Fase 7), conectar a DB

8.2 — Correcciones:
- app/storage/corrections.py: guarda (session_id, raw, polish, final_edit)
- Detectar "final_edit": después de inyectar, trackear cambios en el área de texto activa durante N segundos
  (esto es complicado; alternativa: botón en overlay "corregí esto" que captura el portapapeles)
- Empezar con la alternativa manual, expandir luego

8.3 — RAG:
- app/learning/rag.py: 
  - Embeddings con sentence-transformers/multilingual-MiniLM
  - Vector store: chromadb o FAISS local
  - Query: top-3 correcciones más similares al raw actual
- Integrar en PolishContext.examples

Criterio: después de 50 dictados con correcciones, ver si el polish converge a mi estilo.
```

### Prompt Fase 9

```
Continuamos VibeDictate. Fases 0-8 completas.
Lee PLAN.md, Fase 9.

Implementa la Fase 9 (Optimización + empaquetado):
- Añade instrumentación de latencia: decorador @timed que loggea tiempos
- Reporta en log al final de cada sesión: total, record, stt, polish, inject
- Warmup paralelo al arrancar la app (thread pool)
- build/build.py: script que ejecuta PyInstaller
  - --onefile, --windowed, icon, data de config.default.toml
  - Excluir modelos (se descargan en runtime)
- Documenta en README cómo hacer build
- Opcional: GitHub Actions para build en push a tag

Criterio: dictado.exe standalone, <100MB (sin modelos).
```

---

## 10. Sistema de aprendizaje — detalle

Se implementa en Fase 8, pero el diseño es importante tenerlo claro desde antes para no acumular deuda.

### 10.1 Flujo de datos del aprendizaje

```
[Dictado]                                   [Aprendizaje]
   │                                              │
   ├─ STT con hints desde vocabulary ────────────┤
   │                                              │
   ├─ Polish con examples desde RAG ─────────────┤
   │                                              │
   ├─ Usuario edita el texto ────────────────────┤
   │                                              │
   ├─ Session guardada en history ───────────────┤
   │                                              │
   │                                              ▼
   │                                    ┌─────────────────┐
   │                                    │ Vocabulary      │
   │                                    │ (manual + auto) │
   │                                    └─────────────────┘
   │                                    ┌─────────────────┐
   │                                    │ Corrections     │
   │                                    │ (raw → final)   │
   │                                    └─────────────────┘
   │                                    ┌─────────────────┐
   │                                    │ Embeddings idx  │
   │                                    │ (para RAG)      │
   └────────────────────────────────────┴─────────────────┘
```

### 10.2 Prompts del LLM (ejemplo)

```python
# app/learning/prompts.py
POLISH_SYSTEM = """Eres un editor de dictado por voz. Tu tarea es limpiar la transcripción cruda:
- Añade puntuación y capitalización correctas
- Elimina muletillas ("eh", "pues", "o sea")
- Corrige palabras claramente mal transcritas dado el contexto
- Mantén el significado exacto — NO añadas ni quites información
- Responde en el MISMO idioma que el input
- Devuelve SOLO el texto final, sin explicaciones, sin comillas, sin markdown

Estilo: {style}
Aplicación activa: {app_name}
"""

POLISH_USER_TEMPLATE = """{vocabulary_hint}

{examples_block}

Transcripción cruda:
{raw_text}

Texto pulido:"""
```

### 10.3 Activación / desactivación

El aprendizaje es **opt-in por defecto para correcciones**. El usuario debe poder:
- Ver qué se ha guardado
- Borrar entradas
- Desactivar el RAG si el polish empieza a drift raro
- Exportar/importar su dataset (portabilidad)

---

## 11. Rendimiento — objetivos y medición

### Presupuesto de latencia (objetivo p50 en 5070 Ti)

| Etapa | Objetivo | Medición |
|-------|----------|----------|
| Hotkey release → STT start | <20ms | timestamps en events |
| STT (5s audio, Whisper Turbo) | <400ms | `time.perf_counter()` alrededor de transcribe |
| STT → Inject start | <30ms | tiempo de pipeline |
| Inject (raw, 100 chars) | <50ms | tiempo en SendInput loop |
| **Total release → texto visible** | **<500ms** | e2e |
| Polish LLM (Qwen 7B, 200 tokens) | 1-2s | separado, no bloquea |

### Cómo medir

- Decorador `@timed(event="stt")` que publica eventos `TIMING` al EventBus
- Al final de cada sesión, resumen en log: `[timing] record=3.2s stt=0.38s inject=0.04s polish=1.4s`
- Opción "modo debug" en config que guarda CSV con todos los timings para análisis

### Qué NO optimizar prematuramente

- No hacer streaming STT hasta Fase 9 (complica mucho el pipeline)
- No intentar inyectar palabra por palabra mientras transcribe (fragil, mala UX)
- No optimizar el polish antes de tener el MVP — es async

---

## 12. Validación manual por fase

Lista de comprobaciones manuales (no hay tests automatizados exhaustivos — VibeCoding).

**Fase 0**: `uv run python -m app.main` no crashea, imprime versión.

**Fase 1**: Hotkey funciona, WAV guardado se reproduce bien.

**Fase 2**: 
- Transcripción es legible
- Segunda transcripción es más rápida que la primera (modelo cacheado)
- Probar frase larga (30s) y corta (3s)

**Fase 3**: 
- Inyección funciona en: Notepad, Chrome (caja de búsqueda), VSCode, Word, Slack
- Caracteres especiales (ñ, acentos, ¿, ¡) se inyectan correctamente
- Overlay aparece y desaparece correctamente
- Salir desde tray cierra todo

**Fase 4**: 
- 10 dictados alternando idiomas → idioma detectado correctamente en >90%
- Force hotkey funciona aunque estés hablando en el otro idioma

**Fase 5**: 
- `nvidia-smi` antes/después de switch confirma liberación de VRAM
- Añadir un provider ficticio nuevo en 10 minutos

**Fase 6**: 
- Comparar raw vs polish en 20 frases reales
- Medir cuánto añade polish a la latencia
- Probar estilos: mismo texto, 4 estilos → 4 outputs distintos

**Fase 7**: 
- Editar cada campo de config desde UI y verificar que persiste
- Cambiar hotkey en vivo y verificar que la vieja deja de funcionar

**Fase 8**:
- Añadir 20 términos al vocabulario → mejora en transcripciones con esos términos
- Hacer 30 correcciones → RAG sugiere ejemplos sensatos
- Desactivar RAG → polish vuelve al baseline

**Fase 9**:
- Medir latencia p50, p95, p99 sobre 50 dictados
- .exe en máquina limpia

---

## 13. Riesgos y planes B

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| SendInput no funciona en alguna app (UAC elevated, juegos) | Media | Medio | Fallback a clipboard |
| pynput y PyQt6 pelean por eventos | Media | Alto | Arquitectura con thread separado + Qt signals |
| Reemplazar texto del polish es frágil | Alta | Medio | Modo manual con confirmación (preferible sobre auto-replace) |
| Latencia STT > 500ms en audios largos | Baja | Medio | Chunking + streaming STT (fase 9) |
| Windows Defender flaggea el .exe | Media | Bajo | Firma digital, subir hash a VirusTotal |
| Detección de idioma falla en frases cortas | Media | Medio | Histéresis (fase 4) mitiga |
| Usuario pierde el modelo descargado | Baja | Bajo | UI con botón re-download |
| Polish cambia el significado | Media | Alto | Prompt estricto "NO añadas información", tests manuales |

---

## 14. Convenciones de código

Para que Claude genere código consistente:

- **Naming**: `snake_case` funciones/vars, `PascalCase` clases, `UPPER_CASE` constantes
- **Imports**: absolutos desde `app.` (no relativos)
- **Dataclasses**: siempre con `@dataclass(frozen=True)` si son inmutables, sino sin frozen
- **Errores**: raise exceptions específicas, no `Exception` genéricas
- **Docstrings**: solo en APIs públicas (providers, core components), una línea salvo que sea complejo
- **Logging**: `from loguru import logger`, usar `logger.info/warning/error`
- **Threads**: preferir `threading.Thread` para IO, `concurrent.futures` para pools
- **Rutas**: siempre `pathlib.Path`, nunca strings concatenados
- **Config access**: siempre vía `Config` object pydantic, nunca dict crudo

---

## 15. Glosario

- **STT** (Speech-to-Text): transcripción de audio a texto.
- **LLM**: Large Language Model, aquí usado para "pulir" transcripciones.
- **VAD** (Voice Activity Detection): detecta cuándo hay voz vs silencio.
- **Histéresis**: resistencia al cambio basada en historia; aquí aplicada a la detección de idioma.
- **Push-to-talk**: mantener tecla para grabar.
- **Toggle**: pulsar para empezar, pulsar para parar.
- **Two-stage display**: mostrar texto crudo rápido + reemplazar con pulido después.
- **Hot-swap**: cambiar un componente (modelo) sin reiniciar la app.
- **RAG** (Retrieval-Augmented Generation): aumentar un prompt con ejemplos recuperados de una base.
- **Provider**: implementación concreta de un STT o LLM backend.
- **Perfil**: combinación de providers + parámetros, cambiable en caliente.
- **VibeCoding**: estilo de desarrollo donde el humano describe y la IA implementa sin revisión detallada del código.

---

## 16. Orden sugerido de trabajo

1. Lee este PLAN completo
2. Ejecuta el **Prompt Fase 0** en una sesión limpia de Claude Code
3. Valida el criterio de aceptación
4. **Sesión nueva** para cada fase siguiente (mantiene contexto limpio)
5. Al terminar cada fase, haz commit y **anota en un CHANGELOG.md** qué decisiones se tomaron que no estaban en el plan
6. Si una fase descubre algo que invalida el plan → **edita PLAN.md antes de seguir**, no acumules deriva

El plan es un documento vivo. Revísalo al menos después de cada fase para que no se quede obsoleto respecto al código real.

---

**Versión del plan**: 0.1
**Fecha**: 2026-04-22
