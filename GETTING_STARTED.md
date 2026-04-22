# VibeDictate — Cómo empezar

Guía breve para ponerte a construir. El documento autoritativo es [PLAN.md](PLAN.md).

## Requisitos previos

Instala en tu máquina (una sola vez):

1. **Python 3.11+** (https://www.python.org)
2. **uv** — gestor de paquetes moderno:
   ```powershell
   winget install --id=astral-sh.uv -e
   ```
3. **Ollama** (para el polish local) — https://ollama.com
   Después:
   ```powershell
   ollama pull qwen2.5:7b
   ```
4. **NVIDIA CUDA Toolkit 12.x** (para faster-whisper en GPU)
5. **Claude Code** — https://docs.claude.com/en/docs/claude-code

## Flujo de trabajo VibeCoding

Para cada fase del PLAN (0 → 9):

1. Abre una **sesión limpia** de Claude Code en la carpeta `F:\_PROYECTOS\dictado`
2. Copia el **Prompt Fase N** de [PLAN.md §9](PLAN.md#9-prompts-para-claude-code) y pégalo
3. Espera a que Claude termine
4. Ejecuta el **criterio de aceptación** de [PLAN.md §8](PLAN.md#8-fases-de-desarrollo)
5. Si funciona: commit + pasa a la siguiente fase
6. Si no funciona: describe el problema en la misma sesión a Claude para que itere
7. Si descubres algo que invalida el plan: **edita PLAN.md** antes de continuar

### Regla de oro

> Sesión nueva por fase. No dejes que el contexto acumule decisiones de 3 fases atrás — Claude se despista.

## Primer paso concreto

```powershell
cd F:\_PROYECTOS\dictado
# Abre Claude Code aquí y pega el "Prompt Fase 0" de PLAN.md §9
```

## Checklist de progreso

- [ ] Fase 0 — Bootstrap
- [ ] Fase 1 — Captura de audio
- [ ] Fase 2 — STT básico
- [ ] Fase 3 — Inyección de texto (MVP usable)
- [ ] Fase 4 — Multiidioma con histéresis
- [ ] Fase 5 — Providers + perfiles
- [ ] Fase 6 — LLM post-procesado
- [ ] Fase 7 — UI de configuración
- [ ] Fase 8 — Aprendizaje
- [ ] Fase 9 — Optimización + empaquetado

## Si algo va mal

Situaciones comunes y dónde mirar en el PLAN:

| Problema | Sección |
|----------|---------|
| SendInput no funciona en una app | §13 Riesgos |
| Latencia alta | §11 Rendimiento |
| Cómo añadir un modelo nuevo | §3.3-3.4 Arquitectura |
| Qué validar al terminar una fase | §12 Validación |
| Significado de un término | §15 Glosario |

## CHANGELOG

Crea `CHANGELOG.md` y apunta cada fase completada con fecha y decisiones fuera del plan. Mantiene la memoria histórica cuando el proyecto crezca.
