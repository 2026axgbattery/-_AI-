"""backend/db/repository.py의 get_failing_lots 테스트. .docs/27 참조."""
from backend.db import repository as repo


def _process_row(lot_id: str, model_name: str, fill_weight: str, water_loss: str) -> dict:
    return {
        "lot_id": lot_id, "model_name": model_name, "prod_date": "2026-09-01", "line_no": "1",
        "cell1_weight": "3.0", "cell2_weight": "3.0", "cell3_weight": "3.0",
        "cell4_weight": "3.0", "cell5_weight": "3.0", "cell6_weight": "3.0",
        "cell1_ginap": "50", "cell2_ginap": "50", "cell3_ginap": "50",
        "cell4_ginap": "50", "cell5_ginap": "50", "cell6_ginap": "50",
        "fill_weight": fill_weight, "water_loss": water_loss,
        "voltage_1st": "12.8", "bath_no": "1", "circuit_no": "1",
        "soaking_time_sec": "90", "aging_days": "7", "voltage_2nd": "12.9",
        "electrolyte_temp": "31.0", "charge_amount": "100.0", "tank_temp": "27.0",
    }


def _test_row(lot_id: str, capacity_rate: str) -> dict:
    return {
        "lot_id": lot_id,
        "initial_voltage": "12.87", "initial_resistance": "3.27", "initial_weight": "20188",
        "initial_cca": "785", "rated_capacity": "90",
        "discharge_amount": "89.5", "charge_amount_20h": "95.0",
        "capacity_rate": capacity_rate, "charge_rate": "105.6",
        "mt_voltage": "12.86", "mt_current": "785",
    }


def _setup_db(tmp_path, monkeypatch):
    monkeypatch.setattr(repo, "DB_PATH", tmp_path / "test.db")
    repo.init_db()
    return repo.get_connection()


def test_get_failing_lots_returns_only_spec_violations(tmp_path, monkeypatch):
    conn = _setup_db(tmp_path, monkeypatch)
    try:
        # LOT_PASS: retention_rate = (5900-250)/5900*100 = 95.76% >= spec 91.0, capacity 99.0 >= 95.0 -> 둘 다 pass
        # LOT_FAIL_Y: retention_rate = (5900-900)/5900*100 = 84.7% < spec 91.0 -> Y만 미달
        repo.ingest_process_rows(conn, [
            _process_row("LOT_PASS", "AGM90_S1", "5900", "250"),
            _process_row("LOT_FAIL_Y", "AGM90_S1", "5900", "900"),
        ])
        repo.ingest_test_rows(conn, [_test_row("LOT_PASS", "99.0"), _test_row("LOT_FAIL_Y", "99.0")])
        repo.upsert_spec_thresholds(
            conn, [{"model_name": "AGM90_S1", "spec_lower_y": "91.0", "spec_lower_z": "95.0"}]
        )

        failing = repo.get_failing_lots(conn)
        lot_ids = {r["lot_id"] for r in failing}
        assert lot_ids == {"LOT_FAIL_Y"}
        row = failing[0]
        assert row["model_name"] == "AGM90_S1"
        assert row["spec_lower_y"] == 91.0
        assert row["retention_rate"] < 91.0
        # 1단 X 인자가 원인진단 입력용으로 같이 반환돼야 함
        assert row["electrolyte_temp"] == 31.0
        # ChargeProgramSpec 미업로드 시 charge_program_deviation_pct는 NULL(정상, CLAUDE.md 함정 참조)
        # 이지만 컬럼 자체는 rank_causes 입력용으로 항상 키가 존재해야 한다.
        assert "charge_program_deviation_pct" in row
    finally:
        conn.close()


def test_get_failing_lots_empty_without_spec_thresholds(tmp_path, monkeypatch):
    conn = _setup_db(tmp_path, monkeypatch)
    try:
        repo.ingest_process_rows(conn, [_process_row("LOT_A", "AGM90_S1", "5900", "900")])
        repo.ingest_test_rows(conn, [_test_row("LOT_A", "80.0")])
        # SPEC 미설정(ConstantsByModel 행 자체가 없음) -> get_failing_lots는 아무것도 반환하지 않아야 함
        assert repo.get_failing_lots(conn) == []
    finally:
        conn.close()
