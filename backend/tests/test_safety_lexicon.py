from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import pytest

from app.fixtures.demo import SCENARIO_BY_CROP, DemoProvider, _diagnosis, _observation
from app.schemas.assessments import ActionPlan, AnswerItem, FinalAssessment, VerificationResult
from app.services.retrieval import evidence_for_prompt, retrieve_evidence
from app.services.safety import (
    GUARDED_ACTION_FIELDS,
    SAFE_ACTION_REPLACEMENTS,
    SAFE_REFERRAL,
    SAFE_REFERRAL_SW,
    apply_action_guardrails,
    finalize_verification,
    load_prohibited_terms,
    prohibited_instruction_rules,
)

KNOWLEDGE_BASE = Path(__file__).resolve().parents[1] / "app" / "knowledge" / "crop_problems.json"

# Instructions a model could plausibly generate that the policy must always remove, with the
# rule family expected to catch each one. Several are deliberately outside the old regexes:
# plurals, a number inside the denominator, Swahili word order, trade names, dilution ratios,
# percentage concentrations, formulation codes, and doses with an intervening substance.
PROHIBITED_INSTRUCTIONS: list[tuple[str, str]] = [
    ("Apply pesticides weekly.", "chemical_class"),
    ("Apply a wettable powder fungicide.", "chemical_class"),
    ("Buy an agro-chemical from the agrovet and spray.", "chemical_class"),
    ("Spray mancozeb at 50 g per 20 litres of water.", "active_ingredient"),
    ("Spray copper oxychloride on the seedlings.", "active_ingredient"),
    ("Drench the soil with imidacloprid.", "active_ingredient"),
    ("Spray lambda cyhalothrin in the evening.", "active_ingredient"),
    ("Apply 2,4-D between the rows.", "active_ingredient"),
    ("Fumigate the soil with metam sodium.", "active_ingredient"),
    ("Apply streptomycin to the wounds.", "active_ingredient"),
    ("Spray a 2% copper sulphate solution.", "active_ingredient"),
    ("Use Ridomil Gold to control the blight.", "trade_name"),
    ("Mix 2 tablespoons of Dithane in a 20 litre knapsack.", "trade_name"),
    ("Use Karate 5 EC against the caterpillars.", "formulation_code"),
    ("Use Confidor 200 SL on the aphids.", "formulation_code"),
    ("Nyunyizia dawa ya wadudu kila wiki.", "swahili_term"),
    ("Pulizia dawa ya kuua wadudu jioni.", "swahili_term"),
    ("Tumia viuatilifu kwenye shamba.", "swahili_term"),
    ("Tumia kiuawadudu kama Duduthrin.", "swahili_term"),
    ("Apply 20 ml/litre of product.", "dosage"),
    ("Apply 5 ml per 20 l of water.", "dosage"),
    ("Apply 2.5 ml per litre of water.", "dosage"),
    ("Dissolve 50 g in 20 litres of water and drench the soil.", "dosage"),
    ("Mix 50 g in a 20 l knapsack sprayer.", "dosage"),
    ("Apply 50 g of the recommended product per 20 litres of water.", "dosage"),
    ("Add 50 g to 20 litres of water.", "dosage"),
    ("Use 100 ml for every 20 litres.", "dosage"),
    ("Pour 10 ml into a 20 l tank.", "dosage"),
    ("Mix 20 ml in a 20-litre knapsack.", "dosage"),
    ("Apply 50 g per 20-litre knapsack of water.", "dosage"),
    ("Use 30 ml in a 15-l pump.", "dosage"),
    ("Spray 1 capful per litre.", "dosage"),
    ("Changanya gramu 50 kwa lita 20 za maji.", "dosage"),
    ("Weka kijiko 1 cha dawa kwenye lita 20 za maji.", "dosage"),
    ("Weka gramu 50 kwa kila lita 20.", "dosage"),
    ("Weka gramu 50 katika lita 20 za maji.", "dosage"),
    ("Dilute 1:100 and spray the leaves.", "dilution_ratio"),
    ("Apply a 1:50 dilution.", "dilution_ratio"),
    ("Use one part product to ten parts water.", "dilution_ratio"),
    ("Mix 1 part to 10 parts water.", "dilution_ratio"),
    ("Spray a 0.5% solution every 7 days.", "concentration"),
    ("Spray a 2% copper solution.", "concentration"),
    ("Spray a 1% neem oil solution every week.", "concentration"),
    ("Spray at 0.5 percent soap spray strength.", "concentration"),
    ("Spray mchanganyiko wa asilimia 2.", "concentration"),
    ("Spray asilimia 2 ya mchanganyiko.", "concentration"),
    ("Mix a chemical product before watering.", "mixture"),
    ("Changanya dawa na maji kabla ya kunyunyiza.", "mixture"),
]

# Low-risk advice, referral wording, numbers, times, and Swahili phrases that must survive.
PERMITTED_GUIDANCE: list[str] = [
    "Remove badly affected fallen leaves and wash your hands afterward.",
    "Water at soil level and keep leaves dry.",
    "Spray plants with soapy water in the evening.",
    "Spray a strong jet of water to dislodge aphids.",
    "Hand-pick caterpillars in the early morning.",
    "Use insect netting to protect unaffected plants.",
    "Mulch around the plants to keep soil moisture even.",
    "Rotate crops next season and remove crop debris.",
    "Seek a local soil test before adding fertilizer.",
    "Add 2 kg of compost to the planting hole.",
    "Apply 2 cups of wood ash around each plant.",
    "Water each plant with about 5 litres when the soil is dry.",
    "Inspect the undersides of 10 leaves per plant twice a week.",
    "Check 3 plants per row every 2 days for 3 weeks.",
    "Water at 6:30 am and mix compost into the beds.",
    "Space plants 45 cm apart.",
    "About 10% of plants are affected.",
    "The affected area covers about 30% of the field.",
    "About 10% of plants show spots, so spray soapy water.",
    "Nearly 80% humidity favours the disease, so improve airflow.",
    "Dig the planting hole 30-cm deep and add 2 kg of compost.",
    "Avoid chemicals without qualified advice and a legal product label.",
    "Ask a local extension officer before choosing any chemical control.",
    "Combine hand-picking with netting. Avoid unlabelled products.",
    "Ondoa majani yaliyoathirika sana na osha mikono.",
    "Mwagilia kwenye udongo, si kwenye majani.",
    "Tumia wavu wa wadudu kulinda mimea isiyoathirika.",
    "Kagua ndani ya mikunjo ya majani na tenganisha mimea iliyoathirika sana.",
    "Usitumie kemikali bila ushauri wa mtaalamu na lebo halali.",
    "Kata majani yaliyoathirika na uyachome mbali na shamba.",
]

TEXT_SLOTS = (*GUARDED_ACTION_FIELDS, "expert_guidance")


def clean_final(language: str = "en") -> FinalAssessment:
    sw = language == "sw"
    diagnosis = _diagnosis("tomato", sw)
    return FinalAssessment(
        observation_summary=diagnosis.observation_summary,
        hypotheses=diagnosis.hypotheses,
        most_likely_explanation="Early blight is plausible.",
        overall_confidence=0.7,
        urgency="moderate",
        uncertainty_message="Not confirmed.",
        what_changed="The answer supported the leader.",
        greatest_effect="Target rings.",
        action_plan=ActionPlan(
            do_today=["Remove badly affected fallen leaves."],
            monitor=["Check whether new spots move upward."],
            avoid=["Avoid overhead watering."],
            escalate_when=["Symptoms spread to nearby plants."],
        ),
        warning_signs=["Rapid spread"],
        expert_guidance="Contact an extension officer if symptoms worsen.",
        requires_expert=False,
        sources=["Curated source"],
        limitations_notice="AI can be wrong.",
        simulated=False,
    )


def passed_verification() -> VerificationResult:
    return VerificationResult(
        passed=True,
        issues=[],
        corrected_assessment=None,
        confidence_adjustment=0,
        chemical_advice_removed=False,
    )


def with_text(final: FinalAssessment, slot: str, text: str) -> FinalAssessment:
    values = final.model_dump(mode="python")
    if slot == "expert_guidance":
        values["expert_guidance"] = text
    else:
        values["action_plan"][slot] = [*values["action_plan"][slot], text]
    return FinalAssessment.model_validate(values)


def guarded_texts(final: FinalAssessment) -> list[str]:
    plan = final.action_plan.model_dump(mode="python")
    return [text for field in GUARDED_ACTION_FIELDS for text in plan[field]] + [
        final.expert_guidance
    ]


@pytest.mark.parametrize(("instruction", "rule"), PROHIBITED_INSTRUCTIONS)
def test_prohibited_instruction_is_detected_by_the_expected_rule(
    instruction: str, rule: str
) -> None:
    assert rule in prohibited_instruction_rules(instruction)


@pytest.mark.parametrize("guidance", PERMITTED_GUIDANCE)
def test_low_risk_guidance_is_not_flagged(guidance: str) -> None:
    assert prohibited_instruction_rules(guidance) == ()


def test_lexicon_terms_are_normalized_and_individually_detected() -> None:
    lexicon = load_prohibited_terms()
    named_rules = {
        "chemical_classes": "chemical_class",
        "active_ingredients": "active_ingredient",
        "trade_names": "trade_name",
        "swahili_terms": "swahili_term",
    }
    for field, rule in named_rules.items():
        terms: list[str] = getattr(lexicon, field)
        assert len(terms) == len(set(terms)), f"{field} contains duplicates"
        for term in terms:
            assert term == term.strip().lower(), f"{field}: {term!r} must be lowercase"
            assert len(term) >= 3, f"{field}: {term!r} is too short to be unambiguous"
            assert term[0].isalnum() and term[-1].isalnum(), f"{field}: {term!r} boundaries"
            assert rule in prohibited_instruction_rules(f"Tumia {term} leo."), (field, term)
            assert rule in prohibited_instruction_rules(f"Apply {term.upper()} today."), (
                field,
                term,
            )
    for field in (
        "dose_units",
        "dose_denominators",
        "dose_separators",
        "mixture_verbs",
        "mixture_targets",
        "concentration_words",
    ):
        terms = getattr(lexicon, field)
        assert len(terms) == len(set(terms)), f"{field} contains duplicates"
        assert all(term == term.strip().lower() and term for term in terms), field
    assert all(code.isalpha() and code.isupper() for code in lexicon.formulation_codes)


def test_every_dose_unit_and_denominator_is_recognized() -> None:
    lexicon = load_prohibited_terms()
    for unit in lexicon.dose_units:
        assert "dosage" in prohibited_instruction_rules(f"Apply 5 {unit} per litre."), unit
    for denominator in lexicon.dose_denominators:
        assert "dosage" in prohibited_instruction_rules(f"Apply 5 ml per {denominator}."), (
            denominator
        )
    for separator in lexicon.dose_separators:
        assert "dosage" in prohibited_instruction_rules(f"Apply 5 ml {separator} 20 litres."), (
            separator
        )


def test_safe_replacement_text_never_triggers_the_guardrail() -> None:
    for language, replacements in SAFE_ACTION_REPLACEMENTS.items():
        for field, text in replacements.items():
            assert prohibited_instruction_rules(text) == (), (language, field)
    assert prohibited_instruction_rules(SAFE_REFERRAL) == ()
    assert prohibited_instruction_rules(SAFE_REFERRAL_SW) == ()


def test_knowledge_base_guidance_never_triggers_the_guardrail() -> None:
    entries = json.loads(KNOWLEDGE_BASE.read_text(encoding="utf-8"))
    assert entries
    for entry in entries:
        for field in (
            "low_risk_actions",
            "escalation_signs",
            "distinguishing_features",
            "visual_signs",
            "conditions",
            "distribution",
        ):
            for text in entry[field]:
                assert prohibited_instruction_rules(text) == (), (entry["problem_name"], text)


@pytest.mark.asyncio
@pytest.mark.parametrize("crop", sorted(SCENARIO_BY_CROP))
@pytest.mark.parametrize("language", ["en", "sw"])
@pytest.mark.parametrize("confirmed", [True, False])
async def test_demo_fixture_plans_pass_the_guardrail_untouched(
    crop: str, language: str, confirmed: bool
) -> None:
    provider = DemoProvider(SCENARIO_BY_CROP[crop])
    observation = _observation(crop, language == "sw")
    context: dict[str, Any] = {
        "crop": crop,
        "growth_stage": "vegetative",
        "region": "Kiambu",
        "symptom_duration": "4 days",
        "watering_conditions": "moist",
        "farmer_description": None,
    }
    evidence = evidence_for_prompt(
        retrieve_evidence(crop, observation.visible_symptoms + observation.distribution, context)
    )
    diagnosis = await provider.diagnose(
        observation=observation, context=context, evidence=evidence, language=language
    )
    answers = [
        AnswerItem(question_id=question.id, answer=confirmed)
        for question in diagnosis.follow_up_questions
    ]
    final = await provider.revise(
        initial=diagnosis.model_dump(mode="json"),
        observation=observation.model_dump(mode="json"),
        answers=answers,
        context=context,
        evidence=evidence,
        language=language,
    )
    verification = await provider.verify(
        final=final,
        observation=observation.model_dump(mode="json"),
        evidence=evidence,
        language=language,
    )
    corrected, result = finalize_verification(final, verification, language=language)
    assert result.passed is True
    assert corrected == final


@pytest.mark.parametrize(("instruction", "rule"), PROHIBITED_INSTRUCTIONS)
def test_guardrail_scrubs_every_slot_and_is_idempotent(instruction: str, rule: str) -> None:
    for language in ("en", "sw"):
        referral = SAFE_REFERRAL_SW if language == "sw" else SAFE_REFERRAL
        for slot in TEXT_SLOTS:
            proposed = with_text(clean_final(language), slot, instruction)
            corrected, removed, issues = apply_action_guardrails(proposed, language=language)
            assert removed is True, (language, slot)
            assert issues, (language, slot)
            assert instruction not in guarded_texts(corrected), (language, slot)
            assert all(prohibited_instruction_rules(t) == () for t in guarded_texts(corrected))
            assert referral in corrected.action_plan.do_today, (language, slot)
            again, removed_again, issues_again = apply_action_guardrails(
                corrected, language=language
            )
            assert removed_again is False, (language, slot)
            assert issues_again == []
            assert again == corrected


@pytest.mark.parametrize("guidance", PERMITTED_GUIDANCE)
def test_permitted_guidance_survives_finalization_unchanged(guidance: str) -> None:
    for slot in TEXT_SLOTS:
        proposed = with_text(clean_final(), slot, guidance)
        corrected, result = finalize_verification(proposed, passed_verification())
        assert corrected == proposed, slot
        assert result.passed is True, slot


def test_randomly_composed_dose_instructions_are_always_detected() -> None:
    lexicon = load_prohibited_terms()
    rng = random.Random(20260920)
    templates = [
        "Spray {dose} of water.",
        "Apply {dose} every week.",
        "Dissolve {dose} and drench the soil.",
        "Use {dose}.",
        "Changanya {dose} za maji.",
        "Tumia {dose} kila wiki.",
        "Weka {dose}.",
    ]
    substances = ["", " of the product", " of soap", " ya dawa", " cha unga", " of it"]
    articles = ["", " each", " every", " kila", " a", " an", " one", " the"]

    def number() -> str:
        if rng.random() < 0.3:
            return f"{rng.randint(0, 9)}{rng.choice(['.', ','])}{rng.randint(1, 9)}"
        return str(rng.randint(1, 500))

    def quantity() -> str:
        unit = rng.choice(lexicon.dose_units)
        return f"{number()} {unit}" if rng.random() < 0.7 else f"{unit} {number()}"

    def denominator() -> str:
        unit = rng.choice(lexicon.dose_denominators)
        roll = rng.random()
        if roll < 0.4:
            return f"{number()} {unit}"
        if roll < 0.6:
            return f"{unit} {number()}"
        return unit

    for _ in range(300):
        separator = rng.choice(lexicon.dose_separators)
        joiner = "" if separator == "/" and rng.random() < 0.5 else " "
        dose = (
            f"{quantity()}{rng.choice(substances)}{joiner}{separator}"
            f"{rng.choice(articles)}{joiner}{denominator()}"
        )
        instruction = rng.choice(templates).format(dose=dose)
        assert "dosage" in prohibited_instruction_rules(instruction), instruction
