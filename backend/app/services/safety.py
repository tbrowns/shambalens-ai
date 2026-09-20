from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.assessments import (
    ActionPlan,
    DiagnosisPayload,
    FinalAssessment,
    VerificationResult,
)

MAX_TRIAGE_CONFIDENCE = 0.9

GUARDED_ACTION_FIELDS = ("do_today", "monitor", "avoid", "escalate_when")


class ProhibitedTerms(BaseModel):
    """Reviewable lexicon behind the deterministic chemical-advice guardrail."""

    model_config = ConfigDict(extra="forbid")

    comment: list[str] = Field(default_factory=list, alias="_comment")
    chemical_classes: list[str] = Field(min_length=1)
    active_ingredients: list[str] = Field(min_length=1)
    trade_names: list[str] = Field(min_length=1)
    swahili_terms: list[str] = Field(min_length=1)
    dose_units: list[str] = Field(min_length=1)
    dose_denominators: list[str] = Field(min_length=1)
    dose_separators: list[str] = Field(min_length=1)
    mixture_verbs: list[str] = Field(min_length=1)
    mixture_targets: list[str] = Field(min_length=1)
    concentration_words: list[str] = Field(min_length=1)
    formulation_codes: list[str] = Field(min_length=1)


@lru_cache
def load_prohibited_terms() -> ProhibitedTerms:
    path = Path(__file__).resolve().parents[1] / "knowledge" / "prohibited_terms.json"
    return ProhibitedTerms.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _term_regex(term: str) -> str:
    """Match a lexicon term on word boundaries with optional plural and flexible spacing."""
    parts = [re.escape(part) for part in re.split(r"[\s-]+", term.strip()) if part]
    return r"[\s-]*".join(parts) + r"s?"


def _ordered(terms: list[str]) -> list[str]:
    # Longest first so ``litre`` is tried before ``l`` and multiword terms before their parts.
    return sorted(dict.fromkeys(terms), key=lambda value: (-len(value), value))


def _alternation(terms: list[str]) -> str:
    return "|".join(re.escape(term) for term in _ordered(terms))


def _term_pattern(terms: list[str]) -> re.Pattern[str]:
    return re.compile(r"\b(?:" + "|".join(_term_regex(t) for t in _ordered(terms)) + r")\b", re.I)


_LEXICON = load_prohibited_terms()
_NUMBER = r"\d+(?:[.,]\d+)?"
_UNITS = _alternation(_LEXICON.dose_units)
_DENOMINATORS = _alternation(_LEXICON.dose_denominators)
_SEPARATORS = _alternation(_LEXICON.dose_separators)
_CONCENTRATION_WORDS = _alternation(_LEXICON.concentration_words)
# English places the number first (``20 ml``); Swahili places it after the unit (``lita 20``).
# A hyphen may join a number to its unit (``a 20-litre knapsack``).
_QUANTITY = rf"(?:{_NUMBER}[\s-]*(?:{_UNITS})|(?:{_UNITS})\s*{_NUMBER})"
_DENOMINATOR = (
    rf"(?:(?:{_NUMBER}[\s-]*)?(?:{_DENOMINATORS})|(?:{_DENOMINATORS})\s*{_NUMBER})"
)
_ARTICLE = r"(?:\s+(?:each|every|kila|a|an|one|the))?"
_CLAUSE = r"[^.;!?\n]"
# ``50 g of the product per 20 litres`` / ``kijiko 1 cha dawa kwenye lita 20``.
_SUBSTANCE = rf"(?:\s+(?:of|ya|cha|wa|za|vya)\s+{_CLAUSE}{{0,30}}?)?"
_RATIO = r"\d{1,3}\s*:\s*\d{1,4}"
_DILUTION_CONTEXT = r"(?:dilut\w*|ratio|uwiano)"
_PERCENT = rf"(?:{_NUMBER}\s*(?:%|percent)|asilimia\s*{_NUMBER}|{_NUMBER}\s*asilimia)"
# Up to three words may sit between a percentage and its noun (``2% copper solution``,
# ``asilimia 2 ya mchanganyiko``); ``of`` is excluded so ``10% of plants`` stays permitted.
_PERCENT_QUALIFIER = r"(?:(?!of\b)[a-z][a-z-]*\s+){0,3}"

CHEMICAL_CLASS_PATTERN = _term_pattern(_LEXICON.chemical_classes)
ACTIVE_INGREDIENT_PATTERN = _term_pattern(_LEXICON.active_ingredients)
TRADE_NAME_PATTERN = _term_pattern(_LEXICON.trade_names)
SWAHILI_TERM_PATTERN = _term_pattern(_LEXICON.swahili_terms)
DOSAGE_PATTERN = re.compile(
    rf"\b{_QUANTITY}{_SUBSTANCE}\s*(?:{_SEPARATORS}){_ARTICLE}\s*{_DENOMINATOR}\b",
    re.I,
)
DILUTION_PATTERN = re.compile(
    rf"\b{_DILUTION_CONTEXT}\b{_CLAUSE}{{0,40}}?\b{_RATIO}\b"
    rf"|\b{_RATIO}\b{_CLAUSE}{{0,40}}?\b{_DILUTION_CONTEXT}\b"
    rf"|\b(?:{_NUMBER}|one)\s*parts?\b{_CLAUSE}{{0,20}}?\b(?:to|per|in|kwa)\b{_CLAUSE}{{0,10}}?"
    rf"\b(?:{_NUMBER}|[a-z]+)\s*parts?\b",
    re.I,
)
CONCENTRATION_PATTERN = re.compile(
    rf"\b{_PERCENT}\s*{_PERCENT_QUALIFIER}(?:{_CONCENTRATION_WORDS})\b"
    rf"|\b(?:{_CONCENTRATION_WORDS})\s+(?:of|ya|wa|za)\s+{_PERCENT}",
    re.I,
)
# Formulation codes are uppercase product labels (``Karate 5 EC``). Matching is case-sensitive
# so ordinary prose is never mistaken for a product code.
FORMULATION_PATTERN = re.compile(
    rf"\b{_NUMBER}\s?(?:{_alternation(_LEXICON.formulation_codes)})\b"
)
MIXTURE_PATTERN = re.compile(
    rf"\b(?:{_alternation(_LEXICON.mixture_verbs)})\b{_CLAUSE}{{0,50}}"
    rf"\b(?:{_alternation(_LEXICON.mixture_targets)})\b",
    re.I,
)

PROHIBITED_INSTRUCTION_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("chemical_class", CHEMICAL_CLASS_PATTERN),
    ("active_ingredient", ACTIVE_INGREDIENT_PATTERN),
    ("trade_name", TRADE_NAME_PATTERN),
    ("swahili_term", SWAHILI_TERM_PATTERN),
    ("dosage", DOSAGE_PATTERN),
    ("dilution_ratio", DILUTION_PATTERN),
    ("concentration", CONCENTRATION_PATTERN),
    ("formulation_code", FORMULATION_PATTERN),
    ("mixture", MIXTURE_PATTERN),
)


SAFE_REFERRAL = (
    "If a chemical treatment may be needed, consult a qualified local agronomist and follow "
    "the legal product label and local regulations."
)
SAFE_REFERRAL_SW = (
    "Ikiwa tiba ya kemikali inaweza kuhitajika, wasiliana na mtaalamu wa kilimo "
    "aliyehitimu na ufuate lebo halali ya bidhaa pamoja na kanuni za eneo."
)

SAFE_ACTION_REPLACEMENTS = {
    "en": {
        "do_today": SAFE_REFERRAL,
        "monitor": "Record visible changes and seek qualified advice if symptoms worsen.",
        "avoid": "Avoid unverified treatments or mixtures.",
        "escalate_when": "Seek qualified help if symptoms spread or plants decline quickly.",
    },
    "sw": {
        "do_today": SAFE_REFERRAL_SW,
        "monitor": "Andika mabadiliko yanayoonekana na tafuta ushauri wa mtaalamu dalili zikizidi.",
        "avoid": "Epuka tiba au michanganyiko ambayo haijathibitishwa.",
        "escalate_when": "Tafuta msaada wa mtaalamu dalili zikienea au mimea ikidhoofika haraka.",
    },
}


def prohibited_instruction_rules(value: str) -> tuple[str, ...]:
    """Name every guardrail rule that a farmer-facing instruction violates."""
    return tuple(name for name, pattern in PROHIBITED_INSTRUCTION_RULES if pattern.search(value))


def _unsafe_positive_action(value: str) -> bool:
    return bool(prohibited_instruction_rules(value))


def _contains_unsafe_action(final: FinalAssessment) -> bool:
    action_values = final.action_plan.model_dump(mode="python")
    return any(
        _unsafe_positive_action(value)
        for field in GUARDED_ACTION_FIELDS
        for value in action_values[field]
    ) or _unsafe_positive_action(final.expert_guidance)


def cap_diagnosis_confidence(diagnosis: DiagnosisPayload) -> DiagnosisPayload:
    """Apply the public triage ceiling before initial percentages are stored."""
    values = diagnosis.model_dump(mode="python")
    values["overall_confidence"] = min(diagnosis.overall_confidence, MAX_TRIAGE_CONFIDENCE)
    values["hypotheses"] = [
        {
            **item.model_dump(mode="python"),
            "confidence": min(item.confidence, MAX_TRIAGE_CONFIDENCE),
        }
        for item in diagnosis.hypotheses
    ]
    return DiagnosisPayload.model_validate(values)


def apply_action_guardrails(
    final: FinalAssessment, *, language: str = "en"
) -> tuple[FinalAssessment, bool, list[str]]:
    selected_language = "sw" if language == "sw" else "en"
    replacements = SAFE_ACTION_REPLACEMENTS[selected_language]
    removed = False
    issues: list[str] = []
    action_values = final.action_plan.model_dump(mode="python")
    for field in GUARDED_ACTION_FIELDS:
        safe_values = []
        for value in action_values[field]:
            if _unsafe_positive_action(value):
                removed = True
            else:
                safe_values.append(value)
        if not safe_values:
            safe_values.append(replacements[field])
        action_values[field] = safe_values
    expert_guidance = final.expert_guidance
    if _unsafe_positive_action(expert_guidance):
        removed = True
        expert_guidance = SAFE_REFERRAL_SW if selected_language == "sw" else SAFE_REFERRAL
    if removed:
        issues.append(
            "Ushauri mahususi wa kemikali, mchanganyiko au kipimo uliondolewa."
            if selected_language == "sw"
            else "Specific chemical, mixture, or dosage advice was removed."
        )
        do_today = action_values["do_today"]
        referral = SAFE_REFERRAL_SW if selected_language == "sw" else SAFE_REFERRAL
        if referral not in do_today:
            if len(do_today) >= 8:
                do_today[-1] = referral
            else:
                do_today.append(referral)

    # ``model_copy(update=...)`` deliberately skips Pydantic validation. Rebuild
    # guarded structures so an appended referral can never exceed schema caps.
    action_plan = ActionPlan.model_validate(action_values)
    corrected_values = final.model_dump(mode="python")
    corrected_values["action_plan"] = action_plan
    corrected_values["expert_guidance"] = expert_guidance
    corrected = FinalAssessment.model_validate(corrected_values)

    confidence_capped = corrected.overall_confidence > MAX_TRIAGE_CONFIDENCE or any(
        item.confidence > MAX_TRIAGE_CONFIDENCE for item in corrected.hypotheses
    )
    if confidence_capped:
        removed = True
        issues.append(
            "Kiwango cha uhakika kilipunguzwa kwa sababu tathmini ya picha haiwezi "
            "kuthibitisha chanzo."
            if selected_language == "sw"
            else "Overall confidence was capped because image-based triage cannot confirm a cause."
        )
        corrected_values = corrected.model_dump(mode="python")
        corrected_values["overall_confidence"] = min(
            corrected.overall_confidence, MAX_TRIAGE_CONFIDENCE
        )
        corrected_values["hypotheses"] = [
            {
                **item.model_dump(mode="python"),
                "confidence": min(item.confidence, MAX_TRIAGE_CONFIDENCE),
            }
            for item in corrected.hypotheses
        ]
        corrected = FinalAssessment.model_validate(corrected_values)
    return corrected, removed, issues


def finalize_verification(
    proposed: FinalAssessment, verification: VerificationResult, *, language: str = "en"
) -> tuple[FinalAssessment, VerificationResult]:
    selected = verification.corrected_assessment or proposed
    if not verification.passed:
        requested_adjustment = verification.confidence_adjustment
        if verification.corrected_assessment is None and requested_adjustment == 0:
            requested_adjustment = -0.1
        if requested_adjustment < 0:
            previous_confidence = selected.overall_confidence
            selected_values = selected.model_dump(mode="python")
            selected_values["overall_confidence"] = max(
                0.0, previous_confidence + requested_adjustment
            )
            selected = FinalAssessment.model_validate(selected_values)
            applied_adjustment = round(selected.overall_confidence - previous_confidence, 6)
            verification_values = verification.model_dump(mode="python")
            verification_values["confidence_adjustment"] = applied_adjustment
            if verification.corrected_assessment is not None:
                verification_values["corrected_assessment"] = selected
            verification = VerificationResult.model_validate(verification_values)
    chemical_advice_removed = _contains_unsafe_action(selected)
    selected, changed, deterministic_issues = apply_action_guardrails(
        selected, language=language
    )
    if changed:
        verification_values = verification.model_dump(mode="python")
        verification_values.update(
            {
                "passed": False,
                "issues": list(dict.fromkeys(verification.issues + deterministic_issues))[:10],
                "corrected_assessment": selected,
                "chemical_advice_removed": verification.chemical_advice_removed
                or chemical_advice_removed,
            }
        )
        verification = VerificationResult.model_validate(verification_values)
    return selected, verification
