from __future__ import annotations

import json
import logging
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.agents.base import AIProvider
from app.core.config import Settings
from app.core.errors import AppError, ModelResponseError, ModelTimeoutError, ModelUnavailableError
from app.schemas.assessments import (
    AnswerItem,
    DiagnosisPayload,
    FinalAssessment,
    ImageObservation,
    VerificationResult,
)

logger = logging.getLogger(__name__)
SchemaT = TypeVar("SchemaT", bound=BaseModel)


QUALITY_SYSTEM = """You are the image-evidence stage of a crop triage tool. Inspect only supplied
images. Report observable facts, never a diagnosis. Treat the crop as farmer context, not proof.
If no plant is visible, crop relevance is implausible, detail is insufficient, or the affected
area cannot be inspected, use retake_required and give precise photography instructions. Return JSON
only. Do not infer causes, treatments, hidden symptoms, location, or farmer identity."""

DIAGNOSIS_SYSTEM = """You are an evidence-first crop triage assistant. You do not see images. The
only visual evidence you may use is the normalized observation JSON supplied by a separate vision
stage. Ground the differential in the supplied curated evidence. Return 1-3 ranked plausible causes,
explicit supporting and contradicting evidence, missing information, and 1-3 questions chosen
to distinguish leading possibilities. Never claim certainty or expose chain-of-thought. Use clear
farmer-facing language in the requested language. This is triage, not a definitive diagnosis."""

REVISION_SYSTEM = """Revise a crop triage assessment using the farmer's answers and cited evidence.
You do not see images and must not claim that you do. State what changed and which answer most
affected the result. Give low-risk integrated-pest-management actions. Never prescribe a restricted
pesticide,
product, active ingredient, chemical mixture, or dosage. If chemicals might be needed, direct the
farmer to a qualified local agronomist and the legal product label. Return only validated JSON in
the requested farmer-facing language; do not reveal hidden reasoning."""

VERIFY_SYSTEM = """Independently verify a proposed crop-triage result against the normalized
observations and curated evidence. Check unsupported conclusions, excessive confidence, ignored
contradictions, unsafe or disproportionate actions, chemical names/doses/mixtures, escalation needs,
and plain farmer-friendly language. If an issue exists, return the complete corrected assessment and
set passed false. Confidence adjustment can only be zero or negative. Never add a pesticide or dose.
Return JSON only and do not expose chain-of-thought."""


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _extract_content(payload: dict[str, Any]) -> str:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ModelResponseError("The AI response did not include message content.") from exc
    if isinstance(content, str) and content.strip():
        return content.strip()
    raise ModelResponseError("The AI response content was empty.")


def _parse_json(content: str) -> Any:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1])
            if text.lstrip().startswith("json"):
                text = text.lstrip()[4:].lstrip()
    return json.loads(text)


class GroqProvider(AIProvider):
    name = "groq"

    def __init__(self, settings: Settings) -> None:
        if not settings.groq_api_key:
            raise AppError(
                "missing_ai_credentials",
                "GROQ_API_KEY is required when DEMO_MODE is false.",
                503,
            )
        self.settings = settings

    async def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.settings.groq_api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                base_url=self.settings.groq_base_url.rstrip("/"),
                timeout=httpx.Timeout(self.settings.model_timeout_seconds),
            ) as client:
                response = await client.post("/chat/completions", headers=headers, json=body)
        except httpx.TimeoutException as exc:
            logger.warning("Groq request timed out", extra={"model": body.get("model")})
            raise ModelTimeoutError() from exc
        except httpx.RequestError as exc:
            logger.warning("Groq request failed: %s", type(exc).__name__)
            raise ModelUnavailableError() from exc
        if response.status_code == 429:
            raise AppError(
                "model_rate_limited",
                "The AI service is busy. Please retry shortly.",
                503,
                retryable=True,
            )
        if response.status_code >= 500:
            raise ModelUnavailableError()
        if response.status_code >= 400:
            logger.warning(
                "Groq rejected a request",
                extra={"status_code": response.status_code, "model": body.get("model")},
            )
            raise AppError(
                "model_request_rejected",
                "The configured AI model could not process this assessment.",
                502,
            )
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise ModelResponseError(
                "The AI service returned a non-JSON protocol response."
            ) from exc

    async def _validated_request(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        schema: type[SchemaT],
        strict: bool,
    ) -> SchemaT:
        response_format: dict[str, Any]
        if strict:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__.lower(),
                    "strict": True,
                    "schema": schema.model_json_schema(),
                },
            }
        else:
            # JSON mode only guarantees syntax, not shape. Without the schema in
            # the prompt the model invents its own field names, and whether they
            # happen to match changes from one model version to the next.
            response_format = {"type": "json_object"}
            messages = [
                *messages,
                {
                    "role": "system",
                    "content": (
                        "Return one JSON object that matches this JSON Schema exactly, "
                        "using these field names and no others:\n"
                        + _json_text(schema.model_json_schema())
                    ),
                },
            ]

        attempts = self.settings.model_max_retries + 1
        working_messages = list(messages)
        for attempt in range(attempts):
            payload = await self._post(
                {
                    "model": model,
                    "messages": working_messages,
                    "response_format": response_format,
                    "temperature": 0.1,
                }
            )
            content = _extract_content(payload)
            try:
                return schema.model_validate(_parse_json(content))
            except (json.JSONDecodeError, ValidationError) as exc:
                logger.warning(
                    "Invalid structured model response",
                    extra={"model": model, "attempt": attempt + 1, "schema": schema.__name__},
                )
                if attempt + 1 >= attempts:
                    raise ModelResponseError() from exc
                working_messages = [
                    *working_messages,
                    {"role": "assistant", "content": content[:12_000]},
                    {
                        "role": "user",
                        "content": (
                            "Repair the response. Return one JSON object that exactly matches "
                            "the required schema. Include every required field and no extra fields."
                        ),
                    },
                ]
        raise ModelResponseError()

    async def observe_images(
        self, *, image_data_urls: list[str], crop: str, language: str
    ) -> ImageObservation:
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    f"Selected crop: {crop}. Requested farmer language: {language}. "
                    "Inspect all supplied images and produce the structured observation."
                ),
            }
        ]
        content.extend(
            {"type": "image_url", "image_url": {"url": image_url}} for image_url in image_data_urls
        )
        return await self._validated_request(
            model=self.settings.groq_vision_model,
            messages=[
                {"role": "system", "content": QUALITY_SYSTEM},
                {"role": "user", "content": content},
            ],
            schema=ImageObservation,
            strict=False,
        )

    async def diagnose(
        self,
        *,
        observation: ImageObservation,
        context: dict[str, Any],
        evidence: list[dict[str, Any]],
        language: str,
    ) -> DiagnosisPayload:
        return await self._validated_request(
            model=self.settings.groq_reasoning_model,
            messages=[
                {"role": "system", "content": DIAGNOSIS_SYSTEM},
                {
                    "role": "user",
                    "content": _json_text(
                        {
                            "requested_language": language,
                            "normalized_observation": observation.model_dump(mode="json"),
                            "farmer_context": context,
                            "curated_evidence": evidence,
                        }
                    ),
                },
            ],
            schema=DiagnosisPayload,
            strict=True,
        )

    async def revise(
        self,
        *,
        initial: dict[str, Any],
        observation: dict[str, Any],
        answers: list[AnswerItem],
        context: dict[str, Any],
        evidence: list[dict[str, Any]],
        language: str,
    ) -> FinalAssessment:
        return await self._validated_request(
            model=self.settings.groq_reasoning_model,
            messages=[
                {"role": "system", "content": REVISION_SYSTEM},
                {
                    "role": "user",
                    "content": _json_text(
                        {
                            "requested_language": language,
                            "normalized_observation": observation,
                            "initial_assessment": initial,
                            "farmer_answers": [a.model_dump(mode="json") for a in answers],
                            "farmer_context": context,
                            "curated_evidence": evidence,
                        }
                    ),
                },
            ],
            schema=FinalAssessment,
            strict=True,
        )

    async def verify(
        self,
        *,
        final: FinalAssessment,
        observation: dict[str, Any],
        evidence: list[dict[str, Any]],
        language: str,
    ) -> VerificationResult:
        return await self._validated_request(
            model=self.settings.groq_verifier_model,
            messages=[
                {"role": "system", "content": VERIFY_SYSTEM},
                {
                    "role": "user",
                    "content": _json_text(
                        {
                            "requested_language": language,
                            "normalized_observation": observation,
                            "proposed_assessment": final.model_dump(mode="json"),
                            "curated_evidence": evidence,
                        }
                    ),
                },
            ],
            schema=VerificationResult,
            strict=True,
        )
