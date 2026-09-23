# 🚀 GrameenAI Advisor (Market Research Agent)

**Live Demo:** [https://market-research-agent-jsr2406.vercel.app](https://market-research-agent-jsr2406.vercel.app)

Multi-agent AI platform that turns a plain-language business description from a
micro-entrepreneur into a **Loan Readiness Advisory**: a cash-flow snapshot,
matched Indian MSME schemes (MUDRA/CGTMSE/PMEGP/PM SVANidhi), a document
checklist, a next step, voice narration, and a simplified "read-aloud" document.
Built with **Next.js 15**, **FastAPI**, and a multi-provider LLM client
(Ollama → Hugging Face → OpenRouter) with a deterministic offline fallback.

![Market Research Dashboard](./assets/dashboard.png)

## ✨ Features

- **🤖 Multi-Agent Orchestration**: Specialized agents for Planning, Researching, Analyzing, Opportunity Discovery, Writing, Editing, and Simplifying.
- **⚡ Real-time Updates**: Live WebSocket streaming shows the agent's progress step-by-step.
- **🔍 Deep Analysis**: Leverages multiple free LLM providers (via one client) for actionable advisory.
- **🧭 Real-time Web Research**: Optional web search + scraping enriches the research agent with live snippets.
- **🗣️ Voice I/O**: Record your business description by voice; listen to the advisory (ElevenLabs → Hugging Face → offline pyttsx3 fallback).
- **💬 Business Advisor Chat**: Specialised chatbot that builds your business and makes you loan-ready (schemes, documents, eligibility) — with saved chat memory per session and Hindi/Hinglish replies.
- **📜 Simplified Document**: Low-literacy "In Simple Words" advisory, download/copy as `.txt`.
- **🛟 Offline Resilience**: If every LLM provider is down, a deterministic engine still produces a full advisory from local scheme data.

## 🛠️ Tech Stack

- **Frontend**: Next.js 15 (App Router), TypeScript, Tailwind CSS, Framer Motion, Lucide React.
- **Backend**: FastAPI (Python), WebSockets (with a send-lock wrapper), HTTPX, BeautifulSoup.
- **AI Engine**: Multi-provider LLM client — Ollama (local, free) → Hugging Face Inference API (free tier) → OpenRouter (cloud fallback).
- **Communication**: Real-time bidirectional WebSockets (`ws://localhost:8000/ws/market`, `wss://` in production).

## 🏗️ System Architecture

```text
┌─────────────────────────────┐        WebSocket (ws/wss)         ┌──────────────────────────────────────────────┐
│       Next.js Frontend      │  ◄──────────────────────────────►  │          FastAPI Backend (uvicorn)           │
│  TopicInput · AgentTimeline │    plan / step_start / step_end /  │                                                │
│  AdvisoryCard (+voice UI)   │    token_usage / done / error      │  /health                   (REST)            │
└─────────────┬───────────────┘                                    │  /api/voice/transcribe      (REST)           │
              │ HTTP (voice clip / TTS bytes)                      │  /api/voice/speak           (REST)           │
              ▼                                                    └───────────────┬────────────────────────────────┘
        BACKEND_URL:8000                                                           │
                                                     ┌──────────────────────────────▼─────────────────────────────┐
│  api/                                                        │
                                                      │   ws_market.py — WS loop, session_id, cancel, export/delete │
                                                      │   chat.py     — /api/chat + history + delete            │
                                                      │   voice.py    — STT/TTS HTTP endpoints                    │
                                                     └──────────────────────────────┬─────────────────────────────┘
                                                                                    │
                                                    ┌───────────────────────────────▼──────────────────────────────┐
                                                    │  workflows/                                                   │
                                                    │   executor.py    — orchestrates the run, emits WS events    │
                                                    │   routing.py     — keyword step→agent mapping (zero-LLM)     │
                                                    └───────────────────────────────┬──────────────────────────────┘
                                                                                    │ per-step calls
                                                    ┌───────────────────────────────▼──────────────────────────────┐
                                                    │  agents/                                                      │
                                                    │  planner → research → analyst → opportunity → writer →       │
                                                    │           editor → simplifier                                │
                                                    │  Every agent wraps call_llm in try/except and falls back to   │
                                                    │  a deterministic heuristic so the flow ALWAYS responds.      │
                                                    └───────────────────────────────┬──────────────────────────────┘
                                                                                    │
                                                    ┌───────────────────────────────▼──────────────────────────────┐
                                                    │  core/                                                        │
                                                    │  llm_client.py  — multi-provider fallback + cache + tokens    │
                                                    │  heuristics.py  — zero-LLM advisory engine (offline tier)     │
                                                    │  web_research.py— search + scrape (Google → DuckDuckGo)      │
                                                    │  ws.py          — SafeWebSocket (serialized sends)            │
                                                    │  memory.py      — JSON session store + 7-day retention       │
                                                    │  voice.py       — STT/TTS chain (never raises)                │
                                                    │  config.py      — env-derived settings (fail-fast on bad key) │
                                                    └───────────────────────────────┬──────────────────────────────┘
                                                                                    │
                                                  data/schemes.json (curated MSME schemes) · sessions/*.json (state)
```

### Control flow (one research run)

1. **Frontend** sends `{type:"start", topic, max_steps}` over the WebSocket.
2. **ws_market** wraps the raw socket in `SafeWebSocket` (so concurrent sends can't
   interleave) and spawns `run_research_workflow`.
3. **executor**:
   - resets the token counter,
   - asks the **planner** for a 5-step plan (truncated to `max_steps`),
   - emits `plan`, then loops steps: `route_step()` maps each step to an agent
     (no LLM call needed), the agent runs, `step_start`/`step_end`/`token_usage`
     fire per step,
   - runs **writer** → **editor** once on all accumulated findings,
   - runs **simplifier** to build the plain-language document,
   - emits `done` (final JSON advisory + simplified report + token usage),
   - persists the session when a `session_id` was supplied.
4. **llm_client** tries providers in configured priority order, caches identical
   requests, tracks approximate tokens, and blacklists only *broken* models
   (404/endpoint errors), never rate-limited ones.
5. If every provider fails, each agent degrades to **heuristics.py** — the run
   still returns a valid advisory.

### WebSocket events

| Event | Direction | Description |
|---|---|---|
| `start` / `cancel` | Client → Server | Begin / cancel a run |
| `delete_session` / `export_session` | Client → Server | GDPR delete / export |
| `status`, `plan`, `step_start`, `step_end` | Server → Client | Progress updates |
| `token_usage` | Server → Client | Approx token counter `{input, output, total}` |
| `done` | Server → Client | `{topic, final_report, simplified_report, token_usage}` |
| `resume_available` | Server → Client | Prior session found for `session_id` |
| `cancelled`, `error`, `session_deleted`, `session_export` | Server → Client | Outcomes |

### LLM provider priority (free-first)

Configured via `LLM_PROVIDER_PRIORITY` in `backend/.env` (default
`ollama,huggingface,openrouter`). Each provider has its own fallback model list.
All calls go through `backend/core/llm_client.call_llm()` — agents never
hardcode a provider.

- **Per-agent models**: `AGENT_OPENROUTER_MODELS` in `backend/core/config.py`
  gives each agent a distinct leading OpenRouter model (load spread — no single
  model exhausts its free-tier quota), falling back to the shared
  `FALLBACK_MODELS` chain.
- **Key rotation**: `OPENROUTER_API_KEY_2` (in `backend/.env`) is auto-used on
  429/402/timeout and stays promoted while healthy.

### Voice pipeline (never raises)

- **STT**: ElevenLabs Scribe (if key) → SpeechRecognition/Google (WAV only).
- **TTS**: ElevenLabs (if key) → Hugging Face Inference API → pyttsx3 (offline).

### Realtime voice advisory (LiveKit, optional)

The browser talks directly to a LiveKit voice agent over WebRTC — speech stays
realtime, no record-and-upload round trip.

```
browser mic ──► LiveKit room ──► Silero STT (local) ──► AdvisoryLLM ──► ElevenLabs TTS ──► browser speakers
                                    (free, offline)      (call_llm) 
```

- **Agent worker** (separate process): `pip install -r backend/requirements-voice.txt`, then
  `python -m backend.voice_agent.worker`. Joins `LIVEKIT_ADVISOR_ROOM`.
- **Token endpoint**: `POST /api/voice/livekit-token` → `{url, token, room}`.
- **Frontend**: `LiveAdvisorPanel.tsx` (bottom of `/research`) — Start Voice / End Call / mute.
- **Backend creds** (`backend/.env`): `LIVEKIT_URL`, `LIVEKIT_API_KEY`,
  `LIVEKIT_API_SECRET` (free at https://cloud.livekit.io), reusing
  `ELEVENLABS_API_KEY` for the agent's voice.
- The advisory brain is the same `call_llm` multi-provider client (with the
  heuristic offline guarantee) — `agent_hint="voice"` gives it a short spoken
  style and its own model (`openrouter/auto`).

### Business Advisor Chat (with chat memory)

- **Specialist** (`backend/agents/chat.py`): business advisory & building —
  loan schemes, document packs, eligibility, and step-by-step business-building
  guidance. Off-topic questions get steered back to the business. **Multi-
  language**: replies follow the user — Hindi/Hinglish when they write in
  Devanagari (or the toggle is set to हिंदी), English otherwise; even the
  offline fallback speaks Hindi. Primary model is **open-source**
  (`mistralai/mistral-7b-instruct`); the call follows the normal free-first
  chain (Ollama → Hugging Face → OpenRouter) with a deterministic offline
  fallback.
- **Endpoints**:
  - `POST /api/chat` — body `{message, session_id?, topic?, lang?}` where `lang` ∈ `auto` (default) | `hi` | `en` → `{reply, session_id, history_count}`
  - `GET  /api/chat/history?session_id=` — remembered messages
  - `DELETE /api/chat/{session_id}` — clear chat memory (GDPR-aligned)
- **Memory**: per-session `backend/sessions/{session_id}_chat.json` (capped at
  `MAX_CHAT_MESSAGES`, covered by the 7-day retention cleanup). The session's
  latest advisory is injected automatically, so you can ask follow-ups about
  your own report.
- **Frontend**: `ChatPanel.tsx` on `/research` (bubbles, history restore,
  clear button, Auto/हिंदी/EN language toggle). `session_id` is generated
  browser-side and kept in `localStorage["grameenai_session"]` — the same id
  ties the research run, the chat, its export, and its delete together.

## 📁 Project Structure

```text
market-research-agent/
├── backend/                # FastAPI server
│   ├── agents/             # Planner, Research, Analyst, Opportunity, Writer, Editor, Simplifier
│   ├── api/                # WebSocket endpoint + voice HTTP endpoints
│   ├── workflows/          # Orchestration (executor) + static routing policy
│   ├── core/               # LLM client, heuristics, web_research, ws, memory, voice, config
│   └── data/               # Curated MSME scheme dataset
├── frontend/               # Next.js 15 application
│   ├── app/                # App Router pages
│   └── components/         # TopicInput, AgentTimeline, AdvisoryCard
└── assets/                 # Project media & screenshots
```

## 🚀 Getting Started

### 1. Prerequisites

- Python 3.9+
- Node.js 18+
- OpenRouter API Key

### 2. Backend Setup

1. **Navigate to the root directory.**
2. **Create and activate a virtual environment:**
   ```bash
   python -m venv backend/.venv
   # Windows
   .\backend\.venv\Scripts\activate
   # Linux/macOS
   source backend/.venv/bin/activate
   ```
3. **Install dependencies:**
   ```bash
   pip install -r backend/requirements.txt
   ```
4. **Configure Environment Variables:**
   Copy `backend/.env.example` to `backend/.env` and fill in optional keys
   (local mode needs no keys at all):
   ```env
   LLM_PROVIDER_PRIORITY=ollama,huggingface,openrouter
   # OPENROUTER_API_KEY=sk-or-v1-...   # only needed if 'openrouter' is in the priority
   ```
5. **Run the server:**
   ```bash
   uvicorn backend.main:app --reload --port 8000
   ```

### 3. Frontend Setup

1. **Navigate to the `frontend` directory:**
   ```bash
   cd frontend
   ```
2. **Install dependencies:**
   ```bash
   npm install
   ```
3. **Run the development server:**
   ```bash
   npm run dev
   ```
4. **Open your browser:** Go to `http://localhost:3000`.

## 🧠 Agentic Workflow

1. **Planner**: Breaks the business description into logical research steps.
2. **Researcher**: Gathers facts from curated scheme data + optional live web snippets.
3. **Analyst**: Converts the informal description into a monthly cash-flow snapshot.
4. **Opportunity Agent**: Matches MUDRA / CGTMSE / PMEGP / PM SVANidhi and names the one next step.
5. **Writer**: Drafts the structured advisory (JSON schema).
6. **Editor**: Polishes the advisory into plain, non-jargon language.
7. **Simplifier**: Produces the low-literacy "In Simple Words" document.

> Every agent is wrapped with a deterministic fallback — the flow always responds,
> even when all LLM providers are unavailable.

## 📄 License

This project is open-source and available under the [MIT License](LICENSE).

---

Built with ❤️ by [Janmejay Singh](https://github.com/JSR2406)
