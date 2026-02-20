# src/api/server.py
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.api.state import get_state

app = FastAPI(title="Deriv Trading Bot API", version="0.1.0")


# CORS (frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/metrics")
def metrics():
    s = get_state()
    # dataclass -> dict
    return s.metrics.__dict__


@app.get("/events")
def events(limit: int = 200):
    s = get_state()
    return s.repo.list_events(limit=limit)


@app.get("/trades")
def trades(limit: int = 200):
    s = get_state()
    return s.repo.list_trades(limit=limit)


@app.get("/killswitch")
def killswitch():
    s = get_state()
    s.killswitch.load()
    return {"enabled": s.killswitch.state.enabled, "reason": s.killswitch.state.reason}


class KillSwitchPayload(BaseModel):
    reason: str = ""


@app.post("/killswitch/enable")
def enable_killswitch(payload: KillSwitchPayload):
    s = get_state()
    s.killswitch.state.enabled = True
    s.killswitch.state.reason = payload.reason or "manual"
    s.killswitch.save()
    return {"enabled": True, "reason": s.killswitch.state.reason}


@app.post("/killswitch/disable")
def disable_killswitch():
    s = get_state()
    s.killswitch.state.enabled = False
    s.killswitch.state.reason = ""
    s.killswitch.save()
    return {"enabled": False, "reason": ""}
