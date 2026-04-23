from app.providers.llm.utils import sanitize_polish_output


def test_sanitize_removes_leaked_headers() -> None:
    result = sanitize_polish_output("Texto pulido:\nHola, mundo.", "hola mundo")

    assert result == "Hola, mundo."


def test_sanitize_removes_trailing_explanation_paragraph() -> None:
    result = sanitize_polish_output(
        (
            "¿Qué he hecho? El prompt de usuario ya no envía app, idioma o texto.\n\n"
            "El usuario puede enviar instrucciones mínimas como "
            "\"haz una microcorrección rápida del dictado\" y el modelo responderá "
            "con la corrección del texto."
        ),
        "que he hecho el prom de usuario ya no envia app idioma o texto",
    )

    assert result == "¿Qué he hecho? El prompt de usuario ya no envía app, idioma o texto."


def test_sanitize_keeps_real_multi_paragraph_dictation() -> None:
    result = sanitize_polish_output(
        "Primer punto corregido.\n\nSegundo punto corregido.",
        "primer punto corregido segundo punto corregido",
    )

    assert result == "Primer punto corregido.\n\nSegundo punto corregido."


def test_sanitize_adds_opening_spanish_question_mark() -> None:
    result = sanitize_polish_output("Que puedo hacer?", "que puedo hacer", language="es")

    assert result == "¿Que puedo hacer?"


def test_sanitize_infers_spanish_question_from_interrogative_start() -> None:
    result = sanitize_polish_output("Que puedo hacer.", "que puedo hacer", language="es")

    assert result == "¿Que puedo hacer?"
