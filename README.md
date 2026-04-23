# dictado

Aplicación de dictado por voz para Windows, local-first, pensada para escribir en cualquier campo de texto con una hotkey global.

El flujo es simple:

1. Mantienes pulsada la hotkey.
2. La app graba tu voz.
3. Transcribe con `faster-whisper`.
4. Opcionalmente pule el texto con un LLM.
5. Inserta el resultado en la ventana activa.

Ahora mismo el foco real del proyecto es:

- Windows
- uso personal y pruebas tempranas
- perfiles para máquinas potentes y modestas
- STT local con Whisper
- pulido opcional con proveedores remotos

## Estado

`dictado` ya es usable, pero sigue siendo una versión temprana.

Qué hace bien:

- dictado con hotkey global
- perfiles `default`, `fast` y `low-spec`
- detección inicial de hardware
- descarga guiada del modelo Whisper que falte
- configuración desde interfaz
- icono de bandeja y overlay de grabación
- instalador para Windows

Qué sigue verde:

- la UX del primer arranque todavía necesita más pulido
- el soporte fuera de Windows no existe
- la telemetría y los tests aún son básicos
- la parte de LLM depende de claves/API y red

## Características

- STT local con `faster-whisper`
- perfiles de rendimiento según hardware
- pulido opcional por perfil
- providers LLM: Groq, Gemini y Ollama
- inyección por `SendInput` con fallback a portapapeles
- selección de micrófono
- diccionario de términos para ayudar al reconocimiento
- configuración persistente en `%LocalAppData%\dictado`
- build empaquetada con PyInstaller
- instalador `.exe` con Inno Setup

## Requisitos de uso

Para usar el instalador no hace falta tener Python instalado.

Sí necesitas:

- Windows
- un micrófono funcional
- conexión a internet la primera vez que haya que descargar un modelo Whisper
- conexión a internet y API keys válidas si quieres usar pulido con Groq o Gemini

Notas de hardware:

- En una máquina con GPU NVIDIA decente, el perfil `default` usa `large-v3-turbo`.
- En una máquina modesta, la app puede recomendar `low-spec`, que usa `small` + CPU + `int8`.
- Si no hay CUDA, la app puede seguir funcionando, solo que más lenta.

## Instalación

La forma normal de probarla es con el instalador:

1. Descarga `dictado-setup.exe` desde la sección de releases o desde una build local.
2. Ejecuta el instalador.
3. Opcionalmente marca:
   - `Crear icono en el escritorio`
   - `Iniciar dictado al arrancar Windows`
4. Al terminar, arranca `dictado`.
5. En el primer uso, si falta el modelo Whisper del perfil activo, la app te pedirá descargarlo.

La hotkey por defecto es `Ctrl + Win`.

La app se queda en la bandeja del sistema.

## Primer arranque

En el primer arranque la app intenta elegir un perfil razonable según la máquina.

Ejemplos:

- máquina potente con NVIDIA: normalmente `default`
- máquina media: puede quedarse en `fast`
- máquina sin GPU válida: `low-spec`

Si el modelo Whisper necesario no está descargado todavía:

- la app lo detecta
- muestra un diálogo de descarga
- y bloquea el dictado hasta que termine

Los modelos Whisper se guardan en:

`%LocalAppData%\dictado\models\whisper`

La configuración y datos del usuario se guardan en:

- `%LocalAppData%\dictado\config.toml`
- `%LocalAppData%\dictado\logs\dictado.log`
- `%LocalAppData%\dictado\recordings\`
- `%LocalAppData%\dictado\data\`

## Perfiles

Perfiles incluidos:

- `default`
  - pensado para calidad alta
  - usa `large-v3-turbo`
  - suele activar pulido

- `fast`
  - orientado a menos latencia
  - usa configuración más agresiva de STT
  - por defecto sin pulido

- `low-spec`
  - pensado para CPU o equipos modestos
  - usa `small`
  - `cpu` + `int8`
  - sin pulido

## Pulido de texto

El pulido es opcional y depende del perfil.

Idea general:

- Whisper hace la transcripción base
- el LLM puede hacer una microcorrección del texto
- si no hay nada que corregir, se acepta el texto tal cual
- el texto pulido sale directo, sin pantalla de aprobación

Providers soportados:

- Groq
- Gemini
- Ollama

Si no configuras claves o el proveedor falla, la app puede seguir funcionando solo con STT local.

## Configuración

La ventana de configuración incluye:

- `General`
- `Hotkeys`
- `Perfiles`
- `Modelos`
- `Diccionario`
- `Historial`
- `Acerca de`

El objetivo de la UI es que lo importante se pueda cambiar sin tocar JSON ni editar a mano el TOML.

## Desarrollo

Requisitos para desarrollar:

- Python 3.11+
- `uv`
- Windows

Instalación del entorno:

```powershell
uv sync
```

Ejecutar la app en local:

```powershell
uv run python -m app.main
```

## Build Windows

Generar el ejecutable:

```powershell
uv run python build/build.py
```

Salida:

- `dist/dictado.exe`

Generar el instalador:

```powershell
python build/build_installer.py
```

Salida:

- `dist/dictado-setup.exe`

Notas:

- hace falta tener Inno Setup instalado para generar el instalador
- el script del instalador limpia esta máquina al terminar para dejarla como una instalación nueva de pruebas

## Estructura

Estructura principal del repo:

- [app](app)
- [assets](assets)
- [build](build)
- [tests](tests)
- [config.default.toml](config.default.toml)
- [PLAN.md](PLAN.md)
- [CHANGELOG.md](CHANGELOG.md)

## Roadmap

El plan original del proyecto está en [PLAN.md](PLAN.md).

Las decisiones reales que se han ido tomando durante la implementación están en [CHANGELOG.md](CHANGELOG.md).

## Problemas conocidos

- algunas aplicaciones elevadas pueden resistirse a `SendInput`
- el pulido remoto requiere claves válidas y red
- la experiencia de primer arranque todavía necesita más pruebas en máquinas ajenas
- la calidad final depende mucho del micrófono y del perfil elegido

## Licencia

Pendiente de definir.

Si vas a publicarlo como repo abierto, conviene añadir un fichero `LICENSE` antes de difundirlo.

## Autor

Juan Francisco Briva Casas

X / Twitter:

- [https://x.com/juanfranbrv](https://x.com/juanfranbrv)
