from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.assessments import (
    DiagnosisPayload,
    FollowUpQuestion,
    Hypothesis,
    ImageObservation,
    ImageQuality,
    VerificationResult,
)


def hypothesis(confidence: float = 0.5) -> dict[str, object]:
    return {
        "name": "Early blight",
        "category": "fungal disease",
        "confidence": confidence,
        "supporting_evidence": ["Brown spots"],
        "contradicting_evidence": [],
        "missing_information": [],
        "severity": "moderate",
    }


def diagnosis(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "observation_summary": "Brown spots are visible.",
        "hypotheses": [hypothesis()],
        "follow_up_questions": [
            {
                "id": "q1",
                "text": "Did symptoms start low on the plant?",
                "input_type": "yes_no",
                "options": [],
                "explanation": "This distinguishes disease distribution.",
                "distinguishes": ["Early blight", "Stress"],
            }
        ],
        "overall_confidence": 0.5,
        "urgency": "moderate",
        "uncertainty_message": "The cause is not confirmed.",
        "requires_expert": False,
    }
    value.update(updates)
    return value


@pytest.mark.parametrize("value", [-0.01, 1.01])
def test_confidence_bounds(value: float) -> None:
    with pytest.raises(ValidationError):
        Hypothesis.model_validate(hypothesis(value))


def test_hypothesis_and_question_limits() -> None:
    with pytest.raises(ValidationError):
        DiagnosisPayload.model_validate(diagnosis(hypotheses=[hypothesis()] * 4))
    question = {
        "id": "q1",
        "text": "Is it wet?",
        "input_type": "yes_no",
        "options": [],
        "explanation": "Separates stress from infection.",
        "distinguishes": ["Stress"],
    }
    with pytest.raises(ValidationError):
        DiagnosisPayload.model_validate(diagnosis(follow_up_questions=[question] * 4))


def test_question_controls_are_consistent() -> None:
    with pytest.raises(ValidationError):
        FollowUpQuestion.model_validate(
            {
                "id": "choice",
                "text": "Where?",
                "input_type": "multiple_choice",
                "options": ["Lower leaves"],
                "explanation": "Distinguishes distributions.",
                "distinguishes": ["Disease", "Stress"],
            }
        )


def test_image_quality_rejects_contradictory_statuses() -> None:
    value = {
        "status": "good",
        "plant_visible": False,
        "crop_relevant": True,
        "affected_area_visible": True,
        "clarity_score": 0.8,
        "lighting_acceptable": True,
        "observations": ["No plant is visible."],
        "retake_instructions": [],
    }
    with pytest.raises(ValidationError):
        ImageQuality.model_validate(value)
    value.update({"status": "retake_required"})
    with pytest.raises(ValidationError):
        ImageQuality.model_validate(value)


def test_retake_observation_can_honestly_have_no_visible_symptoms() -> None:
    result = ImageObservation.model_validate(
        {
            "image_quality": {
                "status": "retake_required",
                "plant_visible": False,
                "crop_relevant": False,
                "affected_area_visible": False,
                "clarity_score": 0,
                "lighting_acceptable": False,
                "observations": ["No crop is visible."],
                "retake_instructions": ["Photograph the affected crop."],
            },
            "crop_guess": None,
            "observation_summary": "No crop evidence can be assessed.",
            "visible_symptoms": [],
            "distribution": [],
        }
    )
    assert result.visible_symptoms == []


def test_verification_state_must_be_consistent() -> None:
    with pytest.raises(ValidationError):
        VerificationResult(
            passed=True,
            issues=["Unsupported claim."],
            corrected_assessment=None,
            confidence_adjustment=0,
            chemical_advice_removed=False,
        )
    with pytest.raises(ValidationError):
        VerificationResult(
            passed=False,
            issues=[],
            corrected_assessment=None,
            confidence_adjustment=0,
            chemical_advice_removed=False,
        )


@pytest.mark.parametrize("input_type", ["yes_no", "short_text"])
def test_redundant_options_on_free_controls_are_dropped(input_type: str) -> None:
    """gpt-oss-120b adds ["Yes", "No"] to yes/no questions. Rejecting that
    failed every live analysis; the UI never reads options for these types."""
    question = FollowUpQuestion.model_validate(
        {
            "id": "wet",
            "text": "Is it wet?",
            "input_type": input_type,
            "options": ["Yes", "No"],
            "explanation": "Separates stress from infection.",
            "distinguishes": ["Stress"],
        }
    )
    assert question.options == []
