# Market Research Agent

## Product
- **Name:** Your AI Business Saathi
- **Tagline:** Market research, growth planning and government-scheme guidance for small businesses.
- **Audience:** micro-entrepreneurs and small businesses (street vendors, shopkeepers, farmers, tailors…). Never use startup jargon ("Startup Doctor", "founder", "pitch") in user-facing copy — say "Business Check-up", "business", "shop".
- **Rebrand rule:** all new user-facing copy uses "Your AI Business Saathi" / "Saathi". Legacy identifiers (`GrameenAI Advisor` in old copy, `grameenai_*` localStorage keys, `GrameenChatModel` class name) are kept only where renaming would break stored user data or code — do not propagate them.
- **Deployed:** frontend `https://market-research-agent-neon.vercel.app` (Vercel), backend `https://market-research-agent-backend-00ao.onrender.com` (Render free tier, ~30–60s cold start).

## Verification (run after every change, Windows PowerShell, from repo root)
```powershell
.venv\Scripts\python.exe -m pytest tests/ -q          # backend tests (must pass)
cd frontend; npx tsc --noEmit                          # types
npm run lint                                           # eslint
npm run build                                          # next build
```
Never report a phase complete without all four passing.

## Stack
- Backend: Python, FastAPI, WebSockets, httpx, uvicorn, python-dotenv
- Frontend: Next.js 15 App Router, TypeScript, Tailwind CSS, Framer Motion, react-markdown, remark-gfm, lucide-react
- LLM: Multi-provider via backend/core/llm_client.py — Ollama (local, free), Hugging Face Inference API (free tier), OpenRouter (cloud)
- LangChain (optional): `backend/core/langchain_adapter.py` exposes the same multi-provider stack as a LangChain `BaseChatModel` (`GrameenChatModel`) + tools + `build_advisory_chain()`; REST via `backend/api/langchain.py` (`GET /api/langchain/status`, `POST /api/langchain/run`). Requires `langchain-core` (in `backend/requirements.txt`).
- Web research: googlesearch-python + httpx + BeautifulSoup (no keys, Google → DuckDuckGo fallback)

## Data & Accuracy Principles (non-negotiable)
Order of authority for every output the product produces:

**Official/verified data → deterministic rules/calculations → AI explanation → recommendation.**

- The LLM is NOT a source of truth. It may explain and recommend, never establish facts.
- Never let the model invent scheme names, loan amounts, interest rates, eligibility claims, or approval guarantees. Scheme data comes only from `backend/data/schemes.json` (curated, with `sourceUrl` + `lastVerifiedAt`); amounts/eligibility shown to users must be traceable to that data or a cited source.
- Every financial or government-scheme claim shown to a user must carry its source (URL or "curated dataset" provenance). Where a number is computed (e.g. loan-ready score, cash-flow projection), the calculation must be deterministic code, not an LLM output.
- Scores and projections: deterministic functions in `backend/core/heuristics.py` / client-side calculators — never ask the LLM to compute them.
- Offline guarantee: every agent must still produce usable output (heuristic tier) when all LLM providers are down.

## Folder Structure
market-research-agent/
├── backend/
│   ├── .env
│   └── requirements-voice.txt  # OPTIONAL livekit stack (torch-heavy)
│   ├── main.py                 # FastAPI app, lifespan, CORS, /health, session cleanup
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py           # env-derived settings, fail-fast key guard
│   │   ├── llm_client.py       # multi-provider LLM client + cache + token counter
│   │   ├── heuristics.py       # zero-LLM advisory engine (offline guarantee tier) + loan-ready score
│   │   ├── web_research.py     # search + scrape (Google → DuckDuckGo), no keys
│   │   ├── ws.py               # SafeWebSocket — serialized sends
│   │   ├── memory.py           # JSON session store, 7-day retention, session_id allowlist guard
│   │   ├── langchain_adapter.py # OPTIONAL LangChain: GrameenChatModel → call_llm, tools, chains (never raises)
│   │   └── voice.py            # STT/TTS, never raises
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── planner.py          # 5-step plan (+heuristic fallback)
│   │   ├── research.py         # facts + optional live web context (+heuristic fallback)
│   │   ├── analyst.py          # cash-flow snapshot (+heuristic fallback)
│   │   ├── opportunity.py      # scheme matching (+heuristic fallback)
│   │   ├── writer.py           # advisory JSON (+heuristic fallback)
│   │   ├── editor.py           # polished advisory JSON (+heuristic fallback)
│   │   ├── simplifier.py       # low-literacy "In Simple Words" doc (+heuristic fallback)
│   │   └── chat.py             # specialised business advisory/building chatbot (+heuristic fallback)
│   ├── voice_agent/            # OPTIONAL realtime voice (LiveKit) — separate process
│   │   ├── __init__.py
│   │   ├── llm.py              # LiveKit LLM adapter → call_llm (+heuristic fallback)
│   │   ├── stt.py              # LiveKit STT adapter → local faster-whisper (no key)
│   │   └── worker.py           # AgentSession: faster-whisper STT → AdvisoryLLM → ElevenLabs TTS
│   ├── workflows/
│   │   ├── __init__.py
│   │   ├── executor.py         # run orchestration, emits WS events, loan-ready score attach
│   │   └── routing.py          # keyword step→agent mapping (zero LLM calls)
│   ├── data/
│   │   └── schemes.json        # curated Indian MSME schemes (sourceUrl, lastVerifiedAt)
│   ├── sessions/               # runtime JSON stores (gitignored)
│   └── api/
│       ├── __init__.py
│       ├── ws_market.py        # WS endpoint (start/cancel/export/delete) + input validation
│       ├── chat.py             # /api/chat (POST/GET history/DELETE) + chat memory, pydantic caps
│       ├── sessions.py         # GET /api/sessions/{session_id} — resume a saved advisory
│       ├── langchain.py        # GET /api/langchain/status, POST /api/langchain/run (heuristic fallback, never 500)
│       ├── whatsapp.py         # OPTIONAL WhatsApp Cloud API: GET verify, POST incoming → chat_agent → Graph reply (always 200)
│       └── voice.py            # /api/voice/{transcribe,speak,livekit-token}, 5 MB audio cap
├── tests/
│   ├── test_smoke.py           # offline contracts, route surface, profile plumbing
│   └── test_security.py        # path traversal, WS/API input validation
└── frontend/
    ├── .env.local
    ├── package.json
    ├── lib/
    │   └── api.ts              # SINGLE source of API_BASE + WS_URL (never derive URLs elsewhere)
    ├── app/
    │   ├── globals.css         # design tokens (:root vars), keyframes, prose
    │   ├── layout.tsx
    │   ├── page.tsx            # redirect → /research
    │   └── research/page.tsx   # WS client, run/cancel, report state
    └── components/
        ├── TopicInput.tsx      # text + voice input, step selector
        ├── AgentTimeline.tsx   # step progress + status (keyboard-operable expand)
        ├── AdvisoryCard.tsx    # advisory render, simplified doc, download/copy, listen
        ├── ChatPanel.tsx       # business advisory chatbot with saved chat memory
        ├── LiveAdvisorPanel.tsx # realtime voice (LiveKit): join room, mic, agent audio
        ├── StartupQuiz.tsx     # 5-question Business Check-up (file name legacy; UI copy must say Business Check-up)
        ├── CashflowSimulator.tsx # client-side cash-flow projection + SVG chart
        └── Usps.tsx            # "why this isn't a generic chatbot" section

## LLM Model Routing (all calls via backend/core/llm_client.py only)
- All agents route through `backend/core/llm_client.call_llm()` with a per-agent `agent_hint`.
- Provider priority (default `ollama,huggingface,openrouter`) is configurable via `LLM_PROVIDER_PRIORITY`.
  - **Ollama** (local) — completely free, no token limits: `OLLAMA_MODEL` (default `llama3.2:3b`).
  - **Hugging Face** — Inference API free tier: `HF_MODEL` (default `Qwen/Qwen2.5-7B-Instruct`).
  - **OpenRouter** — cloud fallback: uses `LLM_MODEL` + `FALLBACK_MODELS`.
- Agents never hardcode a provider; they just pass `agent_hint` and the client handles fallback.
- Per-agent OpenRouter model priority (`AGENT_OPENROUTER_MODELS` in `backend/core/config.py`) — each agent leads with a distinct model so no single model's quota gets exhausted; the global `FALLBACK_MODELS` chain is appended as backup.
- OpenRouter key rotation: `OPENROUTER_API_KEY_2` (in `backend/.env`) is used automatically on 429/402/timeout and once healthy it becomes the preferred key for later calls.
- LangChain rule: `GrameenChatModel` and all chains must route through `call_llm` (never call a provider SDK directly); `run_prompt()` must keep the heuristic fallback so endpoints never hard-fail when LangChain or the LLM is unreachable.

## Voice / TTS
- `backend/core/voice.py` — never raises, always falls back through:
  - STT: ElevenLabs Scribe (if key) → faster-whisper (open-source, local, no key; handles WebM + Hindi; model size via `WHISPER_MODEL_SIZE`, default `tiny`) → SpeechRecognition/Google (free, WAV only).
  - TTS: ElevenLabs (if key) → Hugging Face Inference API (`HF_TTS_MODEL`, default `facebook/mms-tts-eng`, free) → pyttsx3 (offline).
- **Realtime voice (LiveKit)** — separate process, stack in `backend/requirements-voice.txt` (`pip install -r backend/requirements-voice.txt`).
  - `python -m backend.voice_agent.worker` joins `LIVEKIT_ADVISOR_ROOM` via `AgentSession`: faster-whisper local STT (`voice_agent/stt.py`, no key) → `AdvisoryLLM` (bridges to `call_llm`, agent_hint="voice") → ElevenLabs TTS. Targets livekit-agents==1.8.x.
  - Browser joins the same room via `POST /api/voice/livekit-token` (needs `LIVEKIT_URL`/`LIVEKIT_API_KEY`/`LIVEKIT_API_SECRET`) and `LiveAdvisorPanel.tsx` (frontend, `livekit-client`).
  - Lazy imports keep the base backend working without the LiveKit stack.

## WhatsApp (optional scaffold)
- `backend/api/whatsapp.py` — Meta Cloud API webhook: `GET /api/whatsapp/webhook` verifies (`WHATSAPP_VERIFY_TOKEN`), `POST` answers text messages with the same `chat_agent` brain (per-sender `wa-<number>` memory namespace) and replies via Graph API (`WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`). Always returns 200 so Meta never retry-storms. Inactive until the three env vars are set.

## Chat / Conversation
- `backend/agents/chat.py` — specialised business advisory & business-building chatbot (loans, schemes, documents, and building the business). Scope-limited: routes off-topic questions back to business. **Multi-language:** replies follow the user's language — Devanagari/Hinglish input (or `lang="hi"`) yields Hindi replies; the offline heuristic fallback speaks Hindi too.
- `backend/api/chat.py` — REST endpoints:
  - `POST /api/chat` (body `{message, session_id?, topic?, lang?, profile?}`) → `{reply, session_id, history_count}` where `lang` ∈ `auto` (default) | `hi` | `en`. Input caps: message ≤ 4000 chars, profile ≤ 1500, session_id must match `^[A-Za-z0-9_-]{1,64}$` (422 otherwise).
  - `GET  /api/chat/history?session_id=` → remembered messages
  - `DELETE /api/chat/{session_id}` → clear chat memory (GDPR-aligned)
- Chat memory: stored as `backend/sessions/{session_id}_chat.json` (capped at `MAX_CHAT_MESSAGES`); the latest written advisory is injected as context so the user can ask follow-ups about their own report. The same `session_id` ties the WS research run, the chat, the export, and the delete together.
- Frontend: `ChatPanel.tsx` on `/research` — bubbles, history restore, clear button, Auto/हिंदी/EN language toggle (persisted in `localStorage["grameenai_chat_lang"]`); `session_id` comes from `localStorage["grameenai_session"]` (generated browser-side).
- **Model rule: the `chat` agent's primary OpenRouter model must stay OPEN-SOURCE** (`mistralai/mistral-7b-instruct`). Call path follows the normal chain: Ollama (local) → Hugging Face (free) → OpenRouter.

## WebSocket Events
plan, step_start, step_end, token_usage, status, done (with simplified_report), cancelled, error, resume_available, session_deleted, session_export

- `start` payload: `{type, topic, max_steps?, session_id?, profile?}` — topic capped at 4000 chars, profile at 1500, `max_steps` coerced to 1–6, `session_id` validated against the allowlist (invalid → `error` event, no run).
- A malformed frame or unknown type yields an `error` event and the connection stays open.

## Security & Input Validation (P0 — do not regress)
- `session_id` is client-controlled and used for file paths. Validation lives in `backend/core/memory.py` (`is_valid_session_id`, allowlist `[A-Za-z0-9_-]{1,64}`); every write/delete entry point raises `ValueError` on invalid ids, reads return empty. WS + REST validate early and answer with friendly `error` events / 422s.
- Client-facing errors are friendly and generic (no `str(e)`, no stack traces, no server paths, no "port 8000" hints in production UI). Details go to server logs (`logger.exception` / `console.error`) only. Dev-only setup hints in the UI must be gated behind `process.env.NODE_ENV !== "production"`.
- All frontend URLs come from `frontend/lib/api.ts` (`API_BASE`, `WS_URL`) — never read `NEXT_PUBLIC_*` env vars elsewhere; the module handles http→https / ws→wss upgrades in one place.

## Frontend Novelty Features
- **Loan-Ready Score** — deterministic 0–100 score added to the advisory JSON by `executor._attach_loan_ready_score()` (no LLM cost; rubric in `backend/core/heuristics.compute_loan_ready_score`). `AdvisoryCard.tsx` draws an SVG gauge + "why" reasons. Always present, even fully offline.
- **Cash-Flow Simulator** (`CashflowSimulator.tsx`) — pure client-side cash-flow projection (capital/weekly sales/weekly expenses, 4–24 weeks), SVG line chart, break-even week, monthly surplus. No backend calls.
- **Business Check-up quiz** (`StartupQuiz.tsx`) — 5 optional questions persisted in `localStorage["grameenai_profile"]`; answers are deterministically folded into the WS `start` topic via `buildProfileSnippet()` AND sent as a separate `profile` field on the `start` message (no extra LLM calls). The backend (`executor.run_research_workflow`) guarantees the profile is in the run topic, injects it into the writer's synthesis prompt (reflected in `business_summary`/`next_step`), persists it in session state (`state.profile`), and `POST /api/chat` uses it (request body, falling back to session state) so the advisor chat answers follow-up questions from the same answers — `chat_agent(profile=...)`.
- **Resume last advisory** — page mount calls `GET /api/sessions/{session_id}` and restores the saved advisory (report + simplified + grey-out of run state) until the user runs again. Backend lives in `backend/api/sessions.py`.

## Rules
- Never hardcode API keys, always use os.getenv()
- All LLM calls only through backend/core/llm_client.py
- Every agent must wrap its call_llm in try/except with a deterministic fallback
- Frontend components: all React components must have "use client" at top
- Use Framer Motion for all animations
- Use lucide-react for all icons; no emoji as icons
- Frontend must import `API_BASE`/`WS_URL` from `@/lib/api` — no ad-hoc URL derivation
- All user-facing errors must be friendly and actionable; never surface exceptions, stack traces, server paths, or dev commands to end users
- Responsive & mobile-first: the app must work from 360 px upward; no fixed-width layouts that break small screens; test before claiming done
- Accessibility: no nested `<button>`s; interactive elements need `role`/`tabIndex`/`onKeyDown`/`aria-*` where semantics aren't native; visible focus must work
- Data integrity: follow the Data & Accuracy Principles above — deterministic code for anything numeric, sources for anything factual
- Use Windows PowerShell compatible commands only

## Data Retention & Privacy
- **Storage:** Research sessions are stored locally as JSON files in `backend/sessions/` (chat memory lives alongside as `{session_id}_chat.json`).
- **Privacy:** Each session is isolated by `session_id`. Users can export their full session data or permanently delete their session using the `export_session` and `delete_session` WebSocket commands (GDPR right-to-delete); deleting a session also clears its chat memory.
- **Retention:** By default, sessions older than 7 days are automatically deleted on server startup by the `cleanup_old_sessions` hook in `main.py`.
