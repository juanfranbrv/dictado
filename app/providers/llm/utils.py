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
    "texto final:",
    "respuesta final:",
    "final:",
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
    "razonamiento:",
    "analisis:",
    "pensamiento:",
    "reasoning:",
    "analysis:",
)


def build_polish_input(text: str, language: str) -> str:
    language_name = {"es": "espanol", "en": "english"}.get(language.lower(), language)
    return (
        f"Corrige este dictado en {language_name}. "
        "Devuelve solo el texto final, sin etiquetas, prologo, notas, razonamiento ni explicaciones. "
        f"<dictado>{text.strip()}</dictado>"
    )


def sanitize_polish_output(text: str, fallback: str, language: str | None = None) -> str:
    cleaned = text.strip()
    if not cleaned:
        return _stabilize_output(fallback, language)

    cleaned = _strip_thinking_blocks(cleaned)
    extracted = _extract_final_section(cleaned)
    if extracted:
        cleaned = extracted
    else:
        cleaned = _strip_final_tag_fragments(cleaned)

    lines = cleaned.splitlines()
    while lines and _looks_like_metadata(lines[0]):
        lines.pop(0)

    cleaned = "\n".join(lines).strip()
    cleaned = _strip_trailing_commentary(cleaned)
    if _looks_like_reasoning_only(cleaned):
        return _stabilize_output(fallback, language)
    return _stabilize_output(cleaned or fallback, language)


def polish_output_is_usable(raw_output: str, sanitized_output: str, fallback: str) -> bool:
    if not raw_output.strip():
        return False
    if _looks_like_reasoning_only(_strip_thinking_blocks(raw_output)):
        return False
    return sanitized_output.strip() != fallback.strip()


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


def _strip_thinking_blocks(text: str) -> str:
    without_blocks = re.sub(r"<think\b[^>]*>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL)
    without_blocks = re.sub(r"<thinking\b[^>]*>.*?</thinking>", "", without_blocks, flags=re.IGNORECASE | re.DOTALL)
    return without_blocks.strip()


def _extract_final_section(text: str) -> str | None:
    tag_match = re.search(r"<final\b[^>]*>(.*?)</final>", text, flags=re.IGNORECASE | re.DOTALL)
    if tag_match:
        return tag_match.group(1).strip()

    open_tag_match = re.search(r"<final\b[^>]*>\s*(.*)$", text, flags=re.IGNORECASE | re.DOTALL)
    if open_tag_match:
        return open_tag_match.group(1).strip()

    marker_match = re.search(
        r"(?:texto final|respuesta final|correccion final|salida final|final)\s*:?\s*(.*)$",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if marker_match:
        return marker_match.group(1).strip()
    return None


def _strip_final_tag_fragments(text: str) -> str:
    cleaned = re.sub(r"</?final\b[^>]*>", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"(?im)^\s*final\s*:?\s*", "", cleaned)
    return cleaned.strip()


def _looks_like_reasoning_only(text: str) -> bool:
    normalized = _normalize(text)
    if not normalized:
        return True
    if _looks_like_numbered_reasoning(text):
        return True
    starters = (
        "el usuario quiere",
        "el texto esta bien transcrito",
        "el texto tiene",
        "debo ",
        "tengo que ",
        "voy a ",
        "voy a corregir",
        "mirandolo bien",
        "la tarea es",
        "the user wants",
        "i need to",
        "we need to",
    )
    return any(normalized.startswith(starter) for starter in starters)


def _looks_like_numbered_reasoning(text: str) -> bool:
    normalized = _normalize(text)
    numbered_lines = re.findall(r"(?m)^\s*\d+[.)]\s+", text)
    if len(numbered_lines) < 2:
        return False
    reasoning_terms = (
        "voy a corregir",
        "aqui falta",
        "podria ser",
        "parece",
        "lo mas natural",
        "mirandolo bien",
        "en el contexto",
    )
    return any(term in normalized for term in reasoning_terms)


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
