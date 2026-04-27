from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.api import (  # noqa: E402
    benchmark,
    dashboard,
    diagnosis,
    extraction,
    finetune,
    finetune_chat,
    finetune_train,
    health,
    llm,
    opencompass,
    projects,
    workspace,
)

app = FastAPI(
    title="Pro-IDE Backend",
    description="FastAPI backend for Pro-IDE (ProDA workbench)",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://10.140.37.163:5174",
        "http://localhost:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(llm.router, prefix="/api/llm", tags=["llm"])
app.include_router(workspace.router, prefix="/api/workspace", tags=["workspace"])
app.include_router(extraction.router, prefix="/api/extraction", tags=["extraction"])
app.include_router(benchmark.router, prefix="/api/benchmark", tags=["benchmark"])
app.include_router(finetune.router, prefix="/api/finetune", tags=["finetune"])
app.include_router(diagnosis.router, prefix="/api/diagnosis", tags=["diagnosis"])
app.include_router(
    finetune_train.router, prefix="/api/finetune_train", tags=["finetune_train"]
)
app.include_router(finetune_chat.router, prefix="/api/finetune_chat", tags=["finetune_chat"])
app.include_router(opencompass.router, prefix="/api/opencompass", tags=["opencompass"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=8001, reload=True)
