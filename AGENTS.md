# Market Research Agent

## Stack
- Backend: Python, FastAPI, WebSockets, httpx, uvicorn, python-dotenv
- Frontend: Next.js 15 App Router, TypeScript, Tailwind CSS, Framer Motion, react-markdown, remark-gfm, lucide-react
- LLM: Multi-provider via backend/core/llm_client.py — Ollama (local, free), Hugging Face Inference API (free tier), OpenRouter (cloud)
- Web research: googlesearch-python + httpx + BeautifulSoup (no keys, Google → DuckDuckGo fallback)

## Folder Structure
market-research-agent/
├── backend/
│   ├── .env
│   └── requirements-voice.txt  # OPTIONAL livekit stack (torch-heavy)
│   ├── main.py                 # FastAPI app, lifespan, CORS, /health
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py           # env-derived settings, fail-fast key guard
│   │   ├── llm_client.py       # multi-provider LLM client + cache + token counter
│   │   ├── heuristics.py       # zero-LLM advisory engine (offline guarantee tier)
│   │   ├── web_research.py     # search + scrape (Google → DuckDuckGo), no keys
│   │   ├── ws.py               # SafeWebSocket — serialized sends
│   │   ├── memory.py           # JSON session store, 7-day retention
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
│   │   └── worker.py           # Silero STT → AdvisoryLLM → ElevenLabs TTS
│   ├── workflows/
│   │   ├── __init__.py
│   │   ├── executor.py         # run orchestration, emits WS events
│   │   └── routing.py          # keyword step→agent mapping (zero LLM calls)
│   ├── data/
│   │   └── schemes.json        # curated Indian MSME schemes
│   └── api/
│       ├── __init__.py
│       ├── ws_market.py        # WS endpoint (start/cancel/export/delete)
│       ├── chat.py             # /api/chat (POST/GET history/DELETE) + chat memory
│       ├── sessions.py         # GET /api/sessions/{session_id} — resume a saved advisory
│       └── voice.py            # /api/voice/{transcribe,speak,livekit-token}
└── frontend/
    ├── .env.local
    ├── package.json
    ├── app/
    │   ├── layout.tsx
    │   ├── page.tsx            # redirect → /research
    │   └── research/page.tsx   # WS client, run/cancel, report state
    └── components/
        ├── TopicInput.tsx      # text + voice input, step selector
        ├── AgentTimeline.tsx   # step progress + status
        ├── AdvisoryCard.tsx    # advisory render, simplified doc, download/copy, listen
        ├── ChatPanel.tsx       # business advisory chatbot with saved chat memory
        └── LiveAdvisorPanel.tsx # realtime voice (LiveKit): join room, mic, agent audio

## LLM Model Routing (all calls via backend/core/llm_client.py only)
- All agents route through `backend/core/llm_client.call_llm()` with a per-agent `agent_hint`.
- Provider priority (default `ollama,huggingface,openrouter`) is configurable via `LLM_PROVIDER_PRIORITY`.
  - **Ollama** (local) — completely free, no token limits: `OLLAMA_MODEL` (default `llama3.2:3b`).
  - **Hugging Face** — Inference API free tier: `HF_MODEL` (default `Qwen/Qwen2.5-7B-Instruct`).
  - **OpenRouter** — cloud fallback: uses `MODEL` + `FALLBACK_MODELS`.
- Agents never hardcode a provider; they just pass `agent_hint` and the client handles fallback.
- Per-agent OpenRouter model priority (`AGENT_OPENROUTER_MODELS` in `backend/core/config.py`) — each agent leads with a distinct model so no single model's quota gets exhausted; the global `FALLBACK_MODELS` chain is appended as backup.
- OpenRouter key rotation: `OPENROUTER_API_KEY_2` (in `backend/.env`) is used automatically on 429/402/timeout and once healthy it becomes the preferred key for later calls.

## Voice / TTS
- `backend/core/voice.py` — never raises, always falls back through:
  - STT: ElevenLabs Scribe (if key) → SpeechRecognition/Google (free).
  - TTS: ElevenLabs (if key) → Hugging Face Inference API (`HF_TTS_MODEL`, default `facebook/mms-tts-eng`, free) → pyttsx3 (offline).
- **Realtime voice (LiveKit)** — separate process, optional stack in `backend/requirements-voice.txt` (`pip install -r backend/requirements-voice.txt`).
  - `python -m backend.voice_agent.worker` joins `LIVEKIT_ADVISOR_ROOM`: Silero local STT → `AdvisoryLLM` (bridges to `call_llm`, agent_hint="voice") → ElevenLabs TTS.
  - Browser joins the same room via `POST /api/voice/livekit-token` (needs `LIVEKIT_URL`/`LIVEKIT_API_KEY`/`LIVEKIT_API_SECRET`) and `LiveAdvisorPanel.tsx` (frontend, `livekit-client`).
  - Lazy imports keep the base backend working without the LiveKit stack.

## Chat / Conversation
- `backend/agents/chat.py` — specialised business advisory & business-building chatbot (loans, schemes, documents, and building the business). Scope-limited: routes off-topic questions back to business. **Multi-language:** replies follow the user's language — Devanagari/Hinglish input (or `lang="hi"`) yields Hindi replies; the offline heuristic fallback speaks Hindi too.
- `backend/api/chat.py` — REST endpoints:
  - `POST /api/chat` (body `{message, session_id?, topic?, lang?}`) → `{reply, session_id, history_count}` where `lang` ∈ `auto` (default) | `hi` | `en`
  - `GET  /api/chat/history?session_id=` → remembered messages
  - `DELETE /api/chat/{session_id}` → clear chat memory (GDPR-aligned)
- Chat memory: stored as `backend/sessions/{session_id}_chat.json` (capped at `MAX_CHAT_MESSAGES`); the latest written advisory is injected as context so the user can ask follow-ups about their own report. The same `session_id` ties the WS research run, the chat, the export, and the delete together.
- Frontend: `ChatPanel.tsx` on `/research` — bubbles, history restore, clear button, Auto/हिंदी/EN language toggle (persisted in `localStorage["grameenai_chat_lang"]`); `session_id` comes from `localStorage["grameenai_session"]` (generated browser-side).
- **Model rule: the `chat` agent's primary OpenRouter model must stay OPEN-SOURCE** (`mistralai/mistral-7b-instruct`). Call path follows the normal chain: Ollama (local) → Hugging Face (free) → OpenRouter.

## WebSocket Events
plan, step_start, step_end, token_usage, status, done (with simplified_report), cancelled, error, resume_available, session_deleted, session_export

## Frontend Novelty Features
- **Loan-Ready Score** — deterministic 0–100 score added to the advisory JSON by `executor._attach_loan_ready_score()` (no LLM cost; rubric in `backend/core/heuristics.compute_loan_ready_score`). `AdvisoryCard.tsx` draws an SVG gauge + "why" reasons. Always present, even fully offline.
- **Cash-Flow Simulator** (`CashflowSimulator.tsx`) — pure client-side cash-flow projection (capital/weekly sales/weekly expenses, 4–24 weeks), SVG line chart, break-even week, monthly surplus. No backend calls.
- **Startup Doctor quiz** (`StartupQuiz.tsx`) — 5 optional questions persisted in `localStorage["grameenai_profile"]`; answers are deterministically folded into the WS `start` topic via `buildProfileSnippet()` (no extra LLM calls).
- **Resume last advisory** — page mount calls `GET /api/sessions/{session_id}` and restores the saved advisory (report + simplified + grey-out of run state) until the user runs again. Backend lives in `backend/api/sessions.py`.

## Rules
- Never hardcode API keys, always use os.getenv()
- All LLM calls only through backend/core/llm_client.py
- Every agent must wrap its call_llm in try/except with a deterministic fallback
- Frontend components: all React components must have "use client" at top
- Use Framer Motion for all animations
- Use lucide-react for all icons
- WebSocket connects to ws://localhost:8000/ws/market
- Use Windows PowerShell compatible commands only

## Data Retention & Privacy
- **Storage:** Research sessions are stored locally as JSON files in `backend/sessions/` (chat memory lives alongside as `{session_id}_chat.json`).
- **Privacy:** Each session is isolated by `session_id`. Users can export their full session data or permanently delete their session using the `export_session` and `delete_session` WebSocket commands (GDPR right-to-delete); deleting a session also clears its chat memory.
- **Retention:** By default, sessions older than 7 days are automatically deleted on server startup by the `cleanup_old_sessions` hook in `main.py`.
