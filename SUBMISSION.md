# ShambaLens AI — Submission Draft

This document is ready to adapt to a submission form. Replace bracketed media and measured-result fields only after capturing them from the running application; do not invent performance or field-impact numbers.

## Project title

ShambaLens AI

## Tagline

Evidence-first crop triage: from uncertain photos to targeted questions and a verified, safer plan.

## Short description

ShambaLens helps tomato, onion, and kale farmers turn crop photos and field context into a transparent differential assessment. It checks image quality, shows evidence for and against several causes, asks targeted follow-up questions, revises its ranking, and independently verifies a low-risk action plan.

## Long description

Smallholder farmers often face a bad choice: wait for scarce expert help or trust an image application that returns one confident disease label. Crop symptoms are rarely that simple. Fungal disease, nutrient stress, pests, heat, and watering problems can look similar in a single photograph, while the most useful distinction may depend on where symptoms began or what happened in the field.

ShambaLens AI treats the interaction as triage rather than classification. A farmer uploads up to three crop images and a small amount of context. The application first checks whether a plant and the affected area are visible and asks for a better photo when needed. For usable images, it records strictly observable symptoms, retrieves relevant crop evidence, and produces one to three hypotheses with supporting, contradicting, and missing evidence. It then asks no more than three questions chosen to separate the leading possibilities.

After the farmer answers, ShambaLens reranks the possibilities and explains what changed. A separate verifier checks whether the result is grounded, confidence is proportionate, contradictions are represented, and actions are safe. Deterministic guardrails prohibit chemical dosages, mixtures, and restricted-product instructions. The final report groups guidance into **Do today**, **Monitor**, **Avoid**, and **Escalate when**, and can be printed or copied in English or Swahili.

Reports remain scoped to an anonymous browser token. Only coarse completed-report aggregates can appear on the community dashboard, which is clearly labelled as unconfirmed AI signals rather than outbreak data.

## Problem statement

- Visual crop symptoms overlap, but conventional classifiers often hide ambiguity behind one label.
- Agronomists and extension officers cannot inspect every field immediately.
- A wrong confident label can waste money, delay escalation, or encourage unsafe treatment.
- Farmer observations—symptom distribution, watering, spread to nearby plants—are valuable evidence that image-only tools often ignore.
- Regional stakeholders need earlier situational awareness without exposing individual farmer records.

## Solution and core innovation

ShambaLens makes uncertainty actionable through a staged evidence loop:

1. **Quality gate:** reject unusable or irrelevant images before expensive reasoning.
2. **Observable evidence:** separate what the vision model can see from what a reasoner may infer.
3. **Differential assessment:** rank several plausible causes with evidence for, against, and missing.
4. **Adaptive questioning:** ask at most three questions that distinguish named leaders.
5. **Confidence revision:** incorporate field answers and explain the most influential change.
6. **Independent verification:** run a separate grounding, calibration, clarity, and safety check.
7. **Deterministic safety:** enforce chemical-advice policy after model verification.
8. **Privacy-conscious signals:** aggregate completed reports without exposing individual images or records.

This is not a generic chatbot wrapped around an upload. Each stage has a strict schema, a bounded responsibility, tests, persistence, and a visible effect on the farmer journey.

## Technical implementation

### Frontend

- Next.js App Router, TypeScript, and Tailwind CSS
- mobile-first assessment wizard with camera-friendly upload and previews
- accessible question controls, retake state, differential cards, uncertainty and action sections
- English/Swahili interface dictionary
- printable report, copied summary, previous reports, dashboard, and safety page
- browser-held opaque token for report ownership without mandatory signup

### Backend

- FastAPI and Pydantic for a versioned, strictly validated API
- SQLAlchemy async persistence and Alembic migrations
- defensive image decode, byte/pixel/blur/lighting checks, metadata removal, and private generated paths
- provider-independent observation, reasoning, revision, and verification services
- cited local crop knowledge base and deterministic retrieval
- standardized safe errors, structured logs, timeouts, one bounded JSON repair, and measured stage latency
- deterministic demo fixtures that exercise the normal schemas and persistence path

### AI pipeline

- `qwen/qwen3.8-27b` receives normalized images and returns observable plant/image evidence.
- `openai/gpt-oss-120b` receives text observations, farmer context, and retrieved evidence for the initial differential and targeted questions.
- The same text model runs a new revision after answers and a separate verifier call with a different responsibility and output contract.
- GPT-OSS is never represented as seeing the images.
- Pydantic invariants constrain confidence, one-to-three hypotheses, no more than three questions, complete uncertainty fields, and safe action-plan structure.
- Deterministic policy code is the final authority on prohibited chemical instructions.

### Data layer

- Neon PostgreSQL stores assessment state, structured results, answers, verifier outcome, anonymous token hash, model provenance, and timing metadata.
- Runtime traffic uses Neon's pooled URL; Alembic uses the direct URL.
- Sanitized images stay on a private Docker volume for the prototype and are served through an ownership-checked route.
- A Compose profile provides disposable local PostgreSQL for tests and credit-free demos.

## Meaningful use of Groq

Groq is the live inference plane across three materially different stages, not a branding panel:

1. multimodal observation converts crop images into constrained visible evidence;
2. text reasoning turns observations, context, and retrieved sources into a differential and discriminating questions;
3. revision and a separate verification call update and audit the final plan.

The runtime panel reports the configured model IDs, explicit demo/live mode, and measured stage latencies. Live inference errors remain live errors; the application cannot silently substitute demo fixtures.

## Meaningful use of Neon

Neon is the state backbone that makes the interaction more than a one-shot prompt. It preserves the assessment between upload, questions, revision, verification, report reopening, and privacy-filtered dashboard aggregation. Pooling supports normal API traffic while a direct connection keeps migrations predictable. The data model stores validated domain results rather than unnecessary raw provider responses.

## Safety and trust design

- The product says **triage**, **possible cause**, and **uncertainty** rather than definitive diagnosis.
- Poor images short-circuit to concrete retake guidance.
- Every hypothesis exposes supporting, contradicting, and missing evidence.
- Confidence is bounded and may be lowered by input quality or verification.
- Chemical doses, mixtures, and restricted-product instructions are prohibited.
- Potential chemical control is redirected to a qualified local professional, the product label, and local regulations.
- Severe, spreading, or ambiguous cases carry clear escalation signs.
- Provider reasoning traces, secrets, raw image paths, and farmer notes are excluded from public outputs and logs.

## Product and market opportunity

### Initial user

Smallholder tomato, onion, and kale farmers who have a smartphone but cannot get immediate field inspection.

### Distribution partners

- cooperatives and farmer groups;
- agronomists and extension programs;
- responsible agrovets that need a structured intake before advice;
- insurers and lenders supporting crop-risk programs;
- county agriculture teams monitoring opt-in, aggregated signals.

### Product path

The farmer triage experience can remain a low-friction entry point. Sustainable offerings can add reviewed cooperative workflows, agronomist escalation queues, organization dashboards, localized evidence packs, and opt-in seasonal analytics. Any outbreak or treatment decision remains human-confirmed.

### Defensibility

The durable asset is not a single model call. It is the reviewed crop evidence, adaptive evidence protocol, agronomist feedback loop, multilingual field UX, calibration dataset, and privacy-preserving longitudinal signals.

## Current limitations

- The knowledge base supports only tomato, onion, and kale/sukuma wiki and is not exhaustive.
- Similar visual symptoms still require field or laboratory confirmation.
- Advice has not yet been validated across all local varieties, seasons, counties, and production systems.
- The configured Qwen vision model may have preview or account-specific access.
- English and Swahili phrasing need structured farmer usability studies.
- Anonymous browser ownership does not synchronize or recover reports across devices.
- Firebase image storage is horizontally accessible, but anonymous identities still lack multi-device recovery and organizational access controls.
- Community summaries are model-generated signals, not verified outbreak surveillance.
- No measured field-accuracy, calibration, or economic-impact claim should be made until an agronomist-reviewed evaluation is complete.

## Roadmap

### Next

- conduct farmer and extension-officer usability sessions in English and Swahili;
- build an agronomist-reviewed evaluation set and publish calibration by crop/problem category;
- version and expand the evidence corpus with regional sources;
- add authenticated cooperative workspaces, recoverable farmer accounts, and expert handoff;
- add offline draft capture for weak-connectivity environments.

### Later

- incorporate weather and season signals only with explicit provenance and consent;
- add more crops based on partner demand and reviewed evidence availability;
- introduce human-confirmed regional alerts with minimum aggregation thresholds;
- evaluate sustainable cooperative and extension-program pricing.

## Suggested technology tags

`AI for Agriculture` · `Multimodal AI` · `Groq` · `GPT-OSS` · `Qwen` · `Neon` · `PostgreSQL` · `FastAPI` · `Next.js` · `TypeScript` · `Tailwind CSS` · `Pydantic` · `Docker` · `English/Swahili` · `Responsible AI`

## Three-minute demo script

### 0:00–0:25 — The problem

**Show:** landing page.

**Say:** “A farmer with leaf damage may get no timely help—or one confident label from an image classifier. But a brown spot could reflect disease, nutrient stress, pests, or water conditions. ShambaLens treats that uncertainty as evidence to investigate, not something to hide.”

**Action:** select **Check a crop**.

### 0:25–0:50 — Upload and context

**Show:** tomato demo scenario, image preview, and compact context form.

**Say:** “I add up to three photos, select tomato and its growth stage, then add only the context I know. Before diagnosis, the service checks whether the plant and affected area are visible, plus blur and lighting. An unusable photo stops here with a precise retake instruction.”

**Action:** submit the demo assessment and point to the quality result.

### 0:50–1:15 — Differential, not a verdict

**Show:** three ranked possibilities.

**Say:** “Instead of one label, ShambaLens separates visible observations from inference, retrieves crop evidence, and ranks several possibilities. Each card shows what supports it, what contradicts it, and what is still missing. The confidence label stays tied to evidence quality.”

**Action:** expand two hypotheses and highlight contradictory evidence.

### 1:15–1:40 — Adaptive questions

**Show:** two or three accessible answer controls.

**Say:** “These are not a generic questionnaire. Each question distinguishes named leaders—for example, whether symptoms began on lower leaves or whether spots show rings.”

**Action:** answer the questions and continue.

### 1:40–2:10 — Revision and verified plan

**Show:** updated ranking, change explanation, verifier status, and four action sections.

**Say:** “The answers trigger a fresh revision. The report explains what changed and which answer mattered most. Then a separate model call checks grounding, confidence, contradiction, clarity, and safety. Code-level guardrails run last. The result prioritizes low-risk steps for today, what to monitor, what to avoid, and when to seek expert help.”

**Action:** point to uncertainty and escalation; switch briefly to Swahili or open print view.

### 2:10–2:35 — Honest provenance

**Show:** runtime/provenance panel.

**Say:** “The image observation came from the configured Qwen vision model. GPT-OSS received only validated text observations for triage, revision, and a separate verification call. The panel shows explicit demo or live mode, the real model IDs, and measured stage latencies—never fabricated infrastructure details.”

**Action:** show the simulated marker in demo mode and the runtime endpoint or panel.

### 2:35–3:00 — Opportunity

**Show:** previous reports, then community signals.

**Say:** “The report can be reopened, copied, or printed. Only coarse completed-report counts reach this dashboard, which is explicitly not confirmed outbreak data. With human confirmation, this workflow can help farmers, cooperatives, extension teams, and insurers move from a risky photo label to earlier, better-structured action.”

**Close:** “ShambaLens does not pretend uncertainty is gone. It helps the farmer ask the next best question.”

## Suggested slide outline

1. **One photo is not one answer** — overlapping symptoms and the cost of false certainty.
2. **Meet ShambaLens AI** — one-sentence pitch and target crops/users.
3. **The evidence loop** — quality → observation → differential → questions → revision → verification.
4. **Live product journey** — four screenshots from the demo.
5. **Trust by construction** — visible contradiction, strict schemas, independent verification, deterministic safety.
6. **Technical architecture** — Next.js, FastAPI, Qwen/GPT-OSS on Groq, Neon, local cited evidence.
7. **Privacy-conscious regional value** — report ownership and coarse community signals.
8. **Market wedge and distribution** — farmer entry point plus cooperative/extension workflows.
9. **Evidence, not hype** — measured benchmark and test results after running them.
10. **Roadmap and ask** — field evaluation partners, agronomist reviewers, and pilot communities.

## Submission asset checklist

- [ ] Public repository and clear MIT license
- [ ] 60–90 second overview video and full three-minute demo
- [ ] Landing, quality gate, differential, verified plan, provenance, and dashboard screenshots
- [ ] Architecture diagram exported from the Mermaid source
- [ ] Demo credentials/instructions that require no paid inference
- [ ] Live model and database configuration instructions
- [ ] Actual verification command results, with date and environment
- [ ] Actual benchmark JSON/Markdown, clearly marked demo or live
- [ ] Safety disclaimer visible in screenshots and video
- [ ] No `.env`, API key, database credential, ownership token, or farmer data in any asset

## Results to insert only after measurement

| Item | Value | Evidence |
| --- | --- | --- |
| Backend tests | `[run and insert]` | CI link or terminal capture |
| Frontend tests | `[run and insert]` | CI link or terminal capture |
| Production builds | `[run and insert]` | CI link or terminal capture |
| Demo E2E flow | `[run and insert]` | Playwright report/video |
| Live structured-output success | `[benchmark and insert]` | benchmark artifact |
| Live median/P95 latency | `[benchmark and insert]` | benchmark artifact |
| Verification correction rate | `[benchmark and insert]` | benchmark artifact |
| Agronomist-reviewed accuracy/calibration | `Not yet established` | future evaluation |
