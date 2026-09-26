from __future__ import annotations

import httpx
import pytest

from app.agents.groq import GroqProvider
from app.core.config import Settings
from app.core.errors import ModelTimeoutError
from app.schemas.assessments import ImageObservation


def test_neon_style_url_is_normalized_for_asyncpg() -> None:
    settings = Settings(
        database_url=(
            "postgresql://user:p%40ss@ep-test-pooler.us-east-2.aws.neon.tech/neondb"
            "?sslmode=require&channel_binding=require&application_name=shambalens"
        ),
        database_url_unpooled=(
            "postgresql://user:p%40ss@ep-test.us-east-2.aws.neon.tech/neondb"
            "?sslmode=require&channel_binding=require"
        ),
    )
    assert settings.async_database_url.startswith("postgresql+asyncpg://")
    assert "ssl=require" in settings.async_database_url
    assert "sslmode" not in settings.async_database_url
    assert "channel_binding" not in settings.async_database_url
    assert "pooler" not in settings.migration_database_url
    assert "p%40ss" in settings.async_database_url


def test_comma_separated_allowed_origins_are_accepted() -> None:
    settings = Settings(allowed_origins="https://app.example,https://preview.example")  # type: ignore[arg-type]
    assert settings.allowed_origins == ["https://app.example", "https://preview.example"]


@pytest.mark.asyncio
async def test_groq_timeout_is_mapped_without_leaking_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TimeoutClient:
        def __init__(self, **_: object) -> None: ...

        async def __aenter__(self) -> TimeoutClient:
            return self

        async def __aexit__(self, *_: object) -> None: ...

        async def post(self, *_: object, **__: object) -> httpx.Response:
            raise httpx.ReadTimeout("secret request timed out")

    monkeypatch.setattr(httpx, "AsyncClient", TimeoutClient)
    provider = GroqProvider(Settings(groq_api_key="gsk_test_secret", demo_mode=False))
    with pytest.raises(ModelTimeoutError) as caught:
        await provider._post({"model": "test-model"})
    assert "gsk_test_secret" not in str(caught.value)


@pytest.mark.asyncio
async def test_json_object_response_is_repaired_once(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = GroqProvider(
        Settings(groq_api_key="gsk_test", demo_mode=False, model_max_retries=1)
    )
    valid = {
        "image_quality": {
            "status": "good",
            "plant_visible": True,
            "crop_relevant": True,
            "affected_area_visible": True,
            "clarity_score": 0.8,
            "lighting_acceptable": True,
            "observations": ["A leaf is visible."],
            "retake_instructions": [],
        },
        "crop_guess": "tomato",
        "observation_summary": "Brown spots are visible.",
        "visible_symptoms": ["Brown spots"],
        "distribution": ["Lower leaf"],
    }
    responses = [
        {"choices": [{"message": {"content": "not valid JSON"}}]},
        {"choices": [{"message": {"content": __import__("json").dumps(valid)}}]},
    ]

    async def fake_post(_: dict[str, object]) -> dict[str, object]:
        return responses.pop(0)

    monkeypatch.setattr(provider, "_post", fake_post)
    result = await provider._validated_request(
        model="vision-test",
        messages=[{"role": "user", "content": "inspect"}],
        schema=ImageObservation,
        strict=False,
    )
    assert result.crop_guess == "tomato"
    assert not responses


@pytest.mark.asyncio
async def test_json_object_request_tells_the_model_the_field_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JSON mode only guarantees valid JSON. Without the schema in the prompt,
    qwen3.8 answered with its own keys (status, observations, instructions)
    and every analysis failed validation."""
    provider = GroqProvider(Settings(groq_api_key="gsk_test", demo_mode=False))
    sent: list[dict[str, object]] = []

    async def fake_post(body: dict[str, object]) -> dict[str, object]:
        sent.append(body)
        return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(provider, "_post", fake_post)
    with pytest.raises(Exception):
        await provider._validated_request(
            model="vision-test",
            messages=[{"role": "user", "content": "inspect"}],
            schema=ImageObservation,
            strict=False,
        )
    prompt = "\n".join(str(m["content"]) for m in sent[0]["messages"])  # type: ignore[index, union-attr]
    for field in ImageObservation.model_fields:
        assert field in prompt
