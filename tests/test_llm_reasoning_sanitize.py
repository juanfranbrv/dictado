from app.providers.llm.utils import sanitize_polish_output


def test_sanitize_removes_thinking_block() -> None:
    result = sanitize_polish_output(
        (
            "<think>\n"
            "El usuario quiere que corrija el texto solo en terminos de puntuacion.\n"
            "</think>\n\n"
            "Fijate, obtengo en la caja de texto el razonamiento del modelo en lugar del texto que he dictado."
        ),
        "fijate obtengo en la caja de texto el razonamiento del modelo en lugar del texto que he deictado",
        language="es",
    )

    assert result == "Fijate, obtengo en la caja de texto el razonamiento del modelo en lugar del texto que he dictado."


def test_sanitize_extracts_final_answer_section() -> None:
    result = sanitize_polish_output(
        (
            "Razonamiento: debo mantener el estilo y corregir solo errores obvios.\n\n"
            "Texto final:\n"
            "Fijate, obtengo en la caja de texto el razonamiento del modelo en lugar del texto que he dictado."
        ),
        "fijate obtengo en la caja de texto el razonamiento del modelo en lugar del texto que he deictado",
        language="es",
    )

    assert result == "Fijate, obtengo en la caja de texto el razonamiento del modelo en lugar del texto que he dictado."


def test_sanitize_removes_final_xml_tags() -> None:
    result = sanitize_polish_output(
        "<final>Vale, esto es una prueba.</final>",
        "vale esto es una prueba",
        language="es",
    )

    assert result == "Vale, esto es una prueba."


def test_sanitize_removes_unclosed_final_tag() -> None:
    result = sanitize_polish_output(
        "<final>\nVale, esto es una prueba.",
        "vale esto es una prueba",
        language="es",
    )

    assert result == "Vale, esto es una prueba."


def test_sanitize_removes_plain_final_label() -> None:
    result = sanitize_polish_output(
        "Final\nVale, esto es una prueba.",
        "vale esto es una prueba",
        language="es",
    )

    assert result == "Vale, esto es una prueba."


def test_sanitize_falls_back_when_only_reasoning_is_returned() -> None:
    result = sanitize_polish_output(
        "El usuario quiere que corrija el texto solo en terminos de puntuacion, mayusculas y errores obvios.",
        "fijate obtengo en la caja de texto el razonamiento del modelo",
        language="es",
    )

    assert result == "fijate obtengo en la caja de texto el razonamiento del modelo"


def test_sanitize_falls_back_for_numbered_reasoning_analysis() -> None:
    result = sanitize_polish_output(
        (
            "El texto esta bien transcrito pero tiene algunos errores de puntuacion y mayusculas obvios. "
            "Voy a corregir:\n\n"
            "1. \"lo que pasa es que como usuario\" - bien\n"
            "2. \"cuando estoy grabando no veo realmente que esta pasando\" - aqui falta una interrogativa clara.\n"
            "3. \"no se si el LLM funciona\" - esto parece una estructura redundante.\n\n"
            "Mirandolo bien: no se..."
        ),
        "lo que pasa es que como usuario cuando estoy grabando no veo realmente que esta pasando",
        language="es",
    )

    assert result == "lo que pasa es que como usuario cuando estoy grabando no veo realmente que esta pasando"
