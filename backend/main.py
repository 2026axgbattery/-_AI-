"""FastAPI 앱 엔트리. 127.0.0.1 전용, CORS는 로컬 Next.js dev 서버만 허용.

실행: uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
(반드시 저장소 루트에서 실행 — backend가 패키지로 import된다)
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.db import repository as repo
from backend.routers import (
    charge_program,
    dashboard,
    detail_analysis,
    prediction,
    scoring,
    spec_thresholds,
    upload,
)

app = FastAPI(title="AI 포화도 예측 시스템 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router)
app.include_router(spec_thresholds.router)
app.include_router(charge_program.router)
app.include_router(dashboard.router)
app.include_router(detail_analysis.router)
app.include_router(prediction.router)
app.include_router(scoring.router)


@app.on_event("startup")
def on_startup() -> None:
    repo.init_db()


@app.get("/api/health")
def health():
    return {"status": "ok"}
