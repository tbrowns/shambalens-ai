# ShambaLens AI

**Evidence-first crop triage that turns crop photos, farm context, and targeted follow-up answers into a cautious, verified action plan.**

ShambaLens AI is a mobile-first advisory tool for tomato, onion, and kale (sukuma wiki) growers. It does not jump from one photo to a definitive label. It first checks whether the images are useful, records only visible observations, compares several plausible causes, asks up to three questions that can separate those causes, and verifies the revised plan before presenting it.

> ShambaLens is an advisory triage tool, not a definitive diagnosis or a replacement for a qualified agronomist. Urgent, spreading, severe, or uncertain cases should be escalated locally.

## Why this workflow matters

Single-label classifiers can hide uncertainty and encourage premature treatment. ShambaLens makes the uncertainty useful:

- every report ranks one to three hypotheses instead of forcing one label;
- supporting, contradicting, and missing evidence remain visible;
- follow-up questions are chosen for their ability to distinguish the leaders;
- the ranking is revised after the farmer answers;
- a separate verification pass checks evidence, calibration, clarity, and safety;
- deterministic guardrails remove prohibited chemical instructions even if a model generates them;
- completed reports contribute only coarse, anonymous community signals.

## Product tour

| Screen | What it demonstrates |
| --- | --- |
| Landing page | Supported crops, the evidence-first promise, and a clear **Check a crop** action |
| Assessment wizard | Mobile image upload, crop context, quality feedback, and retake guidance |
| Adaptive questions | No more than three questions tied to the leading possibilities |
| Verified report | Revised differential, uncertainty, safe actions, sources, print, and copy controls |
| Previous reports | Reports scoped to this browser's anonymous ownership token |
| Community signals | Coarse crop/category/region summaries, explicitly marked as unconfirmed signals |

Capture these six views after starting demo mode for submission screenshots; the application itself contains the complete interactive views.

## Architecture

```mermaid
flowchart LR
    Farmer["Farmer browser"] --> Web["Next.js web app"]
    Web -->|"Anonymous auth + direct upload"| Files[("Private Firebase Storage")]
    Web -->|"Versioned JSON + object paths"| API["FastAPI service"]
    API -->|"Verify identity, read and sanitize"| Files
    API --> Gate["Signature, size, pixel, blur and lighting gate"]
    Gate -->|"usable images"| Vision["Qwen vision observation"]
    Gate -->|"retake required"| Web
    Vision --> Obs["Validated visible observations"]
    Obs --> Retrieve["Local cited crop evidence retrieval"]
    Retrieve --> Reason["GPT-OSS triage and question selection"]
    Reason -->|"farmer answers"| Revise["GPT-OSS assessment revision"]
    Revise --> Verify["Independent GPT-OSS verification"]
    Verify --> Guard["Deterministic safety guardrails"]
    Guard --> API
    API --> DB[("Neon PostgreSQL")]
```

The vision model receives normalized crop images. GPT-OSS is text-only: it receives validated observations, farmer context, answers, and retrieved knowledge—not the images—and the UI never claims otherwise. The AI provider is behind an application interface so the configured implementation can be replaced without changing the API or persistence layer.

See [ARCHITECTURE.md](ARCHITECTURE.md) for trust boundaries and the complete data flow.

## Repository layout

```text
.
├── frontend/              # Next.js, TypeScript, Tailwind, UI and browser tests
├── backend/               # FastAPI, Pydantic, SQLAlchemy, Alembic and tests
│   ├── app/agents/        # Provider-independent pipeline stages
│   ├── app/knowledge/     # Maintainable crop evidence and the prohibited-terms lexicon
│   └── data/uploads/      # Runtime-only files; ignored by Git
├── scripts/               # Verification and benchmark entry points
├── docker-compose.yml
├── .env.example
├── ARCHITECTURE.md
└── SUBMISSION.md
```

## Prerequisites

Docker Desktop with Compose v2.20 or newer is sufficient to run the product. Live mode additionally needs:

- a Neon project with pooled and direct PostgreSQL connection strings; and
- a Groq project API key with access to the configured vision, reasoning, and verifier models.

No database-management API key is used by the application. No API key belongs in the frontend.

## Fastest start: deterministic demo

Demo mode performs no Groq calls and includes deterministic tomato leaf spot, onion discoloration, and kale pest-damage scenarios.

```bash
cp .env.example .env
docker compose --profile local up --build
```

On PowerShell, use `Copy-Item .env.example .env` for the first command. Leave `DATABASE_URL`, `DATABASE_URL_UNPOOLED`, and `GROQ_API_KEY` blank; keep `DEMO_MODE=true`. The `local` profile starts PostgreSQL, and Compose fills both database URLs with the container connection.

Open:

- web application: <http://localhost:3000>
- backend API: <http://localhost:8000>
- interactive API docs: <http://localhost:8000/docs>
- health check: <http://localhost:8000/health>

Demo results carry a visible **Simulated demo** marker. Live errors never silently fall back to fixtures.

Stop the stack with `docker compose --profile local down`. Add `--volumes` only when you intentionally want to erase local reports and uploads.

## Configure live inference and Neon

### 1. Create the Neon database

1. Sign in to the [Neon Console](https://console.neon.tech), create or select a project, and open **Connect**.
2. Select the application database and role.
3. Enable the pooled connection and copy that PostgreSQL URL to `DATABASE_URL`.
4. Switch to the direct/unpooled connection and copy that URL to `DATABASE_URL_UNPOOLED`.
5. Preserve the TLS parameters supplied by Neon, including `sslmode=require` and `channel_binding=require` when present.

The pooled URL serves normal application traffic. The direct URL is used by Alembic so schema migrations are not routed through transaction pooling.

### 2. Create the Groq key

1. Create or select a project in the [Groq Console](https://console.groq.com).
2. Confirm that the project can use `qwen/qwen3.6-27b` and `openai/gpt-oss-120b`. Model availability can vary by account and preview status.
3. Open [API Keys](https://console.groq.com/keys), create a key named `shambalens-local`, and copy it when shown.
4. Put the value only in the root `.env` as `GROQ_API_KEY`. One project key covers the configured models.

The defaults deliberately remain configurable. If Groq changes a preview model identifier, update the corresponding environment variable only after confirming equivalent image-input support.

### 3. Fill `.env`

```dotenv
DATABASE_URL="postgresql://USER:PASSWORD@POOLED-HOST/DATABASE?sslmode=require&channel_binding=require"
DATABASE_URL_UNPOOLED="postgresql://USER:PASSWORD@DIRECT-HOST/DATABASE?sslmode=require&channel_binding=require"

GROQ_API_KEY="gsk_..."
GROQ_BASE_URL="https://api.groq.com/openai/v1"
GROQ_VISION_MODEL="qwen/qwen3.6-27b"
GROQ_REASONING_MODEL="openai/gpt-oss-120b"
GROQ_VERIFIER_MODEL="openai/gpt-oss-120b"

AI_PROVIDER="groq"
DEMO_MODE="false"
MAX_UPLOAD_MB="8"
ALLOWED_ORIGINS="http://localhost:3000"
ANONYMOUS_TOKEN_SALT="replace-with-a-long-random-value"
NEXT_PUBLIC_API_BASE_URL="http://localhost:8000"
```

Do not paste real secrets into issues, logs, screenshots, chat, or committed files. `.env` and its variants are ignored; `.env.example` is the only exception.

Generate a local salt on PowerShell with:

```powershell
$bytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
[Convert]::ToBase64String($bytes)
```

### 4. Start live mode

```bash
docker compose up --build
```

Do not enable the `local` profile when the Neon URLs are set. Inspect the non-sensitive effective runtime at <http://localhost:8000/api/v1/system/runtime>; it reports configured model identifiers, demo/live mode, and measured stage latencies without returning credentials.

### 5. Configure private Firebase image storage for Vercel

The browser can upload images directly to the `shamba-ai-fe407` Firebase Storage bucket so
large multipart requests never pass through a Vercel Function. The API accepts only Firebase
object paths owned by the signed-in anonymous Firebase user, downloads the object with Firebase
Admin, validates and re-encodes it, stores the sanitized copy under an assessment-specific path,
and deletes the temporary original.

1. Upgrade the Firebase project to Blaze and enable **Authentication > Anonymous**.
2. Create a service account with access to the Storage bucket. Put the complete JSON value in
   the backend-only `FIREBASE_SERVICE_ACCOUNT_JSON` deployment secret; never expose it through a
   `NEXT_PUBLIC_` variable.
3. Deploy the deny-by-default rules with `firebase deploy --only storage` from the repository root.
4. Set `IMAGE_STORAGE=firebase`, `FIREBASE_PROJECT_ID=shamba-ai-fe407`, and
   `FIREBASE_STORAGE_BUCKET=shamba-ai-fe407.firebasestorage.app` on the backend.
5. Set `NEXT_PUBLIC_API_BASE_URL` to the deployed API. The Firebase web identifiers are already
   represented in the frontend and may be overridden with the corresponding `NEXT_PUBLIC_`
   variables from `.env.example`.
6. For App Check, create a reCAPTCHA Enterprise web key, set
   `NEXT_PUBLIC_FIREBASE_APP_CHECK_SITE_KEY`, verify production traffic, and only then enable
   Storage enforcement in the Firebase console.

Use `backend` as the Vercel project root. The FastAPI entrypoint and a 300-second Function duration
are declared in `backend/pyproject.toml` and `backend/vercel.json`. Run `alembic upgrade head`
against the Neon direct URL as a separate release step before deploying application code.

## Environment reference

| Variable | Required | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | Live | Neon pooled PostgreSQL URL used at runtime |
| `DATABASE_URL_UNPOOLED` | Live | Neon direct PostgreSQL URL used for Alembic migrations |
| `GROQ_API_KEY` | Live | Backend-only Groq project key |
| `GROQ_BASE_URL` | No | OpenAI-compatible Groq endpoint |
| `GROQ_VISION_MODEL` | No | Image observation model; defaults to Qwen 3.6 27B |
| `GROQ_REASONING_MODEL` | No | Text-only triage and revision model |
| `GROQ_VERIFIER_MODEL` | No | Text-only model used in a separate verification call |
| `AI_PROVIDER` | No | Provider implementation selector; currently `groq` |
| `DEMO_MODE` | No | Uses deterministic fixtures only when explicitly `true` |
| `MAX_UPLOAD_MB` | No | Per-image upload ceiling, 8 MB by default |
| `MAX_IMAGE_PIXELS` | No | Decompression-safety pixel ceiling |
| `MODEL_TIMEOUT_SECONDS` | No | Per-provider-request timeout |
| `ALLOWED_ORIGINS` | No | Comma-separated browser origins allowed by the API |
| `UPLOAD_DIR` | No | Private backend image directory |
| `IMAGE_STORAGE` | No | `local` for development or `firebase` for direct cloud uploads |
| `FIREBASE_PROJECT_ID` | Firebase | Firebase project used for ID-token verification |
| `FIREBASE_STORAGE_BUCKET` | Firebase | Private Cloud Storage bucket name |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Firebase | Backend-only Firebase Admin service-account JSON |
| `ANONYMOUS_TOKEN_SALT` | Deployment | Server-side salt for hashing browser ownership tokens |
| `NEXT_PUBLIC_API_BASE_URL` | Yes | Public browser-facing API URL, set at frontend build time |
| `NEXT_PUBLIC_FIREBASE_*` | No | Public Firebase web identifiers; defaults target `shamba-ai-fe407` |
| `NEXT_PUBLIC_FIREBASE_APP_CHECK_SITE_KEY` | Recommended | Public reCAPTCHA Enterprise site key for App Check |

## Assessment pipeline

1. The browser uploads one to three JPEG, PNG, or WebP files directly to a UID-scoped Firebase path; local development can continue using multipart uploads.
2. The API verifies the Firebase ID token and object ownership, then validates file signatures, size, dimensions, decompression limits, lighting, and blur. It re-encodes sanitized JPEGs under generated assessment paths with metadata removed.
3. Qwen returns plant visibility, crop relevance, affected-area visibility, image quality, and strictly observable symptoms as validated JSON. A malformed response receives one bounded repair attempt.
4. A **retake required** result stops before the more expensive reasoning stage and gives precise capture guidance.
5. The retrieval service selects relevant, cited evidence for tomato, onion, or kale from the local knowledge base.
6. GPT-OSS receives normalized observations and text context, then returns one to three hypotheses and at most three discriminating questions using a strict, closed JSON schema.
7. Farmer answers trigger a fresh revision call. A separate verifier call checks grounding, contradictions, confidence, urgency, safety, and readable language.
8. Deterministic chemical-advice guardrails run after verification, and only the validated result is persisted and returned.

The provider's hidden reasoning is never requested for display, stored, or exposed. User-facing explanations summarize evidence and changes without revealing private reasoning traces.

## API overview

The backend exposes versioned endpoints for the application flow:

```text
GET    /health
GET    /api/v1/system/runtime
POST   /api/v1/assessments
POST   /api/v1/assessments/from-storage
POST   /api/v1/assessments/{id}/analyze
POST   /api/v1/assessments/{id}/answers
GET    /api/v1/assessments/{id}
GET    /api/v1/assessments
GET    /api/v1/assessments/{id}/images/{image_id}
GET    /api/v1/dashboard/summary
POST   /api/v1/demo/reset
```

Local assessment creation uses multipart form data. Firebase assessment creation uses a JSON object-path contract and additionally requires a Firebase bearer token. Protected assessment and image routes require the opaque browser ownership token established by the client. Errors use one envelope:

```json
{
  "error": {
    "code": "stable_machine_code",
    "message": "Safe user-facing explanation",
    "retryable": false,
    "request_id": "correlation-id"
  }
}
```

## Safety, privacy, and uncertainty

- Reports use confidence bands and evidence lists; they do not claim definitive diagnosis.
- Chemical dosages, mixtures, and restricted-product instructions are prohibited. When chemical control may be appropriate, the report directs the farmer to a qualified local professional, the product label, and local regulations.
- The deterministic guardrail that enforces this is driven by a reviewable lexicon, [`backend/app/knowledge/prohibited_terms.json`](backend/app/knowledge/prohibited_terms.json): product classes, about a hundred active ingredients, common East African trade names, and Swahili terms, plus grammar for doses in either word order (`50 g per 20 litres`, `gramu 50 kwa lita 20`), dilution ratios (`1:100`, `one part to ten parts`), percentage concentrations, formulation codes such as `5 EC`, and mixing instructions. Tests assert that a corpus of prohibited instructions is removed from every action section, that low-risk advice, the knowledge base, the demo plans, and the guardrail's own replacement text are never flagged, and that a second pass changes nothing.
- Low-risk integrated pest-management steps are prioritized, with explicit **Do today**, **Monitor**, **Avoid**, and **Escalate when** sections.
- Exact location, names, ownership tokens, and images are excluded from community analytics. Dashboard results are labelled **Community-reported AI signals, not confirmed outbreak data**.
- Original filenames and client URLs are not trusted. Firebase object paths are UID-scoped and validated, images are decoded and normalized by the backend, and sanitized objects are retrieved only through an ownership-checked API route.
- Browser ownership is anonymous and convenient, not full account authentication. Production deployments that require multi-device identity should add an authentication service.

More detail is in [ARCHITECTURE.md](ARCHITECTURE.md).

## Development and verification

For a local toolchain, use Python 3.11+ and a current Node.js LTS release.

```bash
# Backend
cd backend
python -m venv .venv
# Activate .venv for your shell, then:
python -m pip install -e ".[dev]"
python -m ruff check .
python -m mypy app
python -m pytest

# Frontend
cd ../frontend
npm ci
npm run lint
npm run typecheck
npm run test
npm run build

# Compose validation, from the repository root
docker compose config --quiet
```

The repository also provides `scripts/verify.ps1` for PowerShell and `scripts/verify.sh` for POSIX shells. Tests mock Groq calls; they do not consume API credits.

To extend the chemical guardrail, add the term to the matching list in `backend/app/knowledge/prohibited_terms.json` and a phrase that uses it to `PROHIBITED_INSTRUCTIONS` in `backend/tests/test_safety_lexicon.py`; if new low-risk wording must survive, add it to `PERMITTED_GUIDANCE`. The lexicon tests also check that every term is lowercase, unambiguous, and individually detected, and that no term flags the knowledge base or the guardrail's replacement text.

The Playwright flow intercepts API calls with deterministic contract fixtures and runs against the built standalone frontend:

```bash
cd frontend
npm run build
npx playwright install chromium
npm run test:e2e -- --project=chromium
```

Use `docker compose --profile local up --build -d` separately for a full demo-stack smoke test, then check the frontend and `/health` endpoints.

PostgreSQL integration tests should point to a disposable database, never the production Neon branch. A live smoke call is intentionally separate and should run only when an authorized key and expendable database branch are explicitly configured.

## Benchmarking

The benchmark runner exercises sample assessments and records actual request results rather than fixed numbers:

```bash
python backend/scripts/benchmark.py --scenario all --output benchmark-results.json
```

Run it once with `DEMO_MODE=true` to verify orchestration and once with `DEMO_MODE=false` for real provider latency. Results include count, mean/median/P95 latency, structured-output success rate, verification correction rate, configured models, and execution mode. Generated result files are ignored by Git; disclose the environment and mode whenever publishing numbers.

## Deployment guidance

Deploy the frontend and backend as separate Vercel projects (or use the Dockerfiles on a container platform), then configure:

1. `NEXT_PUBLIC_API_BASE_URL` as the public HTTPS backend URL **during the frontend image build**.
2. Use `backend` as the FastAPI project root. Neon pooled/direct URLs, Groq credentials, and Firebase Admin JSON belong in the backend secret manager.
3. `ALLOWED_ORIGINS` as the exact public frontend origin and `ENVIRONMENT=production`.
4. A fresh, stable `ANONYMOUS_TOKEN_SALT`; rotating it invalidates existing anonymous ownership tokens.
5. `IMAGE_STORAGE=firebase`, the Firebase project/bucket identifiers, Anonymous Authentication, the repository Storage Rules, and optionally App Check.
6. Run `alembic upgrade head` against the Neon direct URL as a separate release step.
7. Configure HTTPS, log retention, backups, spend alerts, and rate limiting at the platform edge.

The backend container applies Alembic migrations before serving; Vercel does not, which is why migrations are a separate release action there. Neon and Firebase remain external in live deployments. The Compose `local` database profile and filesystem image adapter remain available for development, tests, and demonstrations.

## Supported crops and limitations

Current crop evidence covers tomato, onion, and kale/sukuma wiki, including representative fungal, bacterial, viral, pest, nutrient, watering, heat, and transplant problems. It is deliberately not exhaustive.

Other limitations:

- image-only signs can overlap; laboratory or field inspection may still be necessary;
- poor images, unseen leaf surfaces, and missing farm history constrain confidence;
- advice must be interpreted for local weather, varieties, regulations, and extension guidance;
- the default Qwen vision model may have preview or account-specific availability;
- translations prioritize accessible English and Swahili but still require field evaluation with farmers;
- community charts show coarse model signals, not confirmed incidence or outbreak declarations;
- browser-token ownership does not provide accounts, synchronization, or recovery across devices;
- Firebase anonymous identities and opaque report tokens do not provide multi-device account recovery.

## Roadmap

- field-test Swahili phrasing and capture guidance with farmers and extension officers;
- expand reviewed crop evidence and add provenance/versioning for every entry;
- add authenticated cooperative workspaces and recoverable farmer accounts;
- support offline draft capture and delayed upload on unreliable connections;
- calibrate confidence against agronomist-reviewed cases and publish evaluation results;
- add opt-in alerts only after regional signals have a human confirmation workflow.

## Submission material

See [SUBMISSION.md](SUBMISSION.md) for a ready-to-edit description, technology tags, slide outline, limitations, and a timed three-minute demo script.

## License

ShambaLens AI is available under the [MIT License](LICENSE).
