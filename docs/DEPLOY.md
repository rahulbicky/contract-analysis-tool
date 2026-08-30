# Deploying ContractLens (Render + Qdrant Cloud)

This deploys the FastAPI backend and Streamlit UI as two Render web services,
using Qdrant Cloud's free tier instead of self-hosting Qdrant.

## 1. Push this repo to GitHub

```
git remote add origin https://github.com/RahulBicky/contractlens.git
git push -u origin main
```

Render deploys from a GitHub repo, so this has to exist before continuing.

## 2. Create a Qdrant Cloud cluster

1. Sign up at https://cloud.qdrant.io and create a free-tier cluster.
2. Copy the cluster's URL (looks like `https://xxxxxxxx.qdrant.io`) and its API key.

## 3. Create the Render Blueprint

1. In the Render dashboard: **New > Blueprint**, connect the GitHub repo.
   Render will read `render.yaml` and propose two services:
   `contractlens-api` and `contractlens-ui`.
2. Render will prompt for the env vars marked `sync: false` in `render.yaml`.
   Fill in what you have so far:
   - `contractlens-api`: `GROQ_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`,
     `CONTRACTLENS_API_KEY` (pick any strong random string — this is the shared
     secret between the UI and API), `LANGSMITH_API_KEY` (optional).
   - `contractlens-ui`: `CONTRACTLENS_API_KEY` (same value as above).
   - Leave `CONTRACTLENS_ALLOWED_ORIGINS` (api) and `CONTRACTLENS_API_URL` (ui)
     blank for now — their values depend on URLs Render hasn't assigned yet.
3. Deploy. Render will build both services from the Dockerfile.

## 4. Wire the two services together

Once both are deployed, Render shows each service's public URL
(e.g. `https://contractlens-api.onrender.com`, `https://contractlens-ui.onrender.com`).

1. On `contractlens-api` > Environment, set:
   `CONTRACTLENS_ALLOWED_ORIGINS=https://contractlens-ui.onrender.com`
2. On `contractlens-ui` > Environment, set:
   `CONTRACTLENS_API_URL=https://contractlens-api.onrender.com`
3. Both services will redeploy automatically on env var save.

## 5. Verify

- `GET https://contractlens-api.onrender.com/health` should return `{"status": "healthy"}`.
- Open the UI URL, upload a test contract PDF, and confirm analysis completes.
- `GET https://contractlens-api.onrender.com/costs` with header
  `X-API-Key: <your CONTRACTLENS_API_KEY>` should return `200`, and `401` without it.

## Notes

- Render's `starter` plan is used in `render.yaml` — the free tier spins
  services down when idle, which will make the first request after idle slow
  (cold start) and can lose in-memory state (`pending_approvals`,
  `data/cost_log.json` — the Render filesystem is ephemeral on free/starter
  plans). For anything beyond a demo, upgrade the plan and consider replacing
  the in-memory `pending_approvals` dict with something durable.
- `CONTRACTLENS_MAX_UPLOAD_MB` and rate limiting (`10/minute` on `/analyze`) are
  already configured — see `src/contractlens/api/main.py` if you need to change them.
