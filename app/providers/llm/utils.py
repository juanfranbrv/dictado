from __future__ import annotations

import re
import unicodedata

_LEAKED_PREFIXES = (
    "app:",
    "aplicacion:",
    "idioma:",
    "texto:",
    "texto pulido:",
    "correccion:",
    "correccion final:",
    "salida:",
)

_COMMENTARY_STARTERS = (
    "aqui tienes",
    "he ",
    "lo he ",
    "el texto ",
    "el usuario ",
    "la correccion ",
    "esta correccion ",
    "nota:",
    "comentario:",
    "explicacion:",
)


def build_polish_input(text: str, language: str) -> str:
    language_name = {"es": "espanol", "en": "english"}.get(language.lower(), language)
    return (
        f"Corrige este dictado en {language_name}. "
        "Devuelve solo el texto final, sin etiquetas, prologo, notas ni explicaciones.\n\n"
        f"{text.strip()}"
    )


def sanitize_polish_output(text: str, fallback: str, language: str | None = None) -> str:
    cleaned = text.strip()
    if not cleaned:
        return _stabilize_output(fallback, language)

    lines = cleaned.splitlines()
    while lines and _looks_like_metadata(lines[0]):
        lines.pop(0)

    cleaned = "\n".join(lines).strip()
    cleaned = _strip_trailing_commentary(cleaned)
    return _stabilize_output(cleaned or fallback, language)


def _stabilize_output(text: str, language: str | None) -> str:
    if (language or "").lower() == "es":
        return _stabilize_spanish_questions(text)
    return text


def _looks_like_metadata(line: str) -> bool:
    normalized = _normalize(line)
    if not normalized:
        return True
    return any(normalized.startswith(prefix) for prefix in _LEAKED_PREFIXES)


def _strip_trailing_commentary(text: str) -> str:
    paragraphs = re.split(r"\n\s*\n", text)
    if len(paragraphs) < 2:
        return text.strip()

    kept: list[str] = []
    for index, paragraph in enumerate(paragraphs):
        if index > 0 and _looks_like_commentary(paragraph):
            break
        kept.append(paragraph.strip())

    return "\n\n".join(kept).strip()


def _looks_like_commentary(paragraph: str) -> bool:
    normalized = _normalize(paragraph)
    if not normalized:
        return True
    return any(normalized.startswith(starter) for starter in _COMMENTARY_STARTERS)


def _normalize(text: str) -> str:
    without_accents = unicodedata.normalize("NFKD", text)
    ascii_text = without_accents.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_text.strip().lower().split())


def _stabilize_spanish_questions(text: str) -> str:
    lines = text.splitlines()
    stabilized = [_stabilize_spanish_question_line(line) for line in lines]
    return "\n".join(stabilized).strip()


def _stabilize_spanish_question_line(line: str) -> str:
    stripped = line.strip()
    if not stripped:
        return line

    leading = line[: len(line) - len(line.lstrip())]
    trailing = line[len(line.rstrip()) :]

    if "?" in stripped and "¿" not in stripped:
        return f"{leading}¿{stripped}{trailing}"

    if _looks_like_spanish_question(stripped):
        core = stripped.rstrip(" .")
        if core.endswith("?"):
            core = core[:-1].rstrip()
        if not core.startswith("¿"):
            core = f"¿{core}"
        return f"{leading}{core}?{trailing}"

    return line


def _looks_like_spanish_question(text: str) -> bool:
    normalized = _normalize(text.lstrip("¿"))
    if not normalized:
        return False

    starters = (
        "que",
        "como",
        "cuando",
        "donde",
        "por que",
        "quien",
        "cuanto",
        "cual",
        "puedes",
        "podrias",
        "debo",
        "tengo que",
        "me puedes",
        "me podrias",
    )
    return any(normalized == starter or normalized.startswith(f"{starter} ") for starter in starters)
