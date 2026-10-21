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
- LangChain / LangGraph: the advisory engine is **agentic** (`backend/agentic/`) — a LangGraph StateGraph (planner → supervisor → research/analyst/schemes → writer → critic/refine → finalize). LangChain and LangGraph are **required** dependencies (in `backend/requirements.txt`). All agent LLM calls use LCEL model chaining (`prompt | model | output_parser`) via `GrameenChatModel` + `build_advisory_chain()` / `build_json_advisory_chain()` / `run_prompt()` in `backend/core/langchain_adapter.py`. REST via `backend/api/langchain.py` (`GET /api/langchain/status` incl. agentic engine info, `POST /api/langchain/run`).
- Web research: googlesearch-python + httpx + BeautifulSoup (no keys, Google → DuckDuckGo fallback)

## Data & Accuracy Principles (non-negotiable)
Order of authority for every output the product produces:

**Official/verified data → deterministic rules/calculations → AI explanation → recommendation.**

- The LLM is NOT a source of truth. It may explain and recommend, never establish facts.
- Never let the model invent scheme names, loan amounts, interest rates, eligibility claims, or approval guarantees. Scheme data comes only from `backend/data/schemes.json` (curated, each entry with `source_url` + `last_verified_at`); amounts/eligibility shown to users must be traceable to that data or a cited source.
- **Eligibility is decided in code, never by the model.** `backend/core/eligibility.py` evaluates the `checks[]` predicates in `schemes.json` against the user's intake and returns `eligible | likely | blocked | not_eligible | wrong_tier`. The writer receives these verdicts as `eligibility_note` and is instructed not to contradict them. A verdict without a `basis` + `source_url` is a bug.
- Every financial or government-scheme claim shown to a user must carry its source (URL or "curated dataset" provenance). Where a number is computed (e.g. loan-ready score, cash-flow projection), the calculation must be deterministic code, not an LLM output.
- **Loan-ready score = f(user's real state), not f(report quality).** `backend/core/ledger.py` scores the Action Ledger — actions the user has actually completed, ticked via `POST /api/ledger/{session_id}`. The older `compute_loan_ready_score` rubric (which awarded points for the report containing a summary / five documents) is retained only as an offline fallback for sessions saved before the ledger existed. Never reintroduce report-quality scoring under the loan-ready label.
- Scores and projections: deterministic functions in `backend/core/heuristics.py` / `backend/core/ledger.py` / client-side calculators — never ask the LLM to compute them.
- **Intake answers are graded, not binary.** `coverage_report()` marks a field `unaddressed | thin | answered`; `next_probe()` re-asks the vaguest answer before moving to an untouched field. "some days" for earnings is half an answer, not an answer.
- Research provenance: `web_research.web_context()` records only pages it genuinely fetched (run-scoped `contextvars` sink set by `executor.run_research_workflow`); the executor attaches the deduped list to the advisory JSON under `sources` and ships it on the `done` event. LLM-written URLs never count as sources. Scheme lines carry their own `(Source: <url>, verified <date>)` annotation added deterministically by `annotate_scheme_sources()`.
- Offline guarantee: every agent must still produce usable output (heuristic tier) when all LLM providers are down. `/api/eligibility` and `/api/ledger` are fully deterministic and must keep answering with every provider offline.

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
│   │   ├── heuristics.py       # offline advisory tier + legacy report-quality score
│   │   ├── intake.py           # THE intake layer: field registry, normalize, canonical
│   │   │                       # snippet, graded coverage (unaddressed/thin/answered),
│   │   │                       # next_probe(), deterministic follow-up questions
│   │   ├── business.py         # deterministic business-class classification
│   │   │                       # (agriculture_crop / agriculture_allied / manufacturing /
│   │   │                       #  home_based / street_vending / trading / services / other)
│   │   ├── eligibility.py      # scheme rule engine over schemes.json `checks[]`
│   │   │                       # → eligible | likely | blocked | not_eligible | wrong_tier;
│   │   │                       # group_by_family() collapses MUDRA tiers into one card
│   │   ├── ledger.py           # Action Ledger + loan-ready score = f(actions completed)
│   │   ├── gates.py            # approval gates: gate model, decision validation, GateBroker
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
│   │   ├── executor.py         # thin adapter: runs the agentic graph, emits done, persists session + loan-ready score attach
│   │   └── routing.py          # legacy keyword step→agent mapping (kept for chat advisor classification)
│   ├── agentic/                # the agentic advisory engine (LangGraph)
│   │   ├── __init__.py         # public exports: run_agentic_workflow, EventEmitter, engine_name
│   │   ├── state.py            # AgenticState TypedDict + Annotated reducers + initial_state
│   │   ├── events.py           # EventEmitter (graph/plan/node_start/node_end/thought/tool_call/tool_result/reflection), WorkflowCancelled
│   │   ├── runtime.py          # LANGGRAPH_AVAILABLE / run_coro_sync / engine_name
│   │   ├── plan.py             # typed Plan IR: Step(id/node/tool/pre/post/fallback) + parse_plan_json
│   │   ├── compiler.py         # compile_plan() validates before any model call; default_plan() fallback; best_plan()
│   │   ├── executor.py         # run_plan(): preconditions → run → postconditions → fallback; never raises
│   │   ├── supervisor.py       # decide(): heuristic routing + guardrails (+LLM when up); ACTION_TO_NODE
│   │   ├── nodes.py            # planner, supervisor, research, analyst, schemes, writer, critic, refine, finalize (+NODE_META)
│   │   ├── graph.py            # topology + conditional routers + build_langgraph() + graph_topology()
│   │   ├── runner.py           # run_agentic_workflow; _run_langgraph (identical events/state)
│   │   └── tools.py            # deterministic tools: web_search, scheme_match, loan_ready_score, document_checklist, cashflow_projection (+langchain_tools())
│   ├── data/
│   │   └── schemes.json        # curated Indian MSME schemes (id, source_url, last_verified_at,
│   │                          #  eligibility_rules, documents, min/max_amount, checks[])
│   ├── sessions/               # runtime JSON stores (gitignored)
│   └── api/
│       ├── __init__.py
│       ├── schemas.py          # shared pydantic request/response models (response_model on every route)
│       ├── ws_market.py        # WS endpoint (start/cancel/export/delete) + input validation
│       ├── chat.py             # /api/chat (POST/GET history/DELETE) + chat memory, pydantic caps
│       ├── ledger.py           # /api/eligibility (rule engine) + /api/ledger/{session_id} (GET/POST)
│       ├── sessions.py         # GET /api/sessions/{session_id} — resume a saved advisory
│       ├── langchain.py        # GET /api/langchain/status, POST /api/langchain/run (heuristic fallback, never 500)
│       ├── whatsapp.py         # OPTIONAL WhatsApp Cloud API: GET verify, POST incoming → chat_agent → Graph reply (always 200)
│       └── voice.py            # /api/voice/{status,transcribe,speak,livekit-token}, 5 MB audio cap, WAV/MP3 sniffing
├── tests/
│   ├── test_smoke.py           # offline contracts, route surface, profile plumbing
│   └── test_security.py        # path traversal, WS/API input validation
└── frontend/
    ├── .env.local
    ├── package.json
    ├── lib/
    │   └── api.ts              # SINGLE source of API_BASE + WS_URL (never derive URLs elsewhere)
    │   ├── i18n.tsx            # site-wide language layer: dictionaries, LocaleProvider, useI18n()
    │   ├── intake.ts           # Business Check-up question registry, branching, label translation
    ├── app/
    │   ├── globals.css         # design tokens (:root vars), keyframes, prose
    │   ├── layout.tsx
    │   ├── page.tsx            # redirect → /research
    │   └── research/page.tsx   # WS client, run/cancel, report state
    └── components/
        ├── TopicInput.tsx      # text + voice input, step selector
        ├── LanguageSwitcher.tsx # site-wide language control (English / हिंदी)
        ├── AgentTimeline.tsx   # live agentic trace (nodes, thoughts, tool calls, reflections) + engine badge
        ├── AdvisoryCard.tsx    # advisory render, simplified doc, download/copy, listen
        ├── ChatPanel.tsx       # business advisory chatbot with saved chat memory
        ├── LiveAdvisorPanel.tsx # realtime voice (LiveKit): join room, mic, agent audio
        ├── StartupQuiz.tsx     # 6-question Business Check-up stepper incl. location (file name legacy; UI copy must say Business Check-up)
        ├── CashflowSimulator.tsx # client-side cash-flow projection + SVG chart
        ├── GateCard.tsx        # approval gate card (plan + schemes + approve/reject)
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
- LangChain rule: `GrameenChatModel` (in `backend/core/langchain_adapter.py`) wraps `call_llm` as a LangChain `BaseChatModel`. All agents use LCEL model chaining (`prompt | model | output_parser`) via `build_advisory_chain()` / `build_json_advisory_chain()` / `run_prompt()` — `run_prompt()` keeps the heuristic fallback so endpoints never hard-fail when the LLM is unreachable. LangChain and LangGraph are **required** dependencies (see `backend/requirements.txt`).

## Voice / TTS
- `backend/core/voice.py` — never raises, always falls back through:
  - STT: ElevenLabs Scribe (if key) → faster-whisper (open-source, local, no key; handles WebM + Hindi; model size via `WHISPER_MODEL_SIZE`, default `tiny`) → SpeechRecognition/Google (free, WAV only).
  - TTS: ElevenLabs (if key) → **Piper TTS** (open-source/local/MIT, no key; ONNX voices `en_US-lessac-medium` + `hi_IN-pratham-medium` auto-selected by Devanagari detection, one-time model download to `PIPER_VOICE_DIR` (default `backend/data/piper`, gitignored), fully offline after warm-up) → Hugging Face Inference API (`HF_TTS_MODEL`, default `facebook/mms-tts-eng`, free) → pyttsx3 (offline).
  - **Private-by-default:** when no `ELEVENLABS_API_KEY` is set, every engine is open-source and local — microphone audio never leaves the server. `voice_status()` reports engine availability; `GET /api/voice/status` exposes it and drives the frontend privacy chip in `TopicInput.tsx`.
  - Engine containers vary (MP3 from cloud tiers, RIFF/WAV from Piper) — `/api/voice/speak` sniffs the bytes and labels the media type correctly.
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

## Agentic Engine
- The advisory pipeline is a LangGraph StateGraph in `backend/agentic/` (topology + routers + nodes), executed by LangGraph. `engine` on `graph` and `done` events is always `"langgraph"`.
- Topology: `START → planner → supervisor`; supervisor routes to `research | analyst | schemes | writer | finalize` (heuristic `decide()` in `supervisor.py`, LLM-assisted when a provider is up). `research/analyst/schemes → supervisor` (they loop until the supervisor has enough). `writer → critic | refine`; `critic → writer (revise) | refine` for up to `AGENTIC_MAX_ITERATIONS`; `refine → finalize → END`.
- With the approval gate enabled the topology becomes `START → planner → gate → supervisor` — the gate node is **only wired into the compiled graph** when gates are on (`build_langgraph(gates_enabled=...)`), so a normal run's trace never shows a no-op node.
- Nodes degrade to deterministic heuristic outputs whenever the LLM fails — the offline guarantee applies to every node. Deterministic tools (`backend/agentic/tools.py`) are bound where relevant: `web_search` (research), `scheme_match` (schemes), `cashflow_projection` (analyst), `loan_ready_score` + `document_checklist` (finalize).
- `finalize` keeps the deterministic post-pass (`_finalize_report`): loan-ready score injection, scheme source annotation, provenance sources. Entity rule: planner/supervisor/critic routing and scores stay deterministic; the LLM only writes prose within the given schema.
- Config: `AGENTIC_ENGINE_ENABLED`, `AGENTIC_MAX_ITERATIONS` (default 8), `AGENTIC_REFLECTION_ENABLED` (default true), `AGENTIC_CHECKPOINTING`. `supervisor` and `critic` have their own token budgets + OpenRouter model priority (see `AGENT_OPENROUTER_MODELS` in `backend/core/config.py`); they use the same `call_llm` chain as all agents.

## WebSocket Events
Live agentic events: status, graph, plan, node_start, node_end, thought, tool_call, tool_result, reflection, token_usage

Approval-gate events: gate_pending, gate_decided, gate_paused

Terminal/legacy events: done (with simplified_report + trace + engine), cancelled, error, resume_available, session_deleted, session_export

- `start` payload: `{type, topic, max_steps?, session_id?, profile?, intake?, lang?, gates?}` — topic capped at 4000 chars, profile at 1500, `max_steps` coerced to 1–6, `session_id` validated against the allowlist (invalid → `error` event, no run), `gates` opts the run into the approval gate (also enabled deployment-wide by `GATES_ENABLED`).
- `gate_decision` payload: `{type, gate_id, decision, note?, session_id?}` — `decision` ∈ `approve | reject`, `note` capped at 500 chars, `gate_id` capped at 64. The decision is **persisted first** (so it survives a reload), then the parked run is woken; if nothing was parked, a fresh run is seeded from the stored topic + intake and the gate passes straight through.
- A malformed frame or unknown type yields an `error` event and the connection stays open.

## Security & Input Validation (P0 — do not regress)
- `session_id` is client-controlled and used for file paths. Validation lives in `backend/core/memory.py` (`is_valid_session_id`, allowlist `[A-Za-z0-9_-]{1,64}`); every write/delete entry point raises `ValueError` on invalid ids, reads return empty. WS + REST validate early and answer with friendly `error` events / 422s.
- Client-facing errors are friendly and generic (no `str(e)`, no stack traces, no server paths, no "port 8000" hints in production UI). **REST** has a unified JSON error contract (`detail` string): 422 for invalid input (single human message, validated via pydantic caps in `backend/api/schemas.py`), generic 500 JSON for anything uncaught — internals go to server logs only (`logger.exception` / `console.error`). **WS** errors are `error` events. Dev-only setup hints in the UI must be gated behind `process.env.NODE_ENV !== "production"`.
- All frontend URLs come from `frontend/lib/api.ts` (`API_BASE`, `WS_URL`) — never read `NEXT_PUBLIC_*` env vars elsewhere; the module handles http→https / ws→wss upgrades in one place.

## Observability
- **HTTP request log** — `backend/main.py` logs one line per request (`[http] METHOD /path -> status (ms)`); path only, never query strings/bodies/headers, so no PII enters logs. Uncaught exceptions still fall through to the global 500 handler which logs the trace.
- **Engine diagnostics** — `GET /api/voice/status` reports which STT/TTS engines are available + the active defaults (cheap spec probes, never starts models); drives the frontend privacy chip.
- Engine usage is always logged in `backend/core/voice.py` (e.g. `[Voice/TTS] piper voice '…' used`), so operators can audit which engine handled which request.

## Frontend Novelty Features
- **Loan-Ready Score** — a 0–100 score derived from the **Action Ledger** (`backend/core/ledger.py`): the things the user has actually done (Udyam registration, 6 months of statements, declared income, business vintage, a matched scheme, a ready document pack), each worth points with a reason and a consequence. Attached to the advisory JSON as `action_ledger` by `executor._finalize_report()`; `ActionLedger.tsx` renders the checklist and ticks items via `POST /api/ledger/{session_id}`, which recomputes the score immediately and persists it for the next run. The legacy report-quality rubric (`heuristics.compute_loan_ready_score`) is now only an offline fallback — never reintroduce it as the loan-ready score.
- **Eligibility Verdicts** (`backend/core/eligibility.py` + `EligibilityPanel.tsx`) — a deterministic rule engine over the `checks[]` predicates in `schemes.json`. Returns `eligible | likely | blocked | not_eligible | wrong_tier` per scheme family, each reason carrying the `basis` line it came from plus `source_url` + `last_verified_at`. Runs **before** any LLM call and is injected into the writer prompt as an override, so the prose cannot contradict it. MUDRA's four tiers collapse into one card with the recommended tier named. `POST /api/eligibility` exposes it standalone; the Business Check-up polls it (debounced) to show a live verdict while the user answers.
- **Cash-Flow Simulator** (`CashflowSimulator.tsx`) — pure client-side cash-flow projection (capital/weekly sales/weekly expenses, 4–24 weeks), SVG line chart, break-even week, monthly surplus. No backend calls.
- **Business Check-up** (`StartupQuiz.tsx` + `frontend/lib/intake.ts` + `backend/core/intake.py`) — the single intake layer. Every question keeps its quick chips **and** accepts a free-text answer ("I sell fruit near the bus stand in Nagpur" beats "Street vendor / cart"). Questions **branch** on earlier answers via `showIf`/`prompt`, so a farmer is asked what they grow and how much land they have. Persisted in `localStorage["grameenai_profile"]` (old chip-code format auto-migrated by `migrateIntake()`) and sent to the backend as structured `intake` (`{field_id: text}`) on both the WS `start` message and `POST /api/chat`. **The field ids in `frontend/lib/intake.ts` and `backend/core/intake.py` must match** — `tests/test_intake.py` fails if they drift. The backend builds the one canonical snippet from them (`build_intake_snippet`) and uses it for the run topic, synthesis, persistence and chat, so every surface reads the same intake. Coverage is graded (`unaddressed`/`thin`/`answered`) and the chat re-probes the vaguest answer before asking about an untouched field.
- **Resume last advisory** — page mount calls `GET /api/sessions/{session_id}` and restores the saved advisory (report + simplified + grey-out of run state) until the user runs again. Backend lives in `backend/api/sessions.py`.
- **Approval Gate** (`backend/core/gates.py` + `backend/agentic/nodes.py::gate_node` + `frontend/components/GateCard.tsx`) — a human approval gate between the planner and the research: the user sees the exact plan steps and the exact schemes (with `source_url` + `last_verified_at`) **before** anything is searched, then approves or rejects. The gate payload is deterministic (never model-written), the decision is persisted on the session before it is applied, and a run that nobody answers **parks** (no report, no failed run) so it can be decided later — `GET /api/sessions/{session_id}/gate` finds it again after a reload. Off by default; a run opts in with `gates: true` in the `start` payload or the deployment sets `GATES_ENABLED=true`. `GATE_WAIT_SECONDS` (default 180) bounds the in-process wait before the run parks.

## Planner / Executor (Phase B) — code decides, the model proposes
The advisory run is a **propose → dispose** loop, not a chatbot that talks its way through a task:

- `agentic/plan.py` — typed Plan IR. A `Step` names the graph node, the deterministic tool (if any), `pre` state keys that must hold, `post` keys that must be produced, and a `fallback` node. `parse_plan_json()` turns model output into a `Plan`, returning `None` on anything unusable.
- `agentic/compiler.py` — `compile_plan()` validates **before any model call is spent**: unique step ids, real graph nodes, real tools, real state keys, reachable pre/postconditions, valid fallbacks. `default_plan()` is the fallback topology; `best_plan()` prefers the candidate and falls back. Compilation never raises.
- `agentic/executor.py` — `run_plan()` runs a compiled plan transactionally: check preconditions → run → check postconditions → run fallback or record failure. Never raises; returns a `PlanRun` written to `state["plan_run"]`.
- `with_postconditions()` wraps every node so a step that claims success but produced nothing is recorded as **failed** in the trace.
- The **supervisor follows the compiled plan** when one exists (`_decide_with_plan`); with no plan it uses the heuristic `decide()` exactly as before — so a rejected plan costs the user nothing.
- LangGraph node wrappers must type `config` as `RunnableConfig`; a `Dict` hint makes LangGraph omit the config and the node then fails for lack of an emitter.

## Language (i18n) — non-negotiable rules
- `frontend/lib/i18n.tsx` is the **only** place user-facing UI copy lives. No hardcoded strings in components — every one resolves through `t()`. A language switch must change the *whole* site, not just the chat.
- Adding a language is one `DICT` entry plus one line in `LOCALES`; no component changes. A missing key falls back to English rather than rendering a raw key.
- **Official terms are never translated**: Udyam, GST, MUDRA, PMEGP, CGTMSE, PM SVANidhi, ElevenLabs. Users must recognise them on a bank form; only the sentence around them is translated. `tests/test_i18n.py` enforces this.
- Language also travels to the **backend**: the WS `start` message carries `lang` (validated against `VALID_LANGS`, anything unexpected falls back to English) so the writer, refiner and simplifier produce the advisory in the chosen language; `POST /api/eligibility` takes `lang` to return translated question wording, business-class labels and scheme rule labels (`label_hi` in `schemes.json`).
- Hindi answers are stored as the **English canonical label** and translated at render time (`optionLabel()`). Storing the displayed text would break every classification regex on the backend. `migrateIntake()` maps a Hindi-stored answer back to canonical, so switching language never loses an answer.
- **Encoding discipline:** Devanagari must survive every round-trip. Never rewrite a source file containing Hindi through PowerShell `Get-Content`/`Set-Content` (it re-encodes UTF-8 through the ANSI code page and produces mojibake such as `à¤¡à¥‡à¤¯à¤°`, which still parses, still passes tests, and ships broken). `tests/test_i18n.py::test_no_source_file_is_mojibake` scans the files that carry Devanagari; keep it green.
- The language handler lives in a long-lived WebSocket closure — read it through `tRef`, never the raw `t`, or a language switch tears down live connections.

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
