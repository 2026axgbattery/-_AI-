"""SPEC 임계값(spec_lower_y/spec_lower_z) 업로드·조회 API.

⑤ SPEC 판정(Day 3 예정)이 참조할 `ConstantsByModel`을 미리 채워둘 수 있는 기반구조.
회귀 분석(③)은 이 테이블을 참조하지 않는다 — SPEC과 통계 분석을 분리하기로 한 결정
(history/12_spec-threshold-업로드-기반구조.md 참조).
"""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, HTTPException, UploadFile

from backend.db import repository as repo

router = APIRouter(prefix="/api", tags=["spec-thresholds"])


@router.post("/spec-thresholds/upload")
async def upload_spec_thresholds(file: UploadFile):
    raw = await file.read()
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)

    missing = repo.validate_columns(reader.fieldnames or [], repo.REQUIRED_SPEC_THRESHOLD_COLUMNS)
    if missing:
        raise HTTPException(status_code=400, detail={"missing_columns": missing})

    conn = repo.get_connection()
    try:
        result = repo.upsert_spec_thresholds(conn, rows)
    finally:
        conn.close()
    return {"row_count": len(rows), **result}


@router.get("/spec-thresholds")
def list_spec_thresholds():
    conn = repo.get_connection()
    try:
        return repo.get_spec_thresholds(conn)
    finally:
        conn.close()
