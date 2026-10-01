"""① 업로드·매칭 + ② 수기입력(그룹 일괄 입력) API.

.docs/02_nextjs-fastapi-구현-아키텍처.md §3 화면-API 매핑 표의 `/upload` 화면에 대응.
"""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, HTTPException, Query, UploadFile
from pydantic import BaseModel

from backend.db import repository as repo
from backend.etl.process_raw import parse_process_raw_workbook
from backend.etl.test_raw import parse_test_raw_workbook

router = APIRouter(prefix="/api", tags=["upload"])

_RAW_EXCEL_EXTENSIONS = (".xls", ".xlsx")


def _decode_csv_bytes(raw_bytes: bytes) -> str:
    """엑셀/한글 툴에서 "다른 이름으로 저장"한 CSV는 cp949(EUC-KR)로 인코딩되는 경우가 흔하다
    (UTF-8이 아니면 무조건 실패하는 대신 순서대로 시도) — 전부 실패하면 400으로 명확히 안내한다."""
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise HTTPException(
        status_code=400,
        detail="CSV 파일의 인코딩을 인식할 수 없습니다(UTF-8/CP949만 지원). "
        "엑셀에서 'CSV UTF-8(쉼표로 분리)' 형식으로 다시 저장해 주세요.",
    )


def _read_csv_rows(raw_bytes: bytes) -> tuple[list[str], list[dict]]:
    text = _decode_csv_bytes(raw_bytes)
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    return reader.fieldnames or [], rows


def _is_raw_excel(filename: str | None) -> bool:
    return bool(filename) and filename.lower().endswith(_RAW_EXCEL_EXTENSIONS)


@router.post("/upload/process")
async def upload_process_csv(
    file: UploadFile,
    dry_run: bool = Query(False, description="true면 실제로 저장하지 않고 미리보기 요약만 반환(.docs/35)"),
):
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
        if not dry_run:
            repo.seed_charge_program_if_empty(conn)  # 기준표 없이 올라가 이탈도가 NULL이 되는 것 방지(.docs/41)
        result = repo.ingest_process_rows(
            conn, rows, filename=file.filename or "process_data.csv", dry_run=dry_run
        )
        coverage = None if dry_run else repo.get_charge_program_coverage(conn)
    finally:
        conn.close()
    return {"file": "process", "row_count": len(rows), **result, "charge_program_coverage": coverage}


@router.post("/upload/test")
async def upload_test_csv(
    file: UploadFile,
    dry_run: bool = Query(False, description="true면 실제로 저장하지 않고 미리보기 요약만 반환(.docs/35)"),
):
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
        result = repo.ingest_test_rows(
            conn, rows, filename=file.filename or "test_data.csv", dry_run=dry_run
        )
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
            # ProcessData는 append-only라 같은 lot_id가 여러 행을 가질 수 있다 — 로트당 최신
            # 행(id 최댓값)에만 적용해야 한다(그렇지 않으면 옛 행이 갱신되거나, 뒤이은
            # LotDerived 재계산이 옛 행 값을 읽어 Y가 조용히 잘못된 값으로 되돌아갈 수 있다).
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(
                f"""
                UPDATE ProcessData SET {set_clause}
                WHERE id = (SELECT MAX(id) FROM ProcessData WHERE lot_id = ?)
                """,
                [*updates.values(), lot_id],
            )
            row = conn.execute(
                """
                SELECT p.fill_weight, p.water_loss, p.charge_amount, p.voltage_1st, p.voltage_2nd,
                       p.cell1_weight, p.cell2_weight, p.cell3_weight, p.cell4_weight,
                       p.cell5_weight, p.cell6_weight, l.rated_capacity
                FROM ProcessData p JOIN Lot l ON l.lot_id = p.lot_id
                WHERE p.id = (SELECT MAX(id) FROM ProcessData WHERE lot_id = ?)
                """,
                (lot_id,),
            ).fetchone()
            repo.upsert_lot_derived(conn, lot_id, dict(row))
            conn.commit()
        return {"lot_id": lot_id, "updated_fields": list(updates.keys())}
    finally:
        conn.close()
