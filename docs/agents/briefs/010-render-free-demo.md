Status: done
For: cursor

# Brief 010: pause the paid Render setup and deploy a free demo instead

The owner wants a temporary link to show the system to a partner, at no cost. The current `render.yaml`
uses paid plans (a private service, a background worker, paid Postgres and Key Value). Keep it, but set it aside,
and put a free-tier Blueprint in its place.

Render's free tier covers only web services, Postgres (expires after 30 days, no backups) and one Key Value.
Private services and background workers have no free plan, and a free web service cannot receive private
network traffic. So for the demo:
- the API becomes a public **web** service (free), and the site calls it at its public https address;
- no worker and no Redis: `QUEUE_ENABLED=false`, so the API reads documents and runs the reminder loop
  in its own process (already supported in `apps/api/app/main.py`);
- `DEMO_MODE=true`, so the partner opens `/demo` without signing up.

## Do

1. Move the paid Blueprint aside, unchanged: `git mv render.yaml deploy/render.paid.yaml`.
   Add one line at its top: `# Paused. To go back to the paid setup, move this file back to the repository root as render.yaml.`
2. Create a new `render.yaml` at the repository root with exactly this content:

```yaml
# FREE demo Blueprint (temporary). The paid production setup is paused in deploy/render.paid.yaml.
# Render → New → Blueprint → this repository and this branch.
#
#   docketflow-web   public, free: the Next.js site
#   docketflow-api   public, free: FastAPI. Free web services cannot talk over Render's private network,
#                    so the site calls the API at its public address.
#   docketflow-db    free PostgreSQL. Render deletes free databases 30 days after creation (14 days' grace).
#
# Free services sleep after 15 minutes without visitors; the first visit after that takes about a minute.
# No worker and no Redis: with QUEUE_ENABLED=false the API reads documents and sends reminders itself.

services:
  - type: web
    name: docketflow-web
    runtime: docker
    region: frankfurt
    plan: free
    dockerfilePath: ./deploy/web.Dockerfile
    dockerContext: .
    healthCheckPath: /login
    envVars:
      # The API's public address. If Render gives the API another name (for example docketflow-api-x1y2),
      # change this in the dashboard to that address and redeploy the site.
      - key: API_INTERNAL_URL
        value: https://docketflow-api.onrender.com

  - type: web
    name: docketflow-api
    runtime: docker
    region: frankfurt
    plan: free
    dockerfilePath: ./apps/api/Dockerfile
    dockerContext: ./apps/api
    # Runs `alembic upgrade head`, then listens on 8000.
    dockerCommand: python -m app.boot api
    envVars:
      - key: PORT
        value: "8000"
      - fromGroup: docketflow-config
      - fromGroup: docketflow-secrets
      - key: DATABASE_URL
        fromDatabase:
          name: docketflow-db
          property: connectionString

databases:
  - name: docketflow-db
    region: frankfurt
    plan: free
    postgresMajorVersion: "16"
    databaseName: docketai
    user: docket
    ipAllowList: []

envVarGroups:
  - name: docketflow-config
    envVars:
      - key: ENVIRONMENT
        value: production
      - key: AUTO_CREATE_SCHEMA
        value: "false"
      - key: QUEUE_ENABLED
        value: "false"
      - key: QDRANT_URL
        value: "off"
      - key: STORAGE_BACKEND
        value: s3
      - key: S3_REGION
        value: auto
      - key: S3_FORCE_PATH_STYLE
        value: "true"
      - key: EMAIL_BACKEND
        value: smtp
      - key: SMTP_HOST
        value: smtp.resend.com
      - key: SMTP_PORT
        value: "587"
      - key: SMTP_SECURITY
        value: starttls
      - key: SMTP_USERNAME
        value: resend
      - key: AI_PROVIDER
        value: claude
      - key: LOG_LEVEL
        value: INFO
      - key: DEMO_MODE
        value: "true"

  - name: docketflow-secrets
    envVars:
      - key: MFA_SECRET_KEY
        generateValue: true
```

3. In `docs/deploy/render.md`, add a short section right after the title, in Hebrew:
   "## דמו חינמי (זמני)" — the paid setup is paused in `deploy/render.paid.yaml`; the current `render.yaml` is free;
   steps 2 (domain) and 7 are skipped; in step 6 `PUBLIC_WEB_URL` is `https://docketflow-web.onrender.com` and
   `EMAIL_FROM` can be `onboarding@resend.dev` (Resend then delivers only to the account owner); if the API got
   a different name, update `API_INTERNAL_URL` on `docketflow-web`; the database is deleted after 30 days;
   the link to send is `https://docketflow-web.onrender.com/demo`. To go back to paid: move `deploy/render.paid.yaml` back.
4. Commit on the current branch and push it (not to `main`). The owner will pick this branch in Render.

## Do not edit
`apps/api/**`, `deploy/web.Dockerfile`, `apps/web/**`.

## Checks
- `python -c "import yaml,sys; yaml.safe_load(open('render.yaml')); yaml.safe_load(open('deploy/render.paid.yaml'))"` passes (or any YAML check you have).
- `git status` is clean after the push.

## Known trade-offs (for the owner, nothing to fix now)
- The API is reachable from the internet in this demo. It still requires its own sessions, but rate limits trust
  the `X-Client-Ip` the caller sends, so they can be dodged. Fine for a showcase with synthetic data; not for real clients.
- The free API has 512 MB and a tenth of a CPU, so reading the demo PDFs is slow. If it runs out of memory,
  the owner moves only `docketflow-api` to a paid plan.

## Answers
