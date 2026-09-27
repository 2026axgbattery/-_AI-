"""backend/db/repository.py의 Day 3(예측·SPEC판정·원인진단) 관련 함수 테스트.

history/17_day3-예측-spec판정-원인진단-구현계획.md 2단계.
"""
from backend.db import repository as repo


def _process_row(lot_id: str, model_name: str = "AGM90_S1") -> dict:
    return {
        "lot_id": lot_id,
        "model_name": model_name,
        "prod_date": "2026-09-01",
        "line_no": "1",
        "cell1_weight": "3.0", "cell2_weight": "3.0", "cell3_weight": "3.0",
        "cell4_weight": "3.0", "cell5_weight": "3.0", "cell6_weight": "3.0",
        "cell1_ginap": "50", "cell2_ginap": "50", "cell3_ginap": "50",
        "cell4_ginap": "50", "cell5_ginap": "50", "cell6_ginap": "50",
        "fill_weight": "5900", "water_loss": "250",
        "voltage_1st": "12.8", "bath_no": "1", "circuit_no": "1",
        "soaking_time_sec": "90", "aging_days": "7", "voltage_2nd": "12.9",
        "electrolyte_temp": "31.0", "charge_amount": "100.0", "tank_temp": "27.0",
    }


def _test_row(lot_id: str) -> dict:
    return {
        "lot_id": lot_id,
        "initial_voltage": "12.87", "initial_resistance": "3.27", "initial_weight": "20188",
        "initial_cca": "785", "rated_capacity": "90",
        "discharge_amount": "89.5", "charge_amount_20h": "95.0",
        "capacity_rate": "99.4", "charge_rate": "105.6",
        "mt_voltage": "12.86", "mt_current": "785",
    }


def _setup_db(tmp_path, monkeypatch):
    monkeypatch.setattr(repo, "DB_PATH", tmp_path / "test.db")
    repo.init_db()
    return repo.get_connection()


def test_get_unmatched_lots_x_excludes_tested_lots(tmp_path, monkeypatch):
    conn = _setup_db(tmp_path, monkeypatch)
    try:
        # charge_program_deviation_pct(history/19 Phase B)도 1단 X셋에 포함돼 있어, 매칭되는
        # 충전 프로그램이 없으면 get_unmatched_lots_x에서 제외된다 — 미리 등록해둔다.
        repo.replace_charge_program_specs(
            conn,
            [{
                "rated_capacity": 90.0, "buyer_code": "S", "program_label": "AGM90_S_test",
                "is_variant": False, "charge_hours": 35.0, "total_charge_ah": 100.0,
                "total_electricity_c": 5.8, "steps_json": "[]",
            }],
            source_file="test.xlsx",
        )
        repo.ingest_process_rows(conn, [_process_row("LOT_MATCHED"), _process_row("LOT_UNMATCHED")])
        repo.ingest_test_rows(conn, [_test_row("LOT_MATCHED")])

        rows = repo.get_unmatched_lots_x(conn)
        lot_ids = {r["lot_id"] for r in rows}
        assert lot_ids == {"LOT_UNMATCHED"}
        row = rows[0]
        assert row["model_name"] == "AGM90_S1"
        assert row["electrolyte_temp"] == 31.0
        assert row["charge_ratio"] is not None
    finally:
        conn.close()


def test_get_unmatched_lots_x_excludes_incomplete_x(tmp_path, monkeypatch):
    conn = _setup_db(tmp_path, monkeypatch)
    try:
        incomplete = _process_row("LOT_INCOMPLETE")
        incomplete["electrolyte_temp"] = ""
        repo.ingest_process_rows(conn, [incomplete])

        rows = repo.get_unmatched_lots_x(conn)
        assert rows == []
    finally:
        conn.close()


def test_get_spec_threshold_for_model_returns_none_when_not_set(tmp_path, monkeypatch):
    conn = _setup_db(tmp_path, monkeypatch)
    try:
        assert repo.get_spec_threshold_for_model(conn, "AGM90_S1") is None

        repo.upsert_spec_thresholds(
            conn, [{"model_name": "AGM90_S1", "spec_lower_y": "91.0", "spec_lower_z": "95.0"}]
        )
        thresholds = repo.get_spec_threshold_for_model(conn, "AGM90_S1")
        assert thresholds == {"spec_lower_y": 91.0, "spec_lower_z": 95.0}
    finally:
        conn.close()


def test_save_prediction_spec_judgment_cause_diagnosis_round_trip(tmp_path, monkeypatch):
    conn = _setup_db(tmp_path, monkeypatch)
    try:
        repo.ingest_process_rows(conn, [_process_row("LOT_A")])
        run_id = repo.save_analysis_run(
            conn, "x_to_y",
            {
                "target": "retention_rate", "x_columns": ["electrolyte_temp"],
                "coefficients": {"electrolyte_temp": 0.2}, "intercept": 90.0,
                "r_squared": 0.5, "vif": {"electrolyte_temp": 1.0},
                "significance": {"electrolyte_temp": {"r": 0.2, "p_value": 0.1, "significant": False, "n": 10}},
                "n": 10,
            },
        )

        prediction_id = repo.save_prediction(conn, "LOT_A", run_id, "y", 90.4, None, "batch_unmatched")
        assert prediction_id > 0

        judgment_id = repo.save_spec_judgment(
            conn, "LOT_A", prediction_id, "y", "fail", {"spec_lower_y": 91.0}
        )
        assert judgment_id > 0

        diagnosis_id = repo.save_cause_diagnosis(
            conn, "LOT_A", prediction_id, "y",
            [{"factor": "electrolyte_temp", "contribution": 1.5, "rank": 1}],
            "전해액온도 점검 필요",
        )
        assert diagnosis_id > 0
    finally:
        conn.close()
