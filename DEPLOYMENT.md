# Deployment Guide

This project has two parts:
1. **Frontend** — Next.js, deployed to Vercel
2. **Backend** — FastAPI (Python), deployed to Railway or Render

---

## Step 1 — Deploy the Backend (Railway recommended)

### Option A: Railway
1. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub repo
2. Set **Root Directory** to `/` (the repo root, NOT `/backend`)
3. Set **Start Command** to:
   ```
   uvicorn backend.main:app --host 0.0.0.0 --port $PORT
   ```
4. Add these **Environment Variables** in Railway dashboard:
   | Key | Value |
   |-----|-------|
   | `OPENROUTER_API_KEY` | your key from [openrouter.ai](https://openrouter.ai/keys) |
   | `ALLOWED_ORIGINS` | `https://market-research-agent-jsr2406.vercel.app` |
   | `MODEL` | `google/gemini-2.5-flash:free` |
5. After deploy, copy your Railway URL, e.g. `https://market-research-agent-production.up.railway.app`

### Option B: Render
1. Go to [render.com](https://render.com) → New Web Service → connect repo
2. Set **Root Directory** to `/` and use the `render.yaml` as blueprint
3. Set the same env vars as above

---

## Step 2 — Configure Vercel Frontend

1. Go to [vercel.com](https://vercel.com) → your `Market-Research-Agent-` project
2. Settings → **General** → Set **Root Directory** to `frontend`
3. Settings → **Environment Variables** → Add:
   | Key | Value |
   |-----|-------|
   | `NEXT_PUBLIC_WS_URL` | `wss://YOUR_RAILWAY_URL/ws/market` |
   > ⚠️ Use `wss://` (secure WebSocket) — NOT `ws://` — because Vercel serves over HTTPS.
4. Redeploy the frontend

---

## Step 3 — Verify

- Visit `https://YOUR_RAILWAY_URL/health` — should return `{"status": "ok"}`
- Visit the Vercel URL, enter a topic, click **Start Research**
- Watch the agent timeline populate and the final report render

---

## Local Development

```bash
# Terminal 1 — Backend
cd <repo root>
cp backend/.env.example backend/.env   # fill in OPENROUTER_API_KEY
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload

# Terminal 2 — Frontend
cd frontend
npm install
npm run dev
# Open http://localhost:3000
```

> NEXT_PUBLIC_WS_URL defaults to `ws://localhost:8000/ws/market` in local dev.
