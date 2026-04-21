from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "pro-ide-backend",
        "time": datetime.utcnow().isoformat() + "Z",
    }
