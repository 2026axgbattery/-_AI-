"""SQLite 연결·초기화·CRUD. `analysis/`는 이 모듈을 몰라도 되고, 라우터만 이 모듈을 호출한다.

append-only 원칙(.docs/03_sqlite-스키마-설계.md §1): ProcessData/TestData는 매 업로드마다
새 행을 추가한다(같은 lot_id 재업로드 시에도 기존 행을 지우지 않음). Lot은 lot_id가
PRIMARY KEY라 마스터 행은 1개만 유지하고(최초 업로드 값을 기준으로 함), 재업로드 시
동일 lot_id는 "중복"으로 집계해 응답에 경고로 포함한다(§8 "동일 lot_id가 재업로드됨").
"""
from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from backend.analysis.derive import (
    compute_lot_derived,
    extract_buyer_code_from_model_name,
    parse_rated_capacity_from_model_name,
)

# 데모/테스트 버전 분리(.docs/24, 2026-09-24, 튜터 조언 .docs/23 반영) — 환경변수 AX_DB_PROFILE이
# 없으면(기본값) 지금까지와 동일하게 app.db(데모 버전)를 쓴다. "test"로 지정하면 app_test.db(검증
# 전용)를 쓴다. 코드는 하나, DB 파일만 분리하는 방식으로 결정됨(.docs/22 §0).
_DB_PROFILE = os.environ.get("AX_DB_PROFILE", "demo")
_DB_FILENAME = "app.db" if _DB_PROFILE == "demo" else f"app_{_DB_PROFILE}.db"
DB_PATH = Path(__file__).resolve().parent / _DB_FILENAME
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

PROCESS_DATA_COLUMNS = [
    "cell1_weight", "cell2_weight", "cell3_weight", "cell4_weight", "cell5_weight", "cell6_weight",
    "cell1_ginap", "cell2_ginap", "cell3_ginap", "cell4_ginap", "cell5_ginap", "cell6_ginap",
    "fill_weight", "water_loss", "voltage_1st", "bath_no", "circuit_no",
    "soaking_time_sec", "aging_days", "voltage_2nd", "electrolyte_temp", "charge_amount", "tank_temp",
]
REQUIRED_PROCESS_COLUMNS = ["lot_id", "model_name", "prod_date", *PROCESS_DATA_COLUMNS]

TEST_DATA_COLUMNS = [
    "initial_voltage", "initial_resistance", "initial_weight", "initial_cca", "rated_capacity",
    "discharge_amount", "charge_amount_20h", "capacity_rate", "charge_rate", "mt_voltage", "mt_current",
    "sae_cca", "en_cca", "en_cca_10s_voltage", "en_cca_6v_hold_sec", "sae_cca_7v2_hold_sec",
]
# sae_cca/en_cca(history/19)와 CCA 규격판정용 체크포인트 3개(history/20)는 신뢰성 시험 raw
# data(xlsx)에서만 채워지는 값이라, 기존 test_data.csv 템플릿·CSV 업로드 경로는 이 컬럼 헤더가
# 없어도 그대로 동작해야 한다(fill_weight/water_loss와 동일한 "선택 컬럼" 철학) — CSV 업로드
# 필수 컬럼 목록에서는 제외한다.
OPTIONAL_TEST_COLUMNS = {
    "sae_cca", "en_cca", "en_cca_10s_voltage", "en_cca_6v_hold_sec", "sae_cca_7v2_hold_sec",
}
REQUIRED_TEST_COLUMNS = [
    "lot_id", *[c for c in TEST_DATA_COLUMNS if c not in OPTIONAL_TEST_COLUMNS]
]

REQUIRED_SPEC_THRESHOLD_COLUMNS = ["model_name", "spec_lower_y", "spec_lower_z"]

# 그룹 일괄 입력 대상 항목과 그룹화 기준(§6-②). charge_amount는 2026-09-21부터 형명·바이어별
# 충전 STEP 기준표(`ChargeProgramSpec`, history/19 Phase B)로 대체돼 그룹 일괄 입력 대상에서
# 제외됨(사용자 확인) — 개별 로트 수기입력 API(`PUT /lots/{lot_id}/manual-fields`)는 그대로 유지.
MANUAL_FIELDS = {
    "electrolyte_temp": ["model_name", "prod_date"],
    "tank_temp": ["model_name", "prod_date"],
}


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()


def validate_columns(fieldnames: Iterable[str], required: list[str]) -> list[str]:
    present = set(fieldnames)
    return [col for col in required if col not in present]


def _to_float(value: str | None) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    return float(value)


def create_upload_batch(conn: sqlite3.Connection, file_type: str, filename: str, row_count: int) -> int:
    cursor = conn.execute(
        "INSERT INTO UploadBatch (file_type, filename, row_count) VALUES (?, ?, ?)",
        (file_type, filename, row_count),
    )
    return cursor.lastrowid


def ingest_process_rows(conn: sqlite3.Connection, rows: list[dict], filename: str = "process_data.csv") -> dict:
    """process_data.csv 행들을 Lot+ProcessData에 반영하고, LotDerived까지 계산한다."""
    inserted_lots = 0
    duplicate_lot_ids: list[str] = []
    inserted_process_rows = 0
    batch_id = create_upload_batch(conn, "process", filename, len(rows))

    for raw in rows:
        lot_id = raw["lot_id"].strip()
        model_name = raw["model_name"].strip()
        prod_date = raw["prod_date"].strip()
        rated_capacity = parse_rated_capacity_from_model_name(model_name)

        existing = conn.execute("SELECT 1 FROM Lot WHERE lot_id = ?", (lot_id,)).fetchone()
        if existing:
            duplicate_lot_ids.append(lot_id)
        else:
            conn.execute(
                "INSERT INTO Lot (lot_id, model_name, rated_capacity, line_no, prod_date) "
                "VALUES (?, ?, ?, ?, ?)",
                (lot_id, model_name, rated_capacity, raw.get("line_no"), prod_date),
            )
            inserted_lots += 1

        process_values = {col: _to_float(raw.get(col)) for col in PROCESS_DATA_COLUMNS
                           if col not in ("bath_no", "circuit_no")}
        process_values["bath_no"] = raw.get("bath_no")
        process_values["circuit_no"] = raw.get("circuit_no")

        columns = ["lot_id", "upload_batch_id", *PROCESS_DATA_COLUMNS]
        placeholders = ", ".join(["?"] * len(columns))
        values = [lot_id, batch_id, *[process_values[c] for c in PROCESS_DATA_COLUMNS]]
        conn.execute(
            f"INSERT INTO ProcessData ({', '.join(columns)}) VALUES ({placeholders})", values
        )
        inserted_process_rows += 1

        buyer_code = extract_buyer_code_from_model_name(model_name)
        charge_program_total_ah = get_active_charge_program_total_ah(conn, rated_capacity, buyer_code)
        derived_input = {
            "fill_weight": process_values["fill_weight"],
            "water_loss": process_values["water_loss"],
            "rated_capacity": rated_capacity,
            "charge_amount": process_values["charge_amount"],
            "voltage_1st": process_values["voltage_1st"],
            "voltage_2nd": process_values["voltage_2nd"],
            "charge_program_total_ah": charge_program_total_ah,
            **{f"cell{i}_weight": process_values[f"cell{i}_weight"] for i in range(1, 7)},
        }
        upsert_lot_derived(conn, lot_id, derived_input)

    conn.commit()
    return {
        "batch_id": batch_id,
        "inserted_lots": inserted_lots,
        "duplicate_lot_ids": duplicate_lot_ids,
        "inserted_process_rows": inserted_process_rows,
    }


def ingest_test_rows(conn: sqlite3.Connection, rows: list[dict], filename: str = "test_data.csv") -> dict:
    inserted = 0
    skipped_unknown_lot: list[str] = []
    batch_id = create_upload_batch(conn, "test", filename, len(rows))

    for raw in rows:
        lot_id = raw["lot_id"].strip()
        lot_exists = conn.execute("SELECT 1 FROM Lot WHERE lot_id = ?", (lot_id,)).fetchone()
        if not lot_exists:
            # test_data.csv는 process_data.csv lot_id의 부분집합이 정상(docs/prd.md 더미 데이터 유의사항).
            # 그렇지 않은 lot_id는 FK 제약 위반을 막기 위해 건너뛰고 경고로만 알린다.
            skipped_unknown_lot.append(lot_id)
            continue

        values = {col: _to_float(raw.get(col)) for col in TEST_DATA_COLUMNS}
        columns = ["lot_id", "upload_batch_id", *TEST_DATA_COLUMNS]
        placeholders = ", ".join(["?"] * len(columns))
        row_values = [lot_id, batch_id, *[values[c] for c in TEST_DATA_COLUMNS]]
        conn.execute(
            f"INSERT INTO TestData ({', '.join(columns)}) VALUES ({placeholders})", row_values
        )
        inserted += 1

    conn.commit()
    return {"batch_id": batch_id, "inserted_test_rows": inserted, "skipped_unknown_lot": skipped_unknown_lot}


def get_active_charge_program_total_ah(
    conn: sqlite3.Connection, rated_capacity: float, buyer_code: str | None
) -> float | None:
    """(정격용량, 바이어 코드)에 매칭되는 충전 STEP 프로그램의 Total 충전량[Ah]을 찾는다.

    같은 조합에 기본·임시(변경) 버전이 같이 있으면 기본(is_variant=0)을 우선한다(history/19
    Phase B 확인). 정확히 매칭되는 바이어 코드가 없으면 그 용량군 전체에 적용되는 'All'
    코드로 한 번 더 시도한다(예: AGM90/AGM105_All). 그래도 없으면 None — 지어내지 않는다.
    """
    if buyer_code is None:
        return None
    for code in (buyer_code, "All"):
        row = conn.execute(
            "SELECT total_charge_ah FROM ChargeProgramSpec "
            "WHERE rated_capacity = ? AND buyer_code = ? "
            "ORDER BY is_variant ASC, id ASC LIMIT 1",
            (rated_capacity, code),
        ).fetchone()
        if row is not None and row["total_charge_ah"] is not None:
            return row["total_charge_ah"]
    return None


def replace_charge_program_specs(
    conn: sqlite3.Connection, rows: list[dict], source_file: str
) -> dict:
    """충전 STEP 프로그램 기준표 전체를 교체한다(참조 테이블이라 append-only 아님).

    Lot/ProcessData와 달리 이 표는 "형명·바이어별 현재 기준이 무엇인가"를 나타내는
    마스터 데이터라, 같은 파일을 재업로드하면 이전 내용을 지우고 새로 채운다.
    """
    conn.execute("DELETE FROM ChargeProgramSpec")
    for row in rows:
        conn.execute(
            """
            INSERT INTO ChargeProgramSpec (
                rated_capacity, buyer_code, program_label, is_variant,
                charge_hours, total_charge_ah, total_electricity_c, steps_json, source_file
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["rated_capacity"], row["buyer_code"], row["program_label"],
                int(row["is_variant"]), row.get("charge_hours"), row.get("total_charge_ah"),
                row.get("total_electricity_c"), row.get("steps_json"), source_file,
            ),
        )
    conn.commit()
    return {"program_row_count": len(rows)}


def get_charge_program_specs(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT rated_capacity, buyer_code, program_label, is_variant, charge_hours, "
        "total_charge_ah, total_electricity_c, source_file, ingested_at FROM ChargeProgramSpec "
        "ORDER BY rated_capacity, buyer_code, is_variant"
    ).fetchall()
    return [dict(r) for r in rows]


def recompute_all_lot_derived(conn: sqlite3.Connection) -> dict:
    """모든 로트의 LotDerived를 다시 계산한다. 충전 STEP 기준표를 새로 올렸을 때, 이미
    들어와 있던 로트들에도 이탈도(charge_program_deviation_pct)를 소급 반영하기 위함."""
    lots = conn.execute(
        """
        SELECT l.lot_id, l.model_name, l.rated_capacity, p.fill_weight, p.water_loss,
               p.charge_amount, p.voltage_1st, p.voltage_2nd,
               p.cell1_weight, p.cell2_weight, p.cell3_weight,
               p.cell4_weight, p.cell5_weight, p.cell6_weight
        FROM Lot l JOIN ProcessData p ON p.lot_id = l.lot_id
        """
    ).fetchall()
    updated = 0
    for lot in lots:
        row = dict(lot)
        buyer_code = extract_buyer_code_from_model_name(row["model_name"])
        charge_program_total_ah = get_active_charge_program_total_ah(
            conn, row["rated_capacity"], buyer_code
        )
        derived_input = {
            "fill_weight": row["fill_weight"],
            "water_loss": row["water_loss"],
            "rated_capacity": row["rated_capacity"],
            "charge_amount": row["charge_amount"],
            "voltage_1st": row["voltage_1st"],
            "voltage_2nd": row["voltage_2nd"],
            "charge_program_total_ah": charge_program_total_ah,
            **{f"cell{i}_weight": row[f"cell{i}_weight"] for i in range(1, 7)},
        }
        upsert_lot_derived(conn, row["lot_id"], derived_input)
        updated += 1
    conn.commit()
    return {"recomputed_lots": updated}


def upsert_lot_derived(conn: sqlite3.Connection, lot_id: str, derived_input: dict) -> None:
    derived = compute_lot_derived(derived_input)
    conn.execute(
        """
        INSERT INTO LotDerived (
            lot_id, retention_rate, water_loss_rate, water_loss_per_ah, theoretical_water_loss,
            water_loss_residual, fill_per_rated, charge_ratio, cell_weight_mean, cell_weight_std,
            formation_dv, saturation_calc, saturation_basis, saturation_source,
            charge_program_deviation_pct, derived_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(lot_id) DO UPDATE SET
            retention_rate=excluded.retention_rate,
            water_loss_rate=excluded.water_loss_rate,
            water_loss_per_ah=excluded.water_loss_per_ah,
            theoretical_water_loss=excluded.theoretical_water_loss,
            water_loss_residual=excluded.water_loss_residual,
            fill_per_rated=excluded.fill_per_rated,
            charge_ratio=excluded.charge_ratio,
            cell_weight_mean=excluded.cell_weight_mean,
            cell_weight_std=excluded.cell_weight_std,
            formation_dv=excluded.formation_dv,
            saturation_calc=excluded.saturation_calc,
            saturation_basis=excluded.saturation_basis,
            saturation_source=excluded.saturation_source,
            charge_program_deviation_pct=excluded.charge_program_deviation_pct,
            derived_at=datetime('now')
        """,
        (
            lot_id, derived["retention_rate"], derived["water_loss_rate"], derived["water_loss_per_ah"],
            derived["theoretical_water_loss"], derived["water_loss_residual"], derived["fill_per_rated"],
            derived["charge_ratio"], derived["cell_weight_mean"], derived["cell_weight_std"],
            derived["formation_dv"], derived["saturation_calc"], derived["saturation_basis"],
            derived["saturation_source"], derived["charge_program_deviation_pct"],
        ),
    )


def get_upload_summary(conn: sqlite3.Connection) -> dict:
    total_lots = conn.execute("SELECT COUNT(*) AS n FROM Lot").fetchone()["n"]
    matched = conn.execute(
        "SELECT COUNT(DISTINCT lot_id) AS n FROM TestData"
    ).fetchone()["n"]
    unmatched = total_lots - matched
    match_rate = round(matched / total_lots * 100, 1) if total_lots else 0.0

    preview_rows = conn.execute(
        """
        SELECT l.lot_id, l.model_name,
               1 AS has_process,
               CASE WHEN t.lot_id IS NULL THEN 0 ELSE 1 END AS has_test
        FROM Lot l
        LEFT JOIN TestData t ON t.lot_id = l.lot_id
        ORDER BY l.ingested_at DESC
        LIMIT 8
        """
    ).fetchall()

    return {
        "total_lots": total_lots,
        "matched": matched,
        "unmatched": unmatched,
        "match_rate": match_rate,
        "preview_rows": [dict(r) for r in preview_rows],
    }


def get_manual_fields_status(conn: sqlite3.Connection) -> dict:
    """그룹 일괄 입력 대상 항목(electrolyte_temp/tank_temp) 중 하나라도 비어 있는 로트 목록.
    1단(X→Y) 분석 대상에서 제외되는 로트를 화면에 안내하기 위한 집계(§6-②). charge_amount는
    더 이상 이 완료 여부 판단에 포함하지 않음(MANUAL_FIELDS 주석 참조) — 다만 charge_amount가
    비어 있으면 1단 회귀 학습 대상에서는 여전히 실제로 제외된다(`get_x_to_y_training_rows` 등의
    별도 `WHERE p.charge_amount IS NOT NULL` 조건, 이 함수와는 독립적).

    ProcessData는 append-only라 같은 lot_id가 여러 행(중복 재업로드, 실제 raw data의 재시험
    등)을 가질 수 있다 — 로트당 최신 행(id 최댓값)만 완료 여부 판단에 반영한다(그렇지 않으면
    행 수가 로트 수보다 많아져 completeness가 왜곡됨, 2026-09-11 실데이터 검증 중 발견).
    """
    total_lots = conn.execute("SELECT COUNT(*) AS n FROM Lot").fetchone()["n"]
    incomplete_rows = conn.execute(
        """
        SELECT p.lot_id FROM ProcessData p
        JOIN (SELECT lot_id, MAX(id) AS latest_id FROM ProcessData GROUP BY lot_id) latest
          ON latest.latest_id = p.id
        WHERE p.electrolyte_temp IS NULL OR p.tank_temp IS NULL
        """
    ).fetchall()
    incomplete_lot_ids = [r["lot_id"] for r in incomplete_rows]
    return {
        "total_lots": total_lots,
        "incomplete_lot_ids": incomplete_lot_ids,
        "complete_lots": total_lots - len(incomplete_lot_ids),
    }


def get_manual_field_groups(conn: sqlite3.Connection, field: str) -> list[dict]:
    """로트당 최신 ProcessData 행만 집계한다(get_manual_fields_status와 동일한 이유)."""
    if field not in MANUAL_FIELDS:
        raise ValueError(f"지원하지 않는 수기입력 항목입니다: {field}")
    group_keys = MANUAL_FIELDS[field]
    group_cols = ", ".join(f"l.{k}" for k in group_keys)
    rows = conn.execute(
        f"""
        SELECT {group_cols},
               COUNT(*) AS total,
               SUM(CASE WHEN p.{field} IS NULL THEN 1 ELSE 0 END) AS missing
        FROM Lot l
        JOIN (SELECT lot_id, MAX(id) AS latest_id FROM ProcessData GROUP BY lot_id) latest
          ON latest.lot_id = l.lot_id
        JOIN ProcessData p ON p.id = latest.latest_id
        GROUP BY {group_cols}
        ORDER BY {group_cols}
        """
    ).fetchall()
    return [dict(r) for r in rows]


def batch_update_manual_field(
    conn: sqlite3.Connection, field: str, group_values: dict, value: float, overwrite: bool = False
) -> dict:
    """group_values의 그룹 키와 일치하는 로트에 값을 반영한다.

    기본(overwrite=False)은 field가 NULL인 로트에만 적용(미입력만 채움). overwrite=True면
    이미 값이 있는 로트도 덮어쓴다 — 화면에서 사용자가 확인 다이얼로그를 거친 뒤에만
    이 플래그를 True로 보내야 한다(docs/prd.md §6-② "실수로 덮어쓰지 않도록 확인 다이얼로그").
    """
    if field not in MANUAL_FIELDS:
        raise ValueError(f"지원하지 않는 수기입력 항목입니다: {field}")
    group_keys = MANUAL_FIELDS[field]
    where_group = " AND ".join(f"l.{k} = ?" for k in group_keys)
    params = [group_values[k] for k in group_keys]
    null_filter = "" if overwrite else f" AND p.{field} IS NULL"

    # ProcessData는 append-only라 같은 lot_id가 여러 행을 가질 수 있어 SELECT DISTINCT로
    # 중복을 제거한다(중복이 남으면 아래 UPDATE는 idempotent해 무해하지만, LotDerived 재계산
    # 루프가 같은 로트를 불필요하게 여러 번 처리하게 된다).
    target_lot_ids = [
        r["lot_id"]
        for r in conn.execute(
            f"""
            SELECT DISTINCT p.lot_id FROM ProcessData p JOIN Lot l ON l.lot_id = p.lot_id
            WHERE {where_group}{null_filter}
            """,
            params,
        ).fetchall()
    ]
    if target_lot_ids:
        placeholders = ", ".join(["?"] * len(target_lot_ids))
        conn.execute(
            f"UPDATE ProcessData SET {field} = ? WHERE lot_id IN ({placeholders})",
            [value, *target_lot_ids],
        )
        # electrolyte_temp/tank_temp는 LotDerived 파생값 계산식에 쓰이지 않으므로(§6-③ 산출식
        # 참조) 재계산이 필요 없다 — charge_amount(파생값에 쓰임)가 그룹 일괄 입력 대상이던
        # 시절엔 여기서 재계산했으나 MANUAL_FIELDS에서 제외되며 해당 분기도 함께 제거됨.
        conn.commit()
    return {"field": field, "updated_lot_ids": target_lot_ids}


def upsert_spec_thresholds(conn: sqlite3.Connection, rows: list[dict]) -> dict:
    """SPEC 임계값(spec_lower_y/spec_lower_z) CSV를 ConstantsByModel에 반영한다.

    회귀 로직(analysis/regression.py)은 이 테이블을 참조하지 않는다 — SPEC은 ⑤ 판정
    단계에서만 쓰이므로(사용자 결정, 2026-09-10), 이 업로드는 통계 분석에 영향을 주지 않는다.
    담당자 확인 전(docs/prd.md §10-11)이라 값이 비어 있어도(NULL) 오류 없이 저장된다.
    """
    updated_models: list[str] = []
    for raw in rows:
        model_name = raw["model_name"].strip()
        if not model_name:
            continue
        rated_capacity = _to_float(raw.get("rated_capacity"))
        if rated_capacity is None:
            rated_capacity = parse_rated_capacity_from_model_name(model_name)
        spec_lower_y = _to_float(raw.get("spec_lower_y"))
        spec_lower_z = _to_float(raw.get("spec_lower_z"))

        conn.execute(
            """
            INSERT INTO ConstantsByModel (model_name, rated_capacity, spec_lower_y, spec_lower_z)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(model_name) DO UPDATE SET
                rated_capacity=excluded.rated_capacity,
                spec_lower_y=excluded.spec_lower_y,
                spec_lower_z=excluded.spec_lower_z
            """,
            (model_name, rated_capacity, spec_lower_y, spec_lower_z),
        )
        updated_models.append(model_name)
    conn.commit()
    return {"updated_models": updated_models}


def get_spec_thresholds(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT model_name, rated_capacity, spec_lower_y, spec_lower_z FROM ConstantsByModel "
        "ORDER BY model_name"
    ).fetchall()
    return [dict(r) for r in rows]


def get_upload_batches(conn: sqlite3.Connection) -> list[dict]:
    """업로드 이력 목록(.docs/13) — 화면에서 파일 단위로 확인·선택 삭제하기 위한 조회.

    `row_count`는 업로드 당시 건수(고정 기록), `remaining_row_count`는 그 뒤 다른 배치의
    "process 삭제 → 고아 로트 정리"로 함께 지워졌을 수 있는 현재 남은 건수(실시간 조회)다.
    """
    rows = conn.execute(
        "SELECT batch_id, file_type, filename, row_count, uploaded_at FROM UploadBatch "
        "ORDER BY uploaded_at DESC, batch_id DESC"
    ).fetchall()
    result = []
    for r in rows:
        row = dict(r)
        table = "ProcessData" if row["file_type"] == "process" else "TestData"
        remaining = conn.execute(
            f"SELECT COUNT(*) AS n FROM {table} WHERE upload_batch_id = ?", (row["batch_id"],)
        ).fetchone()["n"]
        row["remaining_row_count"] = remaining
        result.append(row)
    return result


_ORPHAN_LOT_CLEANUP_TABLES = (
    # FK 순서 준수: SpecJudgment/CauseDiagnosis가 Prediction.prediction_id를 참조하므로
    # Prediction보다 먼저 지운다(PRAGMA foreign_keys = ON).
    "CauseDiagnosis", "SpecJudgment", "Prediction", "ScoringResult", "TestData", "LotDerived", "Lot",
)


def delete_upload_batch(conn: sqlite3.Connection, batch_id: int) -> dict:
    """업로드 이력 1건을 선택 삭제한다(.docs/13).

    'test' 배치는 해당 TestData 행만 지우면 끝난다(Lot/ProcessData는 그대로 유지).
    'process' 배치는 그 배치로 들어온 ProcessData 행을 지운 뒤, 로트별로 남은 ProcessData가
    있으면 그 값으로 LotDerived를 재계산하고, 하나도 안 남으면 고아 로트로 보고
    Lot/LotDerived/TestData/Prediction/SpecJudgment/CauseDiagnosis까지 함께 정리한다
    (append-only 원칙과는 별개인, 사용자가 명시적으로 요청한 되돌리기 조작).

    **2026-09-26 성능 수정**: 고아 로트 정리를 로트 1건당 SQL 7~8건씩 Python 루프로 돌리던
    이전 구현은 로트 수만 건 규모(예: 1만 건짜리 더미 배치)에서 실측 27초가 걸려, 프런트에서
    응답을 기다리다 못해 "Failed to fetch"로 오인되는 원인이었다(사용자 실측 보고). 고아 로트
    판정과 정리를 테이블당 단일 `DELETE ... WHERE lot_id IN (SELECT ...)`로 일괄 처리해
    로트 수와 무관하게 항상 빠르게 끝나도록 바꿨다 — 파생값을 다시 계산해야 하는(=이 배치
    삭제 후에도 다른 배치의 ProcessData가 남아있는) 로트만 예외적으로 로트 단위 루프가 남는다.
    """
    batch = conn.execute("SELECT * FROM UploadBatch WHERE batch_id = ?", (batch_id,)).fetchone()
    if batch is None:
        raise ValueError(f"업로드 이력을 찾을 수 없습니다: {batch_id}")
    file_type = batch["file_type"]
    orphaned_lot_count = 0

    if file_type == "test":
        conn.execute("DELETE FROM TestData WHERE upload_batch_id = ?", (batch_id,))
    else:
        conn.execute("DROP TABLE IF EXISTS temp.affected_lots")
        conn.execute(
            "CREATE TEMP TABLE affected_lots AS "
            "SELECT DISTINCT lot_id FROM ProcessData WHERE upload_batch_id = ?",
            (batch_id,),
        )
        conn.execute("DELETE FROM ProcessData WHERE upload_batch_id = ?", (batch_id,))

        conn.execute("DROP TABLE IF EXISTS temp.orphan_lots")
        conn.execute(
            "CREATE TEMP TABLE orphan_lots AS "
            "SELECT lot_id FROM affected_lots "
            "WHERE lot_id NOT IN (SELECT lot_id FROM ProcessData)"
        )
        orphaned_lot_count = conn.execute("SELECT COUNT(*) AS n FROM orphan_lots").fetchone()["n"]

        for table in _ORPHAN_LOT_CLEANUP_TABLES:
            conn.execute(f"DELETE FROM {table} WHERE lot_id IN (SELECT lot_id FROM orphan_lots)")

        remaining_lot_ids = [
            r["lot_id"]
            for r in conn.execute(
                "SELECT lot_id FROM affected_lots WHERE lot_id NOT IN (SELECT lot_id FROM orphan_lots)"
            ).fetchall()
        ]
        for lot_id in remaining_lot_ids:
            remaining = conn.execute(
                "SELECT * FROM ProcessData WHERE lot_id = ? ORDER BY ingested_at DESC LIMIT 1",
                (lot_id,),
            ).fetchone()
            lot = conn.execute(
                "SELECT rated_capacity, model_name FROM Lot WHERE lot_id = ?", (lot_id,)
            ).fetchone()
            buyer_code = extract_buyer_code_from_model_name(lot["model_name"])
            charge_program_total_ah = get_active_charge_program_total_ah(
                conn, lot["rated_capacity"], buyer_code
            )
            derived_input = {
                "fill_weight": remaining["fill_weight"],
                "water_loss": remaining["water_loss"],
                "rated_capacity": lot["rated_capacity"],
                "charge_amount": remaining["charge_amount"],
                "voltage_1st": remaining["voltage_1st"],
                "voltage_2nd": remaining["voltage_2nd"],
                "charge_program_total_ah": charge_program_total_ah,
                **{f"cell{i}_weight": remaining[f"cell{i}_weight"] for i in range(1, 7)},
            }
            upsert_lot_derived(conn, lot_id, derived_input)

        conn.execute("DROP TABLE affected_lots")
        conn.execute("DROP TABLE orphan_lots")

    conn.execute("DELETE FROM UploadBatch WHERE batch_id = ?", (batch_id,))
    conn.commit()
    return {"batch_id": batch_id, "file_type": file_type, "orphaned_lot_count": orphaned_lot_count}


def delete_all_data(conn: sqlite3.Connection) -> dict:
    """업로드·매칭·수기입력·분석 관련 데이터를 전부 초기화한다(.docs/13 "전체 삭제").

    SPEC 임계값(`ConstantsByModel`)은 별도 업로드 경로(`/api/spec-thresholds/*`)로 관리되므로
    이 초기화 범위에 포함하지 않는다.
    """
    for table in (
        "ScoringResult", "ScoringRun",
        "CauseDiagnosis", "SpecJudgment", "Prediction", "AnalysisRun",
        "LotDerived", "TestData", "ProcessData", "Lot", "UploadBatch",
    ):
        conn.execute(f"DELETE FROM {table}")
    conn.commit()
    return {"status": "all_upload_data_deleted"}


# =========================================================
# Day 2 — 1·2단 회귀(③-1/③-2) 학습 데이터 조회 + AnalysisRun 저장/조회
# =========================================================

def get_x_to_y_training_rows(conn: sqlite3.Connection) -> list[dict]:
    """1단(X→Y) 학습 대상: 수기입력 3항목이 모두 채워졌고 Y(retention_rate)가 계산된 로트.

    ProcessData는 append-only라 같은 lot_id가 여러 행을 가질 수 있어 로트당 최신 행만
    사용한다(get_manual_fields_status와 동일한 이유, .docs/03 2026-09-11 두 번째 추가 참조).
    """
    rows = conn.execute(
        """
        SELECT l.lot_id, p.electrolyte_temp, p.tank_temp, p.soaking_time_sec, p.aging_days,
               d.formation_dv, d.cell_weight_mean, d.cell_weight_std, d.charge_ratio,
               d.charge_program_deviation_pct, d.retention_rate
        FROM Lot l
        JOIN (SELECT lot_id, MAX(id) AS latest_id FROM ProcessData GROUP BY lot_id) latest_p
          ON latest_p.lot_id = l.lot_id
        JOIN ProcessData p ON p.id = latest_p.latest_id
        JOIN LotDerived d ON d.lot_id = l.lot_id
        WHERE p.electrolyte_temp IS NOT NULL AND p.charge_amount IS NOT NULL
          AND p.tank_temp IS NOT NULL AND d.retention_rate IS NOT NULL
        """
    ).fetchall()
    return [dict(r) for r in rows]


def get_xy_to_z_training_rows(conn: sqlite3.Connection) -> list[dict]:
    """2단(X+Y→Z)·베이스라인(X→Z) 학습 대상: 위 조건 + 시험(TestData) 매칭 로트만(실측 Y로 학습)."""
    rows = conn.execute(
        """
        SELECT l.lot_id, p.electrolyte_temp, p.tank_temp, p.soaking_time_sec, p.aging_days,
               d.formation_dv, d.cell_weight_mean, d.cell_weight_std, d.charge_ratio,
               d.charge_program_deviation_pct, d.retention_rate, t.discharge_amount
        FROM Lot l
        JOIN (SELECT lot_id, MAX(id) AS latest_id FROM ProcessData GROUP BY lot_id) latest_p
          ON latest_p.lot_id = l.lot_id
        JOIN ProcessData p ON p.id = latest_p.latest_id
        JOIN LotDerived d ON d.lot_id = l.lot_id
        JOIN (SELECT lot_id, MAX(id) AS latest_id FROM TestData GROUP BY lot_id) latest_t
          ON latest_t.lot_id = l.lot_id
        JOIN TestData t ON t.id = latest_t.latest_id
        WHERE p.electrolyte_temp IS NOT NULL AND p.charge_amount IS NOT NULL
          AND p.tank_temp IS NOT NULL AND d.retention_rate IS NOT NULL
          AND t.discharge_amount IS NOT NULL
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _get_xy_to_cca_training_rows(conn: sqlite3.Connection, cca_column: str) -> list[dict]:
    """2단(X+Y→CCA) 학습 대상 공통 구현(history/19 Phase C). `cca_column`은 'sae_cca'|'en_cca'만
    허용 — 반드시 하드코딩된 값으로만 호출해 SQL 인젝션 여지를 없앤다."""
    if cca_column not in ("sae_cca", "en_cca"):
        raise ValueError(f"지원하지 않는 CCA 컬럼입니다: {cca_column!r}")
    rows = conn.execute(
        f"""
        SELECT l.lot_id, p.electrolyte_temp, p.tank_temp, p.soaking_time_sec, p.aging_days,
               d.formation_dv, d.cell_weight_mean, d.cell_weight_std, d.charge_ratio,
               d.charge_program_deviation_pct, d.retention_rate, t.{cca_column} AS {cca_column}
        FROM Lot l
        JOIN (SELECT lot_id, MAX(id) AS latest_id FROM ProcessData GROUP BY lot_id) latest_p
          ON latest_p.lot_id = l.lot_id
        JOIN ProcessData p ON p.id = latest_p.latest_id
        JOIN LotDerived d ON d.lot_id = l.lot_id
        JOIN (SELECT lot_id, MAX(id) AS latest_id FROM TestData GROUP BY lot_id) latest_t
          ON latest_t.lot_id = l.lot_id
        JOIN TestData t ON t.id = latest_t.latest_id
        WHERE p.electrolyte_temp IS NOT NULL AND p.charge_amount IS NOT NULL
          AND p.tank_temp IS NOT NULL AND d.retention_rate IS NOT NULL
          AND t.{cca_column} IS NOT NULL
        """
    ).fetchall()
    return [dict(r) for r in rows]


def get_xy_to_sae_cca_training_rows(conn: sqlite3.Connection) -> list[dict]:
    """2단(X+Y→SAE CCA) 학습 대상(history/19 Phase C) — 현재 신뢰성 배치 표본 극히 적음(n=2)."""
    return _get_xy_to_cca_training_rows(conn, "sae_cca")


def get_xy_to_en_cca_training_rows(conn: sqlite3.Connection) -> list[dict]:
    """2단(X+Y→EN CCA) 학습 대상(history/19 Phase C) — 현재 신뢰성 배치 표본 극히 적음(n=2)."""
    return _get_xy_to_cca_training_rows(conn, "en_cca")


def get_y_vs_cca_pairs(conn: sqlite3.Connection) -> list[dict]:
    """포화도(Y)와 SAE/EN CCA의 관계 확인용 로트별 쌍(팀장 피드백 — 상세 회귀가 아니라 단순
    산점도/참고 비교 목적, history/19 Phase C). CCA 값이 하나라도 있는 로트만 반환."""
    rows = conn.execute(
        """
        SELECT l.lot_id, l.model_name, d.retention_rate, t.sae_cca, t.en_cca,
               t.en_cca_10s_voltage, t.en_cca_6v_hold_sec, t.sae_cca_7v2_hold_sec
        FROM Lot l
        JOIN LotDerived d ON d.lot_id = l.lot_id
        JOIN (SELECT lot_id, MAX(id) AS latest_id FROM TestData GROUP BY lot_id) latest_t
          ON latest_t.lot_id = l.lot_id
        JOIN TestData t ON t.id = latest_t.latest_id
        WHERE d.retention_rate IS NOT NULL AND (t.sae_cca IS NOT NULL OR t.en_cca IS NOT NULL)
        ORDER BY l.lot_id
        """
    ).fetchall()
    return [dict(r) for r in rows]


def get_scoring_rows(conn: sqlite3.Connection) -> list[dict]:
    """채점 모듈(.docs/24) 대상 로트 전체: 1단 X + retention_rate(Y 실측) + 시험 실측값(Z·CCA
    체크포인트) + 모델별 SPEC 하한(ConstantsByModel, 없으면 NULL)을 한 번에 반환한다.

    `get_xy_to_z_training_rows` 등과 매칭 조건(전해액온도·수조온도·retention_rate 존재)은 같지만,
    채점은 target별로 필요한 컬럼이 달라 필터링을 여기서 미리 하지 않고 `analysis/scoring.py`에
    맡긴다(y는 retention_rate만 있으면 되고, z/CCA는 추가로 실측값이 더 필요함)."""
    rows = conn.execute(
        """
        SELECT l.lot_id, l.model_name, l.rated_capacity,
               p.electrolyte_temp, p.tank_temp, p.soaking_time_sec, p.aging_days,
               d.formation_dv, d.cell_weight_mean, d.cell_weight_std, d.charge_ratio,
               d.charge_program_deviation_pct, d.retention_rate,
               t.discharge_amount, t.capacity_rate,
               t.en_cca_10s_voltage, t.en_cca_6v_hold_sec, t.sae_cca_7v2_hold_sec,
               c.spec_lower_y, c.spec_lower_z
        FROM Lot l
        JOIN (SELECT lot_id, MAX(id) AS latest_id FROM ProcessData GROUP BY lot_id) latest_p
          ON latest_p.lot_id = l.lot_id
        JOIN ProcessData p ON p.id = latest_p.latest_id
        JOIN LotDerived d ON d.lot_id = l.lot_id
        JOIN (SELECT lot_id, MAX(id) AS latest_id FROM TestData GROUP BY lot_id) latest_t
          ON latest_t.lot_id = l.lot_id
        JOIN TestData t ON t.id = latest_t.latest_id
        LEFT JOIN ConstantsByModel c ON c.model_name = l.model_name
        WHERE p.electrolyte_temp IS NOT NULL AND p.charge_amount IS NOT NULL
          AND p.tank_temp IS NOT NULL AND d.retention_rate IS NOT NULL
        """
    ).fetchall()
    return [dict(r) for r in rows]


def save_scoring_run(conn: sqlite3.Connection, result: dict) -> int:
    """`analysis/scoring.py`의 채점 결과(`score_target` 반환값)를 ScoringRun+ScoringResult로 저장한다."""
    cursor = conn.execute(
        """
        INSERT INTO ScoringRun (
            target, threshold_pct, error_tolerance_pct,
            n_total, n_scorable, n_matched, n_mismatched, success_rate_pct, reliable
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            result["target"], result["threshold_pct"], result["error_tolerance_pct"],
            result["n_total"], result["n_scorable"], result["n_matched"], result["n_mismatched"],
            result["success_rate_pct"],
            None if result["reliable"] is None else int(result["reliable"]),
        ),
    )
    run_id = cursor.lastrowid
    for r in result["results"]:
        conn.execute(
            """
            INSERT INTO ScoringResult (
                run_id, lot_id, predicted_value, actual_value, error_pct,
                predicted_spec_result, actual_spec_result, matched
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id, r["lot_id"], r["predicted_value"], r["actual_value"], r["error_pct"],
                r["predicted_spec_result"], r["actual_spec_result"],
                None if r["matched"] is None else int(r["matched"]),
            ),
        )
    conn.commit()
    return run_id


def get_latest_scoring_run(conn: sqlite3.Connection, target: str) -> dict | None:
    """target별 가장 최근 채점 결과 + 불일치(실패) 로트 목록을 조회한다.

    `reliable`은 SQLite에 0/1 INTEGER로 저장돼 있어(`save_scoring_run`) 그대로 반환하면
    프런트(`reliable === true/false` 엄격 비교, `frontend/app/dashboard/page.tsx`의
    `buildScoringCard`)가 0/1을 true/false와 다른 값으로 취급해 "판정 불가"로 잘못 표시된다
    (`POST /api/scoring/run` 직후엔 DB를 안 거친 진짜 bool이라 정상 동작하는 것과 대비됨) —
    여기서 명시적으로 Python bool로 되돌려 두 엔드포인트의 타입을 맞춘다.
    """
    run = conn.execute(
        "SELECT * FROM ScoringRun WHERE target = ? ORDER BY run_id DESC LIMIT 1", (target,)
    ).fetchone()
    if run is None:
        return None
    mismatched = conn.execute(
        "SELECT * FROM ScoringResult WHERE run_id = ? AND matched = 0 ORDER BY lot_id",
        (run["run_id"],),
    ).fetchall()
    result = {**dict(run), "mismatched_lots": [dict(r) for r in mismatched]}
    if result["reliable"] is not None:
        result["reliable"] = bool(result["reliable"])
    return result


def save_analysis_run(conn: sqlite3.Connection, stage: str, result: dict) -> int:
    """회귀 결과(backend/analysis/regression.py의 반환값)를 AnalysisRun에 저장한다.

    같은 stage의 기존 `is_latest_for_stage=1` 행을 0으로 내린 뒤 새 행을 1로 삽입한다
    (`.docs/03_sqlite-스키마-설계.md`의 stage별 최신 run 원칙).
    """
    conn.execute(
        "UPDATE AnalysisRun SET is_latest_for_stage = 0 WHERE stage = ? AND is_latest_for_stage = 1",
        (stage,),
    )
    cursor = conn.execute(
        """
        INSERT INTO AnalysisRun (
            stage, lot_range, correlation_matrix, regression_coefficients, vif, r_squared, is_latest_for_stage
        ) VALUES (?, ?, ?, ?, ?, ?, 1)
        """,
        (
            stage,
            json.dumps({"n": result["n"], "x_columns": result["x_columns"], "target": result["target"]}),
            json.dumps(result["significance"]),
            json.dumps({"coefficients": result["coefficients"], "intercept": result["intercept"]}),
            json.dumps(result["vif"]),
            result["r_squared"],
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_latest_analysis_run(conn: sqlite3.Connection, stage: str) -> dict | None:
    """stage별 가장 최근 `is_latest_for_stage=1` run을 회귀 결과 형태로 복원해 반환한다."""
    row = conn.execute(
        "SELECT * FROM AnalysisRun WHERE stage = ? AND is_latest_for_stage = 1 ORDER BY run_id DESC LIMIT 1",
        (stage,),
    ).fetchone()
    if row is None:
        return None

    result = dict(row)
    lot_range = json.loads(result["lot_range"]) if result["lot_range"] else {}
    coeff_blob = json.loads(result["regression_coefficients"]) if result["regression_coefficients"] else {}
    result["n"] = lot_range.get("n")
    result["x_columns"] = lot_range.get("x_columns")
    result["target"] = lot_range.get("target")
    result["significance"] = json.loads(result["correlation_matrix"]) if result["correlation_matrix"] else None
    result["coefficients"] = coeff_blob.get("coefficients")
    result["intercept"] = coeff_blob.get("intercept")
    result["vif"] = json.loads(result["vif"]) if result["vif"] else None
    return result


def get_kpi_summary(conn: sqlite3.Connection) -> dict:
    """대시보드 상단 KPI 카드용 집계(`GET /api/kpi`)."""
    total_lots = conn.execute("SELECT COUNT(*) AS n FROM Lot").fetchone()["n"]
    matched_lots = conn.execute("SELECT COUNT(DISTINCT lot_id) AS n FROM TestData").fetchone()["n"]
    avg_retention_rate = conn.execute("SELECT AVG(retention_rate) AS v FROM LotDerived").fetchone()["v"]
    match_rate = round(matched_lots / total_lots * 100, 1) if total_lots else 0.0
    return {
        "total_lots": total_lots,
        "matched_lots": matched_lots,
        "match_rate": match_rate,
        "avg_retention_rate": avg_retention_rate,
    }


# =========================================================
# Day 2 — 형명별 상세 분석(③-3) + 추이(③-4) 조회
# =========================================================

def get_spec_compliance_summary(conn: sqlite3.Connection) -> dict:
    """대시보드 KPI용 SPEC 판정 요약(`GET /api/spec-compliance`, history/17 5단계).

    이미 알고 있는 값(Y=LotDerived.retention_rate, Z=TestData.capacity_rate — 둘 다 예측이
    아니라 실측/직접계산값)만으로 SPEC 하한(ConstantsByModel)과 비교한다. 예측(Ŷ/Ẑ) 기반 판정은
    `/prediction` 화면(POST /api/predict/*)이 담당하고, 여기서는 "이번 달 실제로 확보된 데이터
    기준" 요약만 낸다. `models_with_spec=0`이면 SPEC이 아직 하나도 설정되지 않은 것이다.
    """
    row = conn.execute(
        """
        SELECT
          COUNT(CASE WHEN d.retention_rate IS NOT NULL AND c.spec_lower_y IS NOT NULL THEN 1 END) AS y_evaluated,
          COUNT(CASE WHEN d.retention_rate IS NOT NULL AND c.spec_lower_y IS NOT NULL
                       AND d.retention_rate < c.spec_lower_y THEN 1 END) AS y_fail,
          COUNT(CASE WHEN t.capacity_rate IS NOT NULL AND c.spec_lower_z IS NOT NULL THEN 1 END) AS z_evaluated,
          COUNT(CASE WHEN t.capacity_rate IS NOT NULL AND c.spec_lower_z IS NOT NULL
                       AND t.capacity_rate < c.spec_lower_z THEN 1 END) AS z_fail,
          COUNT(DISTINCT CASE WHEN c.spec_lower_y IS NOT NULL OR c.spec_lower_z IS NOT NULL
                               THEN l.model_name END) AS models_with_spec
        FROM Lot l
        LEFT JOIN LotDerived d ON d.lot_id = l.lot_id
        LEFT JOIN (SELECT lot_id, MAX(id) AS latest_id FROM TestData GROUP BY lot_id) latest_t
          ON latest_t.lot_id = l.lot_id
        LEFT JOIN TestData t ON t.id = latest_t.latest_id
        LEFT JOIN ConstantsByModel c ON c.model_name = l.model_name
        """
    ).fetchone()
    return dict(row)


def get_model_summary(conn: sqlite3.Connection) -> list[dict]:
    """형명별 group-by 요약(로트 수, 평균 Y, 시험 매칭 수, 평균 Z) — `GET /api/models/summary`."""
    rows = conn.execute(
        """
        SELECT l.model_name, l.rated_capacity,
               COUNT(DISTINCT l.lot_id) AS lot_count,
               AVG(d.retention_rate) AS avg_retention_rate,
               COUNT(DISTINCT t.lot_id) AS matched_count,
               AVG(t.discharge_amount) AS avg_discharge_amount,
               AVG(t.capacity_rate) AS avg_capacity_rate
        FROM Lot l
        LEFT JOIN LotDerived d ON d.lot_id = l.lot_id
        LEFT JOIN (SELECT lot_id, MAX(id) AS latest_id FROM TestData GROUP BY lot_id) latest_t
          ON latest_t.lot_id = l.lot_id
        LEFT JOIN TestData t ON t.id = latest_t.latest_id
        GROUP BY l.model_name, l.rated_capacity
        ORDER BY l.rated_capacity, l.model_name
        """
    ).fetchall()
    return [dict(r) for r in rows]


def get_model_cca_checkpoints(conn: sqlite3.Connection) -> list[dict]:
    """형명별 CCA 체크포인트 원시값(로트당 최신 시험 매칭 1건) — `GET /api/models/summary`가
    합격/불합격 집계에 쓴다. 판정(pass/fail) 자체는 `analysis/cca_spec.py`의 고정 임계값
    함수로 하므로 여기서는 원시값만 반환한다."""
    rows = conn.execute(
        """
        SELECT l.model_name,
               t.en_cca_10s_voltage, t.en_cca_6v_hold_sec, t.sae_cca_7v2_hold_sec
        FROM Lot l
        JOIN (SELECT lot_id, MAX(id) AS latest_id FROM TestData GROUP BY lot_id) latest_t
          ON latest_t.lot_id = l.lot_id
        JOIN TestData t ON t.id = latest_t.latest_id
        """
    ).fetchall()
    return [dict(r) for r in rows]


def get_model_lot_rows(
    conn: sqlite3.Connection, model_name: str, limit: int = 200, sort: str = "recent"
) -> dict:
    """형명 하나의 로트별 기본 raw data(`GET /api/models/{model_name}/lots`).

    상세 분석 테이블의 "로트 수"/"시험 매칭" 숫자가 어떤 로트로 구성됐는지 드릴다운으로
    확인할 수 있도록, lot_id·prod_date·Y(포화도)·시험 매칭 여부·Z(있으면)를 반환한다.
    `sort="tested_first"`이면 시험 매칭된 로트를 먼저 보여준다(그 안에서는 최신순).
    """
    total_count = conn.execute(
        "SELECT COUNT(*) AS n FROM Lot WHERE model_name = ?", (model_name,)
    ).fetchone()["n"]
    order_by = (
        "ORDER BY has_test DESC, l.prod_date DESC, l.lot_id DESC"
        if sort == "tested_first"
        else "ORDER BY l.prod_date DESC, l.lot_id DESC"
    )
    rows = conn.execute(
        f"""
        SELECT l.lot_id, l.prod_date,
               d.retention_rate,
               t.discharge_amount, t.capacity_rate,
               t.sae_cca, t.en_cca,
               t.en_cca_10s_voltage, t.en_cca_6v_hold_sec, t.sae_cca_7v2_hold_sec,
               CASE WHEN latest_t.lot_id IS NULL THEN 0 ELSE 1 END AS has_test
        FROM Lot l
        LEFT JOIN LotDerived d ON d.lot_id = l.lot_id
        LEFT JOIN (SELECT lot_id, MAX(id) AS latest_id FROM TestData GROUP BY lot_id) latest_t
          ON latest_t.lot_id = l.lot_id
        LEFT JOIN TestData t ON t.id = latest_t.latest_id
        WHERE l.model_name = ?
        {order_by}
        LIMIT ?
        """,
        (model_name, limit),
    ).fetchall()
    return {"total_count": total_count, "rows": [dict(r) for r in rows]}


def get_model_trend_rows(conn: sqlite3.Connection, model_name: str | None) -> list[dict]:
    """형명별(또는 전체) Y 추이 원본 행(`GET /api/models/{model_name}/trend`) — trend.aggregate_by_period 입력."""
    query = "SELECT l.prod_date, d.retention_rate FROM Lot l JOIN LotDerived d ON d.lot_id = l.lot_id"
    params: list = []
    if model_name:
        query += " WHERE l.model_name = ?"
        params.append(model_name)
    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


# =========================================================
# Day 3 — 예측(④)·SPEC 판정·원인진단(⑤) 조회/저장 (history/17)
# =========================================================

def get_unmatched_lots_x(conn: sqlite3.Connection) -> list[dict]:
    """④-1/④-2 미매칭 로트 일괄 예측 대상: 시험(TestData) 매칭이 없고, 1단 X셋이 모두 채워진 로트.

    `get_x_to_y_training_rows`와 동일한 X 완결성 조건(append-only 최신 행 기준)이지만
    `retention_rate` 존재 여부는 요구하지 않는다(예측 대상이므로 Y가 없는 것이 오히려 정상).

    `uploaded_date`는 예측에 실제로 쓰인 최신 ProcessData 행이 시스템에 들어온 날짜(`ingested_at`의
    날짜 부분) — `/upload` 업로드 이력 날짜별 그룹핑과 동일한 기준이라, "그날 넣은 데이터"를
    예측 화면에서도 같은 날짜 단위로 골라 확인할 수 있게 한다.
    """
    rows = conn.execute(
        """
        SELECT l.lot_id, l.model_name, l.rated_capacity,
               p.electrolyte_temp, p.tank_temp, p.soaking_time_sec, p.aging_days,
               d.formation_dv, d.cell_weight_mean, d.cell_weight_std, d.charge_ratio,
               d.charge_program_deviation_pct,
               date(p.ingested_at) AS uploaded_date
        FROM Lot l
        JOIN (SELECT lot_id, MAX(id) AS latest_id FROM ProcessData GROUP BY lot_id) latest_p
          ON latest_p.lot_id = l.lot_id
        JOIN ProcessData p ON p.id = latest_p.latest_id
        JOIN LotDerived d ON d.lot_id = l.lot_id
        WHERE p.electrolyte_temp IS NOT NULL AND p.charge_amount IS NOT NULL
          AND p.tank_temp IS NOT NULL AND d.charge_program_deviation_pct IS NOT NULL
          AND l.lot_id NOT IN (SELECT DISTINCT lot_id FROM TestData)
        """
    ).fetchall()
    return [dict(r) for r in rows]


def get_spec_threshold_for_model(conn: sqlite3.Connection, model_name: str) -> dict | None:
    """모델 하나의 SPEC 하한(spec_lower_y/z) 조회. 미설정(NULL)이어도 행이 없으면 None."""
    row = conn.execute(
        "SELECT spec_lower_y, spec_lower_z FROM ConstantsByModel WHERE model_name = ?",
        (model_name,),
    ).fetchone()
    return dict(row) if row else None


def get_failing_lots(conn: sqlite3.Connection, model_name: str | None = None) -> list[dict]:
    """실측 Y(retention_rate)·Z(capacity_rate)가 SPEC 하한 미달인 로트 전체(`GET /api/models/failing-lots`).

    `get_x_to_y_training_rows`/`get_xy_to_z_training_rows`와 동일한 1단 X셋 조인 패턴에
    `ConstantsByModel`(SPEC 하한)을 더해, 실제로 SPEC 미달인 로트만 걸러 반환한다. 예측이 아니라
    이미 확보된 실측/직접계산값 기준이라 `/prediction`(미매칭 로트 예측)과는 대상이 겹치지 않는다
    (여긴 시험 매칭된 로트만, `/prediction`은 미매칭 로트만). `model_name`을 주면 그 형명만 필터.
    """
    params: list = []
    model_filter = ""
    if model_name:
        model_filter = "AND l.model_name = ?"
        params.append(model_name)
    rows = conn.execute(
        f"""
        SELECT l.lot_id, l.model_name,
               p.electrolyte_temp, p.tank_temp, p.soaking_time_sec, p.aging_days,
               d.formation_dv, d.cell_weight_mean, d.cell_weight_std, d.charge_ratio,
               d.charge_program_deviation_pct, d.retention_rate,
               t.capacity_rate,
               c.spec_lower_y, c.spec_lower_z
        FROM Lot l
        JOIN (SELECT lot_id, MAX(id) AS latest_id FROM ProcessData GROUP BY lot_id) latest_p
          ON latest_p.lot_id = l.lot_id
        JOIN ProcessData p ON p.id = latest_p.latest_id
        JOIN LotDerived d ON d.lot_id = l.lot_id
        JOIN (SELECT lot_id, MAX(id) AS latest_id FROM TestData GROUP BY lot_id) latest_t
          ON latest_t.lot_id = l.lot_id
        JOIN TestData t ON t.id = latest_t.latest_id
        JOIN ConstantsByModel c ON c.model_name = l.model_name
        WHERE (
            (c.spec_lower_y IS NOT NULL AND d.retention_rate IS NOT NULL AND d.retention_rate < c.spec_lower_y)
            OR (c.spec_lower_z IS NOT NULL AND t.capacity_rate IS NOT NULL AND t.capacity_rate < c.spec_lower_z)
          )
          {model_filter}
        ORDER BY l.model_name, l.lot_id
        """,
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def save_prediction(
    conn: sqlite3.Connection,
    lot_id: str | None,
    run_id: int,
    target: str,
    predicted_value: float,
    input_y_source: str | None,
    source: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO Prediction (lot_id, run_id, target, predicted_value, input_y_source, source)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (lot_id, run_id, target, predicted_value, input_y_source, source),
    )
    conn.commit()
    return cur.lastrowid


def save_spec_judgment(
    conn: sqlite3.Connection,
    lot_id: str | None,
    prediction_id: int | None,
    target: str,
    spec_result: str | None,
    spec_thresholds_used: dict,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO SpecJudgment (lot_id, prediction_id, target, spec_result, spec_thresholds_used)
        VALUES (?, ?, ?, ?, ?)
        """,
        (lot_id, prediction_id, target, spec_result, json.dumps(spec_thresholds_used)),
    )
    conn.commit()
    return cur.lastrowid


def save_cause_diagnosis(
    conn: sqlite3.Connection,
    lot_id: str | None,
    prediction_id: int | None,
    target: str,
    ranked_factors: list[dict],
    recommendation_text: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO CauseDiagnosis (lot_id, prediction_id, target, ranked_factors, recommendation_text)
        VALUES (?, ?, ?, ?, ?)
        """,
        (lot_id, prediction_id, target, json.dumps(ranked_factors), recommendation_text),
    )
    conn.commit()
    return cur.lastrowid
