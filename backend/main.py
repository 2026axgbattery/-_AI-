"""FastAPI 앱 엔트리. 기본은 127.0.0.1 전용 로컬 구동이며,
CORS 허용 origin은 ALLOWED_ORIGINS 환경변수(콤마 구분)로 확장 가능하다
(심사용 외부 배포 전환, .docs/37 참조 — 미설정 시 기존과 동일하게 localhost:3000만 허용).

실행(로컬): uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
실행(배포, 예: Render): uvicorn backend.main:app --host 0.0.0.0 --port $PORT
(반드시 저장소 루트에서 실행 — backend가 패키지로 import된다)
"""
import os

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

_extra_origins = [
    origin.strip()
    for origin in os.environ.get("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", *_extra_origins],
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
