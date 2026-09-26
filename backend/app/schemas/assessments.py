from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Crop(StrEnum):
    tomato = "tomato"
    onion = "onion"
    kale = "kale"


class Language(StrEnum):
    english = "en"
    swahili = "sw"


class ImageQuality(StrictModel):
    status: Literal["good", "caution", "retake_required"]
    plant_visible: bool
    crop_relevant: bool
    affected_area_visible: bool
    clarity_score: float = Field(ge=0, le=1)
    lighting_acceptable: bool
    observations: list[NonEmpty] = Field(max_length=8)
    retake_instructions: list[NonEmpty] = Field(max_length=5)

    @model_validator(mode="after")
    def status_matches_evidence(self) -> Self:
        visibility_failed = not (
            self.plant_visible and self.crop_relevant and self.affected_area_visible
        )
        if visibility_failed and self.status != "retake_required":
            raise ValueError("failed visibility checks require a retake")
        if self.status == "good" and not self.lighting_acceptable:
            raise ValueError("good image quality requires acceptable lighting")
        if self.status == "retake_required" and not self.retake_instructions:
            raise ValueError("a required retake must include instructions")
        return self


class ImageObservation(StrictModel):
    image_quality: ImageQuality
    crop_guess: str | None
    observation_summary: NonEmpty
    visible_symptoms: list[NonEmpty] = Field(max_length=12)
    distribution: list[NonEmpty] = Field(max_length=8)

    @model_validator(mode="after")
    def usable_observations_include_a_symptom(self) -> Self:
        if self.image_quality.status != "retake_required" and not self.visible_symptoms:
            raise ValueError("usable image observations require a visible symptom")
        return self


class Hypothesis(StrictModel):
    name: NonEmpty
    category: NonEmpty
    confidence: float = Field(ge=0, le=1)
    supporting_evidence: list[NonEmpty] = Field(min_length=1, max_length=8)
    contradicting_evidence: list[NonEmpty] = Field(max_length=8)
    missing_information: list[NonEmpty] = Field(max_length=8)
    severity: Literal["low", "moderate", "high", "unknown"]


class FollowUpQuestion(StrictModel):
    id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9_-]{1,40}$")]
    text: NonEmpty
    input_type: Literal["yes_no", "multiple_choice", "short_text"]
    options: list[NonEmpty] = Field(max_length=6)
    explanation: NonEmpty
    distinguishes: list[NonEmpty] = Field(min_length=1, max_length=3)

    @field_validator("options")
    @classmethod
    def options_match_input_type(cls, value: list[str], info: Any) -> list[str]:
        input_type = info.data.get("input_type")
        if input_type == "multiple_choice" and len(value) < 2:
            raise ValueError("multiple_choice questions need at least two options")
        if input_type in {"yes_no", "short_text"}:
            # The UI draws these controls itself. Models routinely add
            # ["Yes", "No"] anyway; that is redundant, not wrong, so it is
            # dropped rather than failing the whole assessment over it.
            return []
        return value


class DiagnosisPayload(StrictModel):
    observation_summary: NonEmpty
    hypotheses: list[Hypothesis] = Field(min_length=1, max_length=3)
    follow_up_questions: list[FollowUpQuestion] = Field(min_length=1, max_length=3)
    overall_confidence: float = Field(ge=0, le=1)
    urgency: Literal["low", "moderate", "high"]
    uncertainty_message: NonEmpty
    requires_expert: bool


class AssessmentResult(DiagnosisPayload):
    image_quality: ImageQuality
    sources: list[NonEmpty] = Field(max_length=8)
    simulated: bool


class ActionPlan(StrictModel):
    do_today: list[NonEmpty] = Field(min_length=1, max_length=8)
    monitor: list[NonEmpty] = Field(min_length=1, max_length=8)
    avoid: list[NonEmpty] = Field(min_length=1, max_length=8)
    escalate_when: list[NonEmpty] = Field(min_length=1, max_length=8)


class FinalAssessment(StrictModel):
    observation_summary: NonEmpty
    hypotheses: list[Hypothesis] = Field(min_length=1, max_length=3)
    most_likely_explanation: NonEmpty
    overall_confidence: float = Field(ge=0, le=1)
    urgency: Literal["low", "moderate", "high"]
    uncertainty_message: NonEmpty
    what_changed: NonEmpty
    greatest_effect: NonEmpty
    action_plan: ActionPlan
    warning_signs: list[NonEmpty] = Field(min_length=1, max_length=8)
    expert_guidance: NonEmpty
    requires_expert: bool
    sources: list[NonEmpty] = Field(min_length=1, max_length=8)
    limitations_notice: NonEmpty
    simulated: bool


class VerificationResult(StrictModel):
    passed: bool
    issues: list[NonEmpty] = Field(max_length=10)
    corrected_assessment: FinalAssessment | None
    confidence_adjustment: float = Field(ge=-1, le=0)
    chemical_advice_removed: bool

    @model_validator(mode="after")
    def result_is_internally_consistent(self) -> Self:
        if self.passed:
            if (
                self.issues
                or self.corrected_assessment is not None
                or self.confidence_adjustment != 0
                or self.chemical_advice_removed
            ):
                raise ValueError("a passed verification cannot report corrections or issues")
        elif (
            not self.issues
            and self.corrected_assessment is None
            and self.confidence_adjustment == 0
            and not self.chemical_advice_removed
        ):
            raise ValueError("a failed verification must explain or apply a correction")
        return self


class AnswerItem(StrictModel):
    question_id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9_-]{1,40}$")]
    answer: bool | NonEmpty


class AnswerSubmission(StrictModel):
    answers: list[AnswerItem] = Field(min_length=1, max_length=3)

    @field_validator("answers")
    @classmethod
    def unique_question_ids(cls, value: list[AnswerItem]) -> list[AnswerItem]:
        ids = [item.question_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("question_id values must be unique")
        return value


class StorageImageReference(StrictModel):
    object_path: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=512,
            pattern=r"^[A-Za-z0-9._/-]+$",
        ),
    ]
    content_type: Literal["image/jpeg", "image/png", "image/webp"]
    size_bytes: int = Field(gt=0, le=25 * 1024 * 1024)


class StoredAssessmentCreate(StrictModel):
    crop: Crop
    growth_stage: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
    ]
    symptom_duration: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
    ]
    watering_conditions: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]
    images: list[StorageImageReference] = Field(min_length=1, max_length=3)
    language: Language = Language.english
    region: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = None
    description: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None
    ) = None
    demo_scenario: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
    ] | None = None


class ImageMetadata(StrictModel):
    id: str
    content_type: Literal["image/jpeg", "image/png", "image/webp"]
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    size_bytes: int = Field(gt=0)
    url: str


class AssessmentDetail(StrictModel):
    id: str
    status: Literal[
        "created", "analyzing", "retake_required", "questions_ready", "completed", "failed"
    ]
    crop: Crop
    growth_stage: str
    region: str | None
    symptom_duration: str
    watering_conditions: str
    description: str | None
    language: Language
    images: list[ImageMetadata]
    image_quality: ImageQuality | None
    model_observation: ImageObservation | None
    initial_assessment: AssessmentResult | None
    answers: list[AnswerItem] | None
    final_assessment: FinalAssessment | None
    verification: VerificationResult | None
    provider_metadata: dict[str, Any]
    timing_metadata: dict[str, float]
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    simulated: bool


class AssessmentSummary(StrictModel):
    id: str
    status: str
    crop: Crop
    region: str | None
    urgency: str | None
    leading_hypothesis: str | None
    created_at: datetime
    completed_at: datetime | None
    simulated: bool


class AssessmentList(StrictModel):
    items: list[AssessmentSummary]
    total: int = Field(ge=0)


class DashboardRegion(StrictModel):
    region: str
    reports: int = Field(ge=0)


class DashboardSummary(StrictModel):
    reports_this_week: int = Field(ge=0)
    most_affected_crop: str | None
    most_common_category: str | None
    reports_by_region: list[DashboardRegion]
    high_urgency_signals: int = Field(ge=0)
    disclaimer: str
    simulated: bool


class RuntimeInfo(StrictModel):
    ai_provider: str
    execution_mode: Literal["demo", "live"]
    vision_model: str
    reasoning_model: str
    verifier_model: str
    last_stage_latencies_ms: dict[str, float]
    database: Literal["postgresql", "sqlite", "other"]
    image_storage: Literal["local", "firebase"]


class ErrorBody(StrictModel):
    code: str
    message: str
    retryable: bool
    request_id: str
    details: Any | None = None


class ErrorEnvelope(StrictModel):
    error: ErrorBody
