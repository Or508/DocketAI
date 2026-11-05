# DocketAI

DocketAI ingests a bundle of PDFs and scans, classifies them against a process checklist, asks for the missing personal details, fills a Hebrew-capable AcroForm, and stamps a signature drawn in the browser.

## Layout

```
apps/api                  FastAPI, SQLAlchemy, pipeline, ARQ worker
apps/web                  Next.js case checklist, clerk chat, signing modal
packages/shared-types     API contracts shared with the web app
```

The case is the folder. Each uploaded file is a document. A process definition is the required checklist and the form fields. Audit rows record automatic and human classifications; confirmed labels can be embedded in Qdrant so later files are classified with those examples.

## Flow

1. `POST /cases` opens a case for `onboarding` or `real_estate`.
2. `POST /cases/{id}/upload` stores the files and queues parsing.
3. Text is extracted with PyMuPDF. Sparse pages are rendered and sent to Gemini with a structured classification schema.
4. `GET /cases/{id}/status` returns identified files, missing requirements, and files that need a person. A low-confidence suggestion does not satisfy a requirement.
5. `POST /cases/{id}/classify-manual` records the human label and upserts an embedding.
6. `POST /cases/{id}/chat` validates the next personal details (including an Israeli ID checksum and RTL text).
7. `POST /cases/{id}/fill-and-sign` writes logical Unicode into the AcroForm, paints Hebrew with MuPDF, and stamps the PNG signature.
8. `GET /cases/{id}/signed-document` downloads the packet.

Redis/ARQ runs the pipeline when `QUEUE_ENABLED=true` and Redis is reachable. Otherwise the API processes the bundle in-process after the upload response. Gemini and Qdrant are optional: without a key, every file waits for a human label and the clerk fills one field per message.

## Run locally

```powershell
cd apps\api
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

```powershell
npm install
npm run dev:web
```

The API uses SQLite at `apps/api/data/docketai.db` until `DATABASE_URL` points at Postgres. Copy `.env.example` to `.env` and set `GEMINI_API_KEY` for automatic classification. `docker compose up -d` starts Postgres, Redis, and Qdrant.

```powershell
cd apps\api
alembic upgrade head
```

Use Alembic on an empty Postgres database with `AUTO_CREATE_SCHEMA=false`. The default local boot creates the schema itself. Do not run Alembic against tables that were already created that way unless you `alembic stamp head`.

Hebrew text uses the first font found from `HEBREW_FONT_PATH`, Arial, Segoe UI, or DejaVu. Delete `apps/api/app/assets/templates/*.pdf` after changing a form so the templates are rebuilt.

The worker, once Redis is up:

```powershell
cd apps\api
arq app.workers.tasks.WorkerSettings
```

## Not in this scaffold

Authentication, tenant isolation, and object storage. Put the API behind an auth gateway before exposing it. Document text is sent to Gemini when a key is set, and confirmed excerpts are stored in Qdrant.
