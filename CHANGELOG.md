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

## 2026-04-22 - Fase 4 (en curso)

- Histéresis de idioma con persistencia a disco y política `es-first`.
- Hotkeys para forzar la siguiente frase en `es` o `en`.
- Indicador del idioma activo en el overlay.

## 2026-04-22 - Fase 5 (en curso)

- Configuración con perfiles y perfil activo.
- Pipeline con hot-swap de provider STT por perfil.
- Infraestructura LLM base/registry y skeleton de Ollama.
- Submenú de perfiles en la bandeja del sistema.
- Añadido perfil `fast` local usando el mismo modelo con `beam_size` reducido.

## 2026-04-22 - Fase 6 (cerrada)

- Provider Ollama real con prompts por estilo.
- Polish asíncrono en background.
- Propuesta manual de polish en overlay con aceptar/descartar.
- Modelo por defecto de Ollama ajustado a `qwen3.5:9b` según los modelos disponibles en la máquina.
- Cambio a Gemini como provider principal de polish con Groq como fallback.
- Prompts y timeouts recortados para priorizar latencia frente a edición agresiva.
- Ajuste de prompts para permitir estructura ligera y cambio de orden a Groq primero, Gemini después.
- Groq queda como provider principal de polish y Gemini como fallback en `config.toml`.
- El prompt de usuario se mantiene mínimo: instrucción breve + dictado, sin metadatos de app/idioma/texto.
- Añadido saneado defensivo de salida LLM para eliminar cabeceras filtradas (`Texto pulido:`, `Corrección:`) y comentarios posteriores que no sean dictado.
- Añadidos tests unitarios para fijar el contrato de salida: devolver solo texto pulido, manteniendo dictados multipárrafo reales.

## 2026-04-22 - Fase 7 (en curso)

- Ventana de configuracion reemplazada por UI con pestañas: General, Hotkeys, Perfiles, Modelos, Diccionario e Historial.
- Añadido guardado atomico de `config.toml` desde la UI.
- Añadido hot-reload parcial de configuracion: perfiles, perfil activo, overlay e inyeccion.
- El pulido se configura por perfil con `profiles.<nombre>.polish_enabled`; se elimina el interruptor global por ambiguo.
- El tray mantiene perfiles y configuracion, pero ya no tiene toggle global de pulido.
- Los perfiles controlan velocidad/modelos y si tienen pulido activo.
- El editor de perfiles deja de mostrar JSON crudo y usa campos de seleccion para STT, LLM, modelos, timeouts y claves.
- La ventana de configuracion añade texto explicativo en General y ayuda contextual/tooltips en Perfiles para opciones como metodo de inyeccion, beam size y timeout.

## 2026-04-23 - Fase 9 (en curso)

- Añadida instrumentacion de tiempos por sesion (`record`, `stt`, `polish`, `inject`) con resumen en logs al finalizar la inyeccion.
- Warmup paralelo se mantiene al arrancar para STT y LLM activos.
- Añadido `build/build.py` para generar `dictado.exe` con PyInstaller.
- README ampliado con la instruccion minima de build para Windows.
- Ollama reutiliza el mismo prompt minimo y saneado de salida que Groq/Gemini.
- El overlay de grabacion se reduce a un punto rojo pulsante sin texto ni marco.
- Eliminadas de la ventana de configuracion las hotkeys de aplicar/descartar pulido porque el pulido se inyecta directamente.
- Eliminada la opcion `inject_raw_first` de la UI y del guardado TOML; el flujo activo es pulido directo o crudo como fallback.
- Eliminado por completo el modo tarjeta del overlay; durante grabacion solo queda una ventana transparente de 44x44 con punto rojo pulsante y sin sombra.
- Diccionario e historial quedan como pestañas placeholder hasta Fase 8; el diseño previsto es usar hints de STT para no aumentar la latencia de insercion.
- Añadido autotuning de primer arranque según hardware para recomendar y fijar un perfil inicial (`default`, `fast` o `low-spec`) una sola vez.
- Añadido perfil `low-spec` para CPU/int8/sin pulido en máquinas modestas.
- El build incluye ya un script de instalador con Inno Setup y dos opciones visibles para el usuario, ambas desactivadas por defecto: crear icono en escritorio e iniciar con Windows.

## 2026-04-22 - Fase 8.1 (en curso)

- Añadida base SQLite local en `data/dictado.sqlite3`.
- Añadido CRUD de diccionario personalizado con termino, idioma, peso y estado activo.
- La pestaña Diccionario ya permite añadir, editar, borrar y recargar terminos.
- El pipeline pasa los terminos activos como `initial_prompt`/hints a Whisper antes de transcribir.
- Los hints se filtran por idioma (`auto`, `es`, `en`) y se limitan para no penalizar la latencia.
- El icono de bandeja usa `assets/mic-vocal.png` y el clic izquierdo abre Configuracion.
