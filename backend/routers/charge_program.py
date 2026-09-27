"""충전 STEP/SPEC 기준표(.xlsx) 업로드·조회 API.

팀장 피드백(2026-09-18) 반영: 형명·바이어별 충전 프로그램을 미리 등록해두고, 실제 X 인자
(charge_amount)가 이 기준 대비 얼마나 벗어났는지(charge_program_deviation_pct)를 1단·2단
회귀의 새 X 인자로 쓴다. 근거·범위는 `history/19_v1.1-충전step-cca-확장-계획.md` Phase B 참조.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile

from backend.db import repository as repo
from backend.etl.charge_program import parse_charge_program_workbook

router = APIRouter(prefix="/api", tags=["charge-program"])


@router.post("/charge-program/upload")
async def upload_charge_program(file: UploadFile):
    raw = await file.read()
    try:
        rows = parse_charge_program_workbook(raw)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"충전 프로그램 파일을 해석하지 못했습니다: {exc}") from exc
    if not rows:
        raise HTTPException(status_code=400, detail="인식 가능한 충전 프로그램 블록을 찾지 못했습니다.")

    conn = repo.get_connection()
    try:
        result = repo.replace_charge_program_specs(conn, rows, source_file=file.filename or "charge_program.xlsx")
        recompute_result = repo.recompute_all_lot_derived(conn)
    finally:
        conn.close()
    return {**result, **recompute_result}


@router.get("/charge-program")
def list_charge_program_specs():
    conn = repo.get_connection()
    try:
        return repo.get_charge_program_specs(conn)
    finally:
        conn.close()
