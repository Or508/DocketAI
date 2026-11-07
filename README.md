# DocketAI

**Audit-ready document onboarding, classification, and electronic signing, with first-class Hebrew and RTL support.**

DocketAI takes a bundle of PDFs and scans, classifies each file against a process checklist, shows exactly what is missing, collects the remaining details through a validated conversational clerk, and produces a flattened, signed PDF packet with a Certificate of Completion.

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Next.js 15](https://img.shields.io/badge/Next.js-15-000000?logo=nextdotjs&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-strict-3178C6?logo=typescript&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![Pytest](https://img.shields.io/badge/pytest-98%20passing-0A9EDC?logo=pytest&logoColor=white)

> **Project status:** DocketAI is a working portfolio system, not a hosted product. Office routes require a staff login. The API stays private behind the Next.js proxies. See [Known limitations](#known-limitations-and-roadmap).

## Contents

- [How it works](#how-it-works)
- [System architecture](#system-architecture)
- [Engineering highlights](#engineering-highlights)
- [Repository structure](#repository-structure)
- [Getting started](#getting-started)
- [Testing and quality](#testing-and-quality)
- [Known limitations and roadmap](#known-limitations-and-roadmap)

## How it works

1. **Ingest.** The office opens a case for a process, such as employee onboarding, and uploads a bundle. File types are checked by content, not just by extension.
2. **Classify.** PyMuPDF extracts text. Sparse pages are rendered and sent to Gemini with a structured schema. Labels confirmed by a person can be embedded in Qdrant and reused as few-shot examples.
3. **Find the gaps.** A low-confidence suggestion never satisfies a requirement. Those files wait for a person to review them.
4. **Collect.** A clerk gathers missing details and checks each one with deterministic validators, including the Israeli ID checksum. The model can rephrase a reply, but it cannot decide what gets recorded.
5. **Sign.** The office signs in the workspace, or sends a signer a single-purpose link. The signer reviews a draft of the filled form before signing.
6. **Finish.** The form is flattened, a Certificate of Completion is appended, and every page is numbered. Both the form content and the final file are hashed, and the event is written to the audit log.

Gemini and Qdrant are optional. Without a key, every file waits for a human label and the clerk fills one field per message.

## System architecture

DocketAI is a monorepo with a Python API, a Next.js app, and a shared contract package.

```mermaid
flowchart LR
    Office["Office browser"] --> Web["Next.js app"]
    Signer["Signer browser"] -->|"/sign/token"| Web
    Web -->|"Office proxy"| API["FastAPI API"]
    Web -->|"Allowlisted /portal proxy"| API
    API --> DB[("PostgreSQL or SQLite")]
    API --> Files[("Object storage")]
    API -->|"Enqueue job"| Redis[("Redis")]
    Redis --> Worker["ARQ worker"]
    Worker --> DB
    Worker --> Files
    API -.->|"Optional"| Gemini["Gemini"]
    Worker -.->|"Optional"| Gemini
    Worker -.->|"Optional"| Qdrant[("Qdrant")]
    API -.->|"Optional"| Qdrant
```

| Package | Responsibility |
|---|---|
| [`apps/api`](apps/api) | FastAPI service: case workflow, ingestion pipeline, classification, clerk, PDF engine, signer portal API, ARQ worker |
| [`apps/web`](apps/web) | Next.js App Router app: office workspace, signer portal, same-origin portal proxy |
| [`packages/shared-types`](packages/shared-types) | TypeScript API contracts, checked against the Pydantic models by a test |

| Layer | Technology |
|---|---|
| API | Python 3.11+, FastAPI, Pydantic, SQLAlchemy (async), Alembic |
| Web | Next.js 15 (App Router), React 19, TypeScript (strict), Tailwind CSS, pdf.js |
| Documents | PyMuPDF, ReportLab, pypdf, python-bidi, arabic-reshaper, bundled Rubik font |
| Data | PostgreSQL (SQLite for zero-setup local runs), local or S3-compatible object storage |
| Background work | Redis, ARQ |
| AI | Gemini (classification, field extraction, reply phrasing), Qdrant (label memory) |
| Infrastructure | Docker, Docker Compose |

## Engineering highlights

### Hebrew and RTL in a PDF pipeline

PDF form widgets do not lay out right-to-left text reliably, and flattening can paint over text drawn earlier. The engine in [`pdf_filler.py`](apps/api/app/services/pdf_filler.py) works around both problems:

- Logical Unicode is written to the AcroForm field, which is then rendered invisibly.
- After the form is baked, Hebrew is drawn directly at the widget's coordinates, so no widget appearance can cover it.
- [`text_layout.py`](apps/api/app/domain/text_layout.py) converts text to visual order with `python-bidi` and `arabic-reshaper`, and the bundled Rubik font is embedded in the PDF.
- If drawing fails, the code falls back to an HTML layout with `dir="rtl"`.

### Layered signing record

Each signed packet has two hashes, because a document cannot contain a hash of itself:

| Hash | Covers | Purpose |
|---|---|---|
| `content_sha256` | The flattened, signed form, before the certificate and footers | Printed in the PDF. The exact bytes are stored, so it can be recomputed. |
| `file_sha256` | The complete final PDF | Stored outside the document. A changed copy no longer matches. |

The [Certificate of Completion](apps/api/app/services/certificate_page.py) records the case reference, signature record ID, timeline, signing method, the signature image, and the exact consent text the signer confirmed. Times are shown in UTC and Israel time, using the correct IST or IDT label.

A few details keep that record honest:

- **One timestamp** feeds the PDF, the certificate, and the database, so they agree to the second.
- **Text overflow fails the signing.** PyMuPDF drops text that does not fit without raising an error, so the code checks the result rather than produce an incomplete certificate.
- **A signed case cannot be overwritten.** Signing a signed case returns `409`. Changing a field after signing invalidates the packet and writes an audit row.
- **IP address and browser are labelled "as reported".** Portal requests take the rightmost `X-Forwarded-For` entry, and client-supplied portal headers are never forwarded. This is reliable only behind a reverse proxy that overwrites that header.

The certificate states that it does not verify the signer's identity. Tampering is detected by comparing a file with the stored hash. The PDF itself has no cryptographic seal.

### Signer portal

The portal gives an outside signer exactly one capability: completing one case.

- **Hash-only tokens.** Links use 256-bit random tokens. Only the SHA-256 hash is stored, and the raw token is shown once, so a database leak does not expose working links.
- **Private API.** Signers never call the API directly. A [same-origin Next.js proxy](apps/web/app/api/portal/%5Btoken%5D/%5B%5B...path%5D%5D/route.ts) forwards only an exact allowlist of method and path pairs, and passes the token as a bearer header to keep it out of API access logs.
- **Purpose-built responses.** `PortalView` is a separate schema with no case UUID, document IDs, internal case name, classification data, or office chat. Tests assert this for responses, stream frames, and error bodies.
- **Sign what you reviewed.** The signer sees a watermarked draft and signs a digest of those values. If the office changes a field in the meantime, signing returns `409` and asks for a fresh review.
- **Atomic completion.** The link is claimed with a conditional `UPDATE` before any file is touched, so a double submit cannot sign twice. If PDF generation fails, the claim rolls back and the link still works.
- **Revocation with a receipt.** Signing closes all write access at once, while the same token keeps time-limited, read-only access to the signed copy.
- **Bounded cost and exposure.** Chat turns are capped per link, and portal pages send `no-referrer`, `noindex`, and `no-store` headers.

Object keys are the only stored paths. A new file is `org/{organization_id}/cases/{case_id}/documents/{id}{suffix}`, and a signed packet is `org/{organization_id}/cases/{case_id}/signed/{id}/signed.pdf` with the pre-certificate form beside it. Keys are generated, never reused, and contain neither the case name nor the uploaded filename. A download still goes through the office session or the signing token before any bytes are read.

### Background processing and streaming

- **Queue with fallback.** With `QUEUE_ENABLED=true`, an upload is queued only if a worker has published a live ARQ health key. Otherwise the API processes it in-process, so a case is not left waiting on a worker that isn't running.
- **Restart recovery.** A queued job survives a worker restart, and documents left in `PROCESSING` are picked up again. In-process fallback work is lost if the API restarts.
- **Live progress.** Pipeline progress reaches the browser over Server-Sent Events, backed by a one-second database poll, which works the same whether the API or a worker is doing the job.
- **Streaming that cannot lose data.** The clerk's validated turn and template reply are committed before streaming starts. Gemini only rephrases field labels, validation messages, and the next question. If the stream fails or goes quiet for 20 seconds, the saved reply stands and the client replaces any partial text.

### Contracts that cannot drift

A test compares the fields of each listed Pydantic model with its TypeScript interface in [`packages/shared-types`](packages/shared-types/src/index.ts), including field order. An API contract change that skips the web app fails the suite.

## Repository structure

```text
.
├── apps/
│   ├── api/
│   │   ├── alembic/versions/     Database migrations
│   │   ├── app/
│   │   │   ├── api/routes/       HTTP routes: cases, portal, signing links
│   │   │   ├── assets/           Bundled font and generated form templates
│   │   │   ├── catalog/          Process definitions
│   │   │   ├── core/             Configuration, container, dependencies
│   │   │   ├── db/               Sessions and schema compatibility
│   │   │   ├── domain/           Pure rules: readiness, tokens, text layout
│   │   │   ├── models/           SQLAlchemy models
│   │   │   ├── schemas/          Pydantic request and response models
│   │   │   ├── services/         Pipeline, clerk, PDF engine, portal
│   │   │   └── workers/          ARQ settings and job runner
│   │   ├── tests/                Unit and integration tests
│   │   └── Dockerfile
│   └── web/
│       ├── app/
│       │   ├── api/portal/       Same-origin signer proxy
│       │   ├── cases/[id]/       Office case workspace
│       │   └── sign/[token]/     Signer portal
│       ├── components/           Workspace, portal, and shared UI
│       └── lib/                  Office and portal API clients
├── packages/
│   └── shared-types/             TypeScript API contracts
├── docker-compose.yml            Infrastructure, plus the optional app profile
├── .env.example
└── package.json                  npm workspaces
```

## Getting started

**Prerequisites:** Python 3.11+, Node.js 20+, and Docker for the services below.

```bash
git clone <repository-url> docketai
cd docketai
cp .env.example .env
```

Set `GEMINI_API_KEY` in `.env` to enable automatic classification. Everything else runs without it.

### 1. Start infrastructure

This starts PostgreSQL, Redis, and Qdrant:

```bash
docker compose up -d
```

### 2. Set up the API

Point `.env` at PostgreSQL, and let Alembic own the schema:

```dotenv
DATABASE_URL=postgresql+asyncpg://docket:docket@localhost:5432/docketai
AUTO_CREATE_SCHEMA=false
```

Then install, migrate, and run:

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate    # Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

The API is at `http://localhost:8000`, with interactive docs at `/docs`.

### 3. Create the first staff user

From `apps/api`, with the virtualenv active:

```bash
python -m app.cli create-user --organization "Default organization" --email "staff@example.com" --display-name "Staff"
```

The command asks for a password of at least 12 characters. Set `DOCKET_USER_PASSWORD` to supply it without a prompt. Office pages then sign in at `http://localhost:3000/login`.

> **Quick start without Docker:** keep the default `.env`, skip Step 1 and `alembic upgrade head`, and the API creates a local SQLite database by itself. Do not run Alembic against a database created this way unless you first run `alembic stamp head`.

### 4. Start the web app

From the repository root:

```bash
npm install
npm run dev:web
```

Open `http://localhost:3000`.

### 5. Optional: run a background worker

Set `QUEUE_ENABLED=true` in `.env`, restart the API, and start a worker from `apps/api`:

```bash
arq app.workers.tasks.WorkerSettings
```

### Run the API and worker in Docker

Stop any API on port 8000 first. This uses its own PostgreSQL database and publishes the API on `127.0.0.1:8000` only:

```bash
docker compose --profile app up -d --build
```

After changing a form definition, delete `apps/api/app/assets/templates/*.pdf` so the templates are rebuilt.

## Storage

`STORAGE_BACKEND=local` keeps objects under `STORAGE_DIR` (or `apps/api/data/storage`). `STORAGE_BACKEND=s3` uses the bucket named by `S3_BUCKET`. Set `S3_ENDPOINT_URL` and `S3_FORCE_PATH_STYLE=true` for RustFS, MinIO, or another S3-compatible service. Leave `S3_ACCESS_KEY_ID` and `S3_SECRET_ACCESS_KEY` both blank to use the default AWS credential chain, or set both. `S3_SERVER_SIDE_ENCRYPTION` and `S3_KMS_KEY_ID` are sent when they are set.

Docker Compose starts [RustFS](https://github.com/rustfs/rustfs), an S3-compatible server, on `127.0.0.1:9000` with its console on `127.0.0.1:9001`. A one-shot `storage-setup` service creates a private `docketai` bucket, and the `app` profile points the API and worker at it, so they share no volume. MinIO no longer publishes community container images, which is why it is not used here. The compose credentials are development defaults, overridable with `S3_DEV_ACCESS_KEY` and `S3_DEV_SECRET_KEY`. Templates and fonts stay on the local disk.

Local and S3-compatible backends are covered by the test suite, using moto in the default run and a real S3-compatible server when `TEST_S3_ENDPOINT` is set. That mode has been run against RustFS. AWS S3 itself has not been tested. Google Cloud Storage is untested.

An invalidated signature clears the case columns and writes an audit row. The superseded packet and its form object are kept. No retention period is configured.

To copy existing local files into the configured bucket:

```bash
cd apps/api
python -m app.cli migrate-storage --dry-run
python -m app.cli migrate-storage
```

The command refuses to run unless `STORAGE_BACKEND=s3`. It checks each stored hash, writes `org/{organization_id}/{relative key}`, reads the object back, and updates one row at a time. The local source is not deleted, and the command is safe to run again.

## Testing and quality

The API suite has 98 tests across 18 files. It runs on a temporary SQLite database and needs no external services. moto stands in for S3. To run the same suite against an S3-compatible server such as the compose RustFS, create a bucket and export `TEST_S3_ENDPOINT`, `TEST_S3_BUCKET`, `TEST_S3_REGION`, `TEST_S3_ACCESS_KEY_ID`, `TEST_S3_SECRET_ACCESS_KEY`, and `TEST_S3_FORCE_PATH_STYLE`, then run `pytest` from `apps/api`. Tests that read the local directory directly are skipped in that mode.

```bash
cd apps/api
pytest
```

From the repository root, type-check and build the web app:

```bash
npx tsc --noEmit -p apps/web
```

```bash
npm run build -w web
```

| Area | Test file |
|---|---|
| End-to-end case flow | `test_api_flow.py` |
| Signature record and API contracts | `test_audit_contract.py` |
| Certificate, page numbering, re-sign protection | `test_certificate.py` |
| Portal access, data isolation, link lifecycle | `test_portal.py` |
| Chat collection and stream failure handling | `test_chat_collector.py`, `test_chat_stream.py` |
| Queue gating | `test_queue.py` |
| PDF filling, document parsing, file sniffing | `test_pdf_filler.py`, `test_document_processor.py`, `test_file_sniff.py` |
| Validators, gap analysis, structural excerpts | `test_field_validator.py`, `test_gap_analyzer.py`, `test_structural_excerpt.py` |
| Staff sessions | `test_auth.py` |
| Organization isolation | `test_tenancy.py` |
| Object storage | `test_object_store.py`, `test_storage.py`, `test_storage_flow.py` |

## Known limitations and roadmap

These are deliberate boundaries of the current version.

| Area | Current state | Planned |
|---|---|---|
| Authentication | Office routes require a staff login. Sessions are httpOnly cookies on the Next.js app, and the API stays private behind that proxy. MFA, password reset, and SSO are not built. | Optional stronger sign-in |
| Multi-tenancy | Each case belongs to one organization, and Qdrant label search is filtered by that organization. Database row-level security is not built. | Database policies in addition to the application filter |
| PDF integrity | Changes are detected by comparing with the stored file hash. | Cryptographic PDF seal (PAdES) |
| Signer identity | Holding the link is the only proof. Identity is not verified. | Optional stronger verification |
| Storage | Local and S3-compatible backends. Tested with moto and RustFS. AWS S3 and GCS are untested. Invalidated signed packets are retained, and no retention period is set. | Retention rules |
| Data retention | No automatic deletion. Signer IP addresses and browser details are stored. | Configurable retention rules |
| CI | Checks run locally | GitHub Actions |

The Next.js app must sit behind a reverse proxy that overwrites `X-Forwarded-For`. The office and portal proxies send the rightmost entry of that header to the API as the client address.

**Privacy:** with a Gemini key set, document text and clerk messages are sent to Gemini, and confirmed excerpts are stored in Qdrant. Use synthetic data for demos.

**Legal:** DocketAI records evidence of a signing process. It does not provide legal advice, and its certificate wording has not been reviewed by a lawyer.

## Acknowledgements

The Rubik font is distributed under the [SIL Open Font License](apps/api/app/assets/fonts/OFL.txt).
