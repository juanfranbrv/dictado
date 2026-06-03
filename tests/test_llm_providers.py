from __future__ import annotations

import httpx

from app.providers.llm.fireworks import FireworksLLM


def test_fireworks_rejects_reasoning_output() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                "El texto esta bien transcrito pero tiene errores. Voy a corregir:\n\n"
                                "1. primera observacion\n"
                                "2. segunda observacion"
                            )
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    httpx.Client = client_factory
    try:
        provider = FireworksLLM("key")
        try:
            provider.polish("hola mundo", "es")
        except ValueError:
            return
    finally:
        httpx.Client = original_client

    raise AssertionError("reasoning output was accepted")
