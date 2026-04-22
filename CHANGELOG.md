# CHANGELOG

## 2026-04-22 - Fase 0

- Bootstrap inicial del proyecto `dictado`.
- Entorno creado con `uv` sobre Python 3.11.
- Estructura base de paquetes creada en `app/`.
- Configuracion inicial con `config.default.toml` y generacion automatica de `config.toml`.
- Logging base con `loguru`.
- Validado `uv run python -m app.main`.

## 2026-04-22 - Fase 1 (en curso)

- Captura de hotkey global y grabacion de audio en WAV.
- Cambio de interaccion a `hold-to-talk`: graba mientras la combinacion esta pulsada.
- Config por defecto actualizada a `ctrl+win` con soporte para combinaciones solo de modificadores.

## 2026-04-22 - Fase 2 (en curso)

- Integracion inicial de `faster-whisper` con provider modular y registry.
- Pipeline de transcripcion al soltar la hotkey.
- Impresion de transcript en consola mediante evento `TRANSCRIPT_READY`.
- Modo `local_files_only` para evitar descargas en runtime.
- Warmup asincrono configurable al arrancar.

## 2026-04-22 - Fase 3 (en curso)

- Inyeccion de texto via `SendInput` con fallback a portapapeles.
- Overlay minimo en PyQt6 para indicar grabacion.
- Tray icon con pausa, configuracion y salida limpia.
