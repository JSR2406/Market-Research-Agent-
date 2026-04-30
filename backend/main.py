from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api.ws_market import router as ws_router

app = FastAPI(title="Market Research Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ws_router)

@app.get("/health")
async def health():
    return {"status": "ok"}
