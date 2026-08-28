# Running the Market Research Agent — Local Development

## Prerequisites
- Python 3.11+ with a virtual environment in `backend/.venv`
- Node.js 18+ for the frontend
- An OpenRouter API key (free tier works): https://openrouter.ai/keys

---

## ⚠️ Critical: Always run uvicorn from the **project root**, NOT from inside `backend/`

The backend uses absolute Python package imports (`from backend.core.config import ...`).
Running uvicorn from inside `backend/` breaks these imports silently.

```powershell
# ✅ CORRECT — run from the project root (e.g. E:\CODING\Market Research Agent\)
cd "E:\CODING\Market Research Agent"
.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8000

# Or if using backend/.venv
backend\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8000

# ❌ WRONG — do NOT cd into backend/ first
cd backend
uvicorn main:app --reload   # will fail with ImportError
```

---

## Step-by-step setup (first time)

### 1. Create and activate the virtual environment

```powershell
cd "E:\CODING\Market Research Agent"
python -m venv backend\.venv
backend\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

### 2. Configure environment variables

```powershell
# Copy the example env file
Copy-Item backend\.env.example backend\.env

# Edit backend\.env and set your key:
#   OPENROUTER_API_KEY=sk-or-v1-...
notepad backend\.env
```

**The server will refuse to start (`sys.exit(1)`) if `OPENROUTER_API_KEY` is missing or empty.**

### 3. Start the backend

```powershell
# From project root:
backend\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8000
```

Confirm it's running: http://localhost:8000/health

### 4. Start the frontend (separate terminal)

```powershell
cd frontend
npm install   # first time only
npm run dev
```

Frontend: http://localhost:3000

---

## One-command start (PowerShell helper)

```powershell
# From project root — starts backend + frontend in separate windows
.\run.ps1
```

---

## Common failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `ImportError: No module named 'backend'` | uvicorn run from inside `backend/` | Run from project root |
| `FATAL: OPENROUTER_API_KEY is not set` | Missing `.env` file | Copy `.env.example` → `.env`, set key |
| `OSError: [Errno 98] Address already in use` | Port 8000 occupied | `netstat -ano \| findstr :8000` then kill the PID, or use `--port 8001` |
| `ModuleNotFoundError: No module named 'bs4'` | Requirements not installed | `pip install -r backend\requirements.txt` |
| 429 / token exhausted after a few runs | Free-tier OpenRouter rate limit | Wait ~1 hr, or add a paid model to `LLM_MODEL` in `.env` |

---

## WebSocket events reference

| Event type | Direction | Description |
|---|---|---|
| `start` | Client → Server | Begin research: `{type, topic, max_steps, session_id?}` |
| `cancel` | Client → Server | Cancel running workflow |
| `delete_session` | Client → Server | GDPR delete: `{type, session_id}` |
| `export_session` | Client → Server | Export stored data: `{type, session_id}` |
| `status` | Server → Client | Free-text progress message |
| `plan` | Server → Client | Array of planned steps |
| `step_start` | Server → Client | Agent starting a step |
| `step_end` | Server → Client | Agent finished a step + output |
| `token_usage` | Server → Client | Live token counter `{input, output, total}` |
| `resume_available` | Server → Client | Prior session found for session_id |
| `done` | Server → Client | Final report + token_usage summary |
| `cancelled` | Server → Client | Workflow was cancelled |
| `error` | Server → Client | Error message |
