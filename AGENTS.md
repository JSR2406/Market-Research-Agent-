# Market Research Agent

## Stack
- Backend: Python, FastAPI, WebSockets, httpx, uvicorn, python-dotenv
- Frontend: Next.js 15 App Router, TypeScript, Tailwind CSS, Framer Motion, react-markdown, remark-gfm, lucide-react
- LLM: Multi-provider via backend/core/llm_client.py — Ollama (local, free), Hugging Face Inference API (free tier), OpenRouter (cloud)

## Folder Structure
market-research-agent/
├── backend/
│   ├── .env
│   ├── requirements.txt
│   ├── main.py
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   └── llm_client.py
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── planner.py
│   │   ├── research.py
│   │   ├── analyst.py
│   │   ├── opportunity.py
│   │   ├── writer.py
│   │   ├── editor.py
│   │   └── executor.py
│   └── api/
│       ├── __init__.py
│       └── ws_market.py
└── frontend/
    ├── .env.local
    ├── package.json
    ├── app/
    │   ├── layout.tsx
    │   ├── page.tsx
    │   └── research/page.tsx
    └── components/
        ├── TopicInput.tsx
        ├── AgentTimeline.tsx
        └── ReportViewer.tsx

## LLM Model Routing (all calls via backend/core/llm_client.py only)
- All agents route through `backend/core/llm_client.call_llm()` with a per-agent `agent_hint`.
- Provider priority (default `ollama,huggingface,openrouter`) is configurable via `LLM_PROVIDER_PRIORITY`.
  - **Ollama** (local) — completely free, no token limits: `OLLAMA_MODEL` (default `llama3.2:3b`).
  - **Hugging Face** — Inference API free tier: `HF_MODEL` (default `Qwen/Qwen2.5-7B-Instruct`).
  - **OpenRouter** — cloud fallback: uses `MODEL` + `FALLBACK_MODELS`.
- Agents never hardcode a provider; they just pass `agent_hint` and the client handles fallback.

## Voice / TTS
- `backend/core/voice.py` — never raises, always falls back through:
  - STT: ElevenLabs Scribe (if key) → SpeechRecognition/Google (free).
  - TTS: ElevenLabs (if key) → Hugging Face Inference API (`HF_TTS_MODEL`, default `facebook/mms-tts-eng`, free) → pyttsx3 (offline).

## WebSocket Events
plan, step_start, step_end, done, cancelled, error, status

## Rules
- Never hardcode API keys, always use os.getenv()
- All LLM calls only through backend/core/llm_client.py
- All React components must have "use client" at top
- Use Framer Motion for all animations
- Use lucide-react for all icons
- WebSocket connects to ws://localhost:8000/ws/market
- Use Windows PowerShell compatible commands only

## Data Retention & Privacy
- **Storage:** Research sessions are stored locally as JSON files in `backend/sessions/`.
- **Privacy:** Each session is isolated by `session_id`. Users can export their full session data or permanently delete their session using the `export_session` and `delete_session` WebSocket commands (GDPR right-to-delete).
- **Retention:** By default, sessions older than 7 days are automatically deleted on server startup by the `cleanup_old_sessions` hook in `main.py`.
