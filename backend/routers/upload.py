"""① 업로드·매칭 + ② 수기입력(그룹 일괄 입력) API.

.docs/02_nextjs-fastapi-구현-아키텍처.md §3 화면-API 매핑 표의 `/upload` 화면에 대응.
"""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from backend.db import repository as repo
from backend.etl.process_raw import parse_process_raw_workbook
from backend.etl.test_raw import parse_test_raw_workbook

router = APIRouter(prefix="/api", tags=["upload"])

_RAW_EXCEL_EXTENSIONS = (".xls", ".xlsx")


def _read_csv_rows(raw_bytes: bytes) -> tuple[list[str], list[dict]]:
    text = raw_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    return reader.fieldnames or [], rows


def _is_raw_excel(filename: str | None) -> bool:
    return bool(filename) and filename.lower().endswith(_RAW_EXCEL_EXTENSIONS)


@router.post("/upload/process")
async def upload_process_csv(file: UploadFile):
    raw = await file.read()

    if _is_raw_excel(file.filename):
        rows = parse_process_raw_workbook(raw)
    else:
        fieldnames, rows = _read_csv_rows(raw)
        missing = repo.validate_columns(fieldnames, repo.REQUIRED_PROCESS_COLUMNS)
        if missing:
            raise HTTPException(status_code=400, detail={"missing_columns": missing})

    conn = repo.get_connection()
    try:
        result = repo.ingest_process_rows(conn, rows, filename=file.filename or "process_data.csv")
    finally:
        conn.close()
    return {"file": "process", "row_count": len(rows), **result}


@router.post("/upload/test")
async def upload_test_csv(file: UploadFile):
    raw = await file.read()

    if _is_raw_excel(file.filename):
        rows = parse_test_raw_workbook(raw)
    else:
        fieldnames, rows = _read_csv_rows(raw)
        missing = repo.validate_columns(fieldnames, repo.REQUIRED_TEST_COLUMNS)
        if missing:
            raise HTTPException(status_code=400, detail={"missing_columns": missing})

    conn = repo.get_connection()
    try:
        result = repo.ingest_test_rows(conn, rows, filename=file.filename or "test_data.csv")
    finally:
        conn.close()
    return {"file": "test", "row_count": len(rows), **result}


@router.get("/upload/summary")
def upload_summary():
    conn = repo.get_connection()
    try:
        return repo.get_upload_summary(conn)
    finally:
        conn.close()


@router.get("/upload/batches")
def list_upload_batches():
    conn = repo.get_connection()
    try:
        return repo.get_upload_batches(conn)
    finally:
        conn.close()


@router.delete("/upload/batches/{batch_id}")
def delete_upload_batch(batch_id: int):
    conn = repo.get_connection()
    try:
        return repo.delete_upload_batch(conn, batch_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        conn.close()


@router.delete("/upload/data")
def delete_all_upload_data():
    conn = repo.get_connection()
    try:
        return repo.delete_all_data(conn)
    finally:
        conn.close()


@router.get("/manual-fields/status")
def manual_fields_status():
    conn = repo.get_connection()
    try:
        return repo.get_manual_fields_status(conn)
    finally:
        conn.close()


@router.get("/manual-fields/groups")
def manual_field_groups(field: str):
    conn = repo.get_connection()
    try:
        return repo.get_manual_field_groups(conn, field)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        conn.close()


class ManualFieldBatchRequest(BaseModel):
    field: str
    group_values: dict
    value: float
    overwrite: bool = False


@router.put("/manual-fields/batch")
def manual_field_batch(payload: ManualFieldBatchRequest):
    conn = repo.get_connection()
    try:
        return repo.batch_update_manual_field(
            conn, payload.field, payload.group_values, payload.value, payload.overwrite
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        conn.close()


class ManualFieldsUpdate(BaseModel):
    electrolyte_temp: float | None = None
    charge_amount: float | None = None
    tank_temp: float | None = None


@router.get("/lots/{lot_id}/manual-fields")
def get_lot_manual_fields(lot_id: str):
    """개별 편집 API — docs/prd.md §10-20에 따라 화면에는 연결하지 않고 API만 존치."""
    conn = repo.get_connection()
    try:
        row = conn.execute(
            "SELECT lot_id, electrolyte_temp, charge_amount, tank_temp FROM ProcessData WHERE lot_id = ?",
            (lot_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="lot_id를 찾을 수 없습니다")
        return dict(row)
    finally:
        conn.close()


@router.put("/lots/{lot_id}/manual-fields")
def put_lot_manual_fields(lot_id: str, payload: ManualFieldsUpdate):
    """개별 편집 API — 화면에는 연결하지 않음(docs/prd.md §10-20). 값이 있는 항목만 덮어쓴다."""
    conn = repo.get_connection()
    try:
        existing = conn.execute("SELECT 1 FROM Lot WHERE lot_id = ?", (lot_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="lot_id를 찾을 수 없습니다")

        updates = {k: v for k, v in payload.model_dump().items() if v is not None}
        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(
                f"UPDATE ProcessData SET {set_clause} WHERE lot_id = ?",
                [*updates.values(), lot_id],
            )
            row = conn.execute(
                """
                SELECT p.fill_weight, p.water_loss, p.charge_amount, p.voltage_1st, p.voltage_2nd,
                       p.cell1_weight, p.cell2_weight, p.cell3_weight, p.cell4_weight,
                       p.cell5_weight, p.cell6_weight, l.rated_capacity
                FROM ProcessData p JOIN Lot l ON l.lot_id = p.lot_id WHERE p.lot_id = ?
                """,
                (lot_id,),
            ).fetchone()
            repo.upsert_lot_derived(conn, lot_id, dict(row))
            conn.commit()
        return {"lot_id": lot_id, "updated_fields": list(updates.keys())}
    finally:
        conn.close()
