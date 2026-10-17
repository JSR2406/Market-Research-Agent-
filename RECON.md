# RECON.md — Saathi Integration Plan: verified current state

> Output of Section 1.4 recon. The plan's Section 1 is explicitly "VERIFY before
> coding"; several of its assumptions are wrong. This file records reality and
> the resulting corrections, per the Section 1.4 acceptance criteria.

Date of recon: 2026-10-17 · Repo: `E:\CODING\Market Research Agent` · Branch: `main`
Baseline commit: `b3e863c`

---

## 1. Real stack

| Plan assumption (§1.2) | Reality | Verdict |
|---|---|---|
| Next.js App Router + TS on Vercel | Next.js **15.5.23** App Router + TypeScript; deployed on Vercel | ✅ correct |
| Tailwind CSS | Tailwind **v4** (`@tailwindcss/postcss`); styling is mostly CSS variables + inline styles | ✅ correct |
| "At least one server route" in Next.js | **`frontend/app/api/` does not exist.** There is **no** Next.js API layer. | ❌ **wrong** |
| Client-side persistence only (localStorage/IndexedDB) | localStorage holds only the session id + intake + language. **Research sessions are stored server-side** as JSON (`backend/sessions/*.json`, 7-day retention). | ❌ **wrong** |
| Scheme data hardcoded in a component | `backend/data/schemes.json` — a curated dataset (7 entries: CGTMSE, MUDRA Shishu/Kishore/Tarun/Tarun Plus, PMEGP, PM SVANidhi) with `source_url` + `last_verified_at` + `checks[]`; served via `GET /api/schemes`. | ⚠️ partly |
| No database client | Correct — **no** prisma/drizzle/pg/vercel-postgres anywhere. | ✅ correct |

**The big correction:** this is a **two-service app**, not a single Next.js
project.

- **Frontend** — Next.js 15 App Router (`frontend/`), talks to the backend only
  through `frontend/lib/api.ts` (`API_BASE`, `WS_URL`).
- **Backend** — **Python / FastAPI** (`backend/`), REST + **WebSocket**
  (`/api/ws/market`), deployed on Render free tier (~30–60 s cold start).
  Routers: `chat`, `langchain`, `ledger`, `schemes`, `sessions`, `voice`,
  `whatsapp`, `ws_market`.

Any "API route" in the plan means a **FastAPI router**, not a Next.js handler.

## 2. Real routes (frontend)

| Route | File | Notes |
|---|---|---|
| `/` | `app/page.tsx` | landing (marked, no auth) |
| `/research` | `app/research/page.tsx` | WS run + Business Check-up + report + history |
| `/advisor` | `app/advisor/page.tsx` | chat + LiveKit voice |
| `/schemes` | `app/schemes/page.tsx` | fetches `GET /api/schemes` |
| `/history` | `app/history/page.tsx` | session history (added `b3e863c`) |

The plan's "dead routes returning 404" (`/about`, `/voice`, `/pricing`,
`/roadmap`, `/dashboard`) **do not exist as links anywhere** — there are no
broken links to fix. `/about`, `/privacy`, `/terms`, `/disclaimer` genuinely do
**not** exist yet (WS-13 is a real gap).

## 3. Where capabilities the plan calls "Not present" already exist

| Plan claim (§1.3) | Reality |
|---|---|
| "Eligibility: **Not present**" | ❌ **Present and central.** `backend/core/eligibility.py` — a deterministic rule engine over `schemes.json` `checks[]` returning `eligible / likely / blocked / not_eligible / wrong_tier`, with `basis` + `source_url` per verdict, `group_by_family()` collapsing MUDRA tiers. Exposed at `POST /api/eligibility`; the Business Check-up polls it live. |
| "Trust: **None**" | ⚠️ Report-internal disclaimers exist; no `/about`/`/privacy`/`/terms` pages. |
| "Channel: web only" | ❌ **WhatsApp scaffold already exists** — `backend/api/whatsapp.py` (Meta Cloud API webhook → `chat_agent`, per-sender memory, always-200). Inactive until `WHATSAPP_TOKEN` / `WHATSAPP_PHONE_NUMBER_ID` / `WHATSAPP_VERIFY_TOKEN` are set. |
| "Freshness: manual Verified badge" | ⚠️ `last_verified_at` + `source_url` are stored per scheme, but there is **no scheduled re-verification job** (WS-7 is a real gap). |
| "Document prep: partial ledger" | ✅ ActionLedger + `document_checklist` tool; no per-bank routing, no PDF export (WS-4/WS-5 real gaps). |
| "Real-time: web search only" | ✅ correct (`googlesearch-python` → DuckDuckGo fallback); no structured feeds (WS-8 real gap). |
| "Languages EN + HI" | ✅ 2 languages only (WS-9 real gap). |
| "Value estimate: Not present" | ⚠️ `CashflowSimulator` (client-side projection) exists; no per-scheme subsidy/benefit value (WS-3 real gap). |
| "Measurement: None" | ✅ correct — no analytics at all (WS-12 real gap). |

## 4. LLM / provider env vars (backend, server-only)

`backend/core/config.py` reads (all optional, all `os.getenv`):

`OPENROUTER_API_KEY`, `OPENROUTER_API_KEY_2`, `OPENROUTER_BASE_URL`,
`LLM_MODEL`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `HF_API_TOKEN`, `HF_MODEL`,
`LLM_PROVIDER_PRIORITY` (default `ollama,huggingface,openrouter`),
`AGENTIC_ENGINE_ENABLED`, `AGENTIC_MAX_ITERATIONS`, `WEB_SEARCH_ENABLED`,
`WEB_SEARCH_MAX_RESULTS`, `ELEVENLABS_API_KEY`, `HF_TTS_MODEL`,
`PIPER_VOICE_*`, `LIVEKIT_*`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_TOKEN`,
`WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_APP_SECRET`, plus CORS origins.

Provider chain: **Ollama (local, free) → Hugging Face (free tier) → OpenRouter**,
with a deterministic **heuristic tier** so every agent still answers with all
providers down. All LLM calls go through `backend/core/llm_client.py`.

## 5. Non-negotiables that constrain the plan

These are repo rules (AGENTS.md) and must survive every workstream:

1. **Offline guarantee** — every agent must produce usable output with all LLM
   providers down; `/api/eligibility` and `/api/ledger` are fully deterministic.
   **Implication:** no hard dependency on a network DB for the core flows; a DB
   must be optional and degrade to the curated JSON dataset.
2. **Provenance** — scheme data comes only from `backend/data/schemes.json`
   (each entry carries `source_url` + `last_verified_at`); eligibility is decided
   in code, never by the model; every numeric value is deterministic code.
3. **Existing routes never break**; new behaviour is additive.
4. **Secrets** — env vars only (`os.getenv`), never in client components, no
   `.env` committed.
5. **i18n** — every user-facing string through `frontend/lib/i18n.tsx`; official
   terms (Udyam, GST, MUDRA, PMEGP, CGTMSE, PM SVANidhi) never translated.
6. **Gates** — `pytest`, `tsc --noEmit`, `eslint`, `next build` must all pass.

## 6. Corrections to the plan

1. **Data layer location.** The plan puts the data model in Prisma/Postgres
   inside the Next.js app. That would create a **second source of truth** for
   schemes/eligibility, which the repo forbids. The data layer belongs in the
   **Python backend**, extending `backend/data/schemes.json` into a governed,
   versioned dataset. A real DB (Postgres) is introduced **only if**
   `DATABASE_URL` is present, behind an adapter, with the JSON dataset as the
   always-available fallback (preserves the offline guarantee).
2. **"Server-render `/schemes` from the DB."** `/schemes` must stay a client of
   the backend API (`GET /api/schemes`); it cannot read Postgres directly.
3. **WS-12 analytics** must be first-party and stored via the backend (or
   client-only), never a third-party tracker.
4. **WS-13 compliance pages** are pure frontend additions and safe to ship early.
5. **WS-9 voice** already has a strong keyless local chain (faster-whisper +
   Piper); Sarvam is an *additive* cloud option, not a replacement.

## 7. Revised P0 (Foundations) — adapted to reality

| WS | Adapted scope | Status |
|---|---|---|
| WS-1 | Expand `schemes.json` from 7 → 25+ central schemes (+ structure for `category/level/state`, benefits, documents); keep `/api/schemes`; add filters. | queued |
| WS-2 | Extend the **existing** eligibility engine with soft-rule **scoring** (0–100) + structured `reasons[]`/`matched`/`failed`; keep the existing verdicts. | queued |
| WS-3 | Benefit/subsisdy value per match (deterministic). | queued |
| WS-7 | Provenance/freshness: a verification job + "review due" flagging + link-health. | queued |
| WS-12 | First-party analytics events + funnel (opt-out). | queued |
| WS-13 | `/about`, `/privacy` (DPDP), `/terms`, `/disclaimer` + footer/sitemap/robots. | queued |

P0 exit criterion (adapted): **25+ schemes served with provenance and provenance
blocks; eligibility returns scored matches with reasons; trust pages live;
analytics funnel visible — all offline-safe and all four gates green.**
