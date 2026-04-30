# Market Research Agent

This is a full-stack AI market research assistant built with Next.js 15, FastAPI, and OpenRouter AI. It features real-time, step-by-step market research capabilities using various sub-agents for planning, research, analysis, opportunity generation, and editing.

## Structure
- `/frontend`: Next.js 15 App Router frontend using Tailwind CSS and Framer Motion.
- `/backend`: FastAPI Python backend acting as a WebSocket server, orchestrating multiple AI agents.

## Setup Instructions

### 1. Backend
Open a terminal in the root `Market Research Agent` directory (not inside `/backend`).

1. Ensure the virtual environment is set up: `python -m venv backend/.venv`
2. Activate it: `.\backend\.venv\Scripts\activate`
3. Install dependencies: `pip install -r backend/requirements.txt`
4. Set up your `.env` file inside `backend/.env` with your `OPENROUTER_API_KEY`.
5. Run the FastAPI server from the root directory:
   ```bash
   uvicorn backend.main:app --reload --port 8000
   ```

*(Note: It is crucial to run uvicorn from the root directory so the `backend` module can be resolved correctly.)*

### 2. Frontend
Open another terminal in the `/frontend` directory.

1. Install dependencies: `npm install`
2. Start the development server:
   ```bash
   npm run dev
   ```

Visit the displayed localhost address (usually `http://localhost:3000` or `3001`) to interact with the Market Research Agent.

## Stack Details
Check `AGENTS.md` for architectural rules and specific models configured.
