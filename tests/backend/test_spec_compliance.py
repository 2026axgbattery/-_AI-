"""backend/db/repository.py의 get_spec_compliance_summary 테스트. history/17 5단계."""
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


def test_spec_compliance_applies_default_when_no_override_set(tmp_path, monkeypatch):
    """§10-11 확정(2026-09-27) — ConstantsByModel에 형명별 override가 전혀 없어도, Y=90%/Z=95%
    전체 공통 기본값(config.spec_thresholds)이 적용돼 판정 가능한 상태가 된다(더 이상 0건)."""
    conn = _setup_db(tmp_path, monkeypatch)
    try:
        # retention_rate = (5900-250)/5900*100 = 95.76% >= 기본값 90 -> pass
        repo.ingest_process_rows(conn, [_process_row("LOT_A", "AGM90_S1", "5900", "250")])
        summary = repo.get_spec_compliance_summary(conn)
        assert summary["models_with_spec"] == 1
        assert summary["y_evaluated"] == 1
        assert summary["y_fail"] == 0
        assert summary["z_evaluated"] == 0  # 시험 데이터 없음 — capacity_rate 자체가 NULL
        assert summary["spec_lower_y_min"] == 90.0
        assert summary["spec_lower_y_max"] == 90.0
        assert summary["spec_lower_z_min"] == 95.0
        assert summary["spec_lower_z_max"] == 95.0
    finally:
        conn.close()


def test_spec_compliance_default_catches_fail_without_override(tmp_path, monkeypatch):
    """override 없이도 기본값 90%가 실제로 강제되는지(단순히 존재만 하는 게 아니라) 확인."""
    conn = _setup_db(tmp_path, monkeypatch)
    try:
        # retention_rate = (5900-900)/5900*100 = 84.7% < 기본값 90 -> fail
        repo.ingest_process_rows(conn, [_process_row("LOT_FAIL", "AGM90_S1", "5900", "900")])
        summary = repo.get_spec_compliance_summary(conn)
        assert summary["y_evaluated"] == 1
        assert summary["y_fail"] == 1
    finally:
        conn.close()


def test_spec_compliance_counts_pass_and_fail(tmp_path, monkeypatch):
    conn = _setup_db(tmp_path, monkeypatch)
    try:
        # LOT_PASS: retention_rate = (5900-250)/5900*100 = 95.76% >= spec 91.0 -> pass
        # LOT_FAIL: retention_rate = (5900-900)/5900*100 = 84.7% < spec 91.0 -> fail
        repo.ingest_process_rows(conn, [
            _process_row("LOT_PASS", "AGM90_S1", "5900", "250"),
            _process_row("LOT_FAIL", "AGM90_S1", "5900", "900"),
        ])
        repo.ingest_test_rows(conn, [_test_row("LOT_PASS", "99.0"), _test_row("LOT_FAIL", "90.0")])
        repo.upsert_spec_thresholds(
            conn, [{"model_name": "AGM90_S1", "spec_lower_y": "91.0", "spec_lower_z": "95.0"}]
        )

        summary = repo.get_spec_compliance_summary(conn)
        assert summary["models_with_spec"] == 1
        assert summary["y_evaluated"] == 2
        assert summary["y_fail"] == 1
        assert summary["z_evaluated"] == 2
        assert summary["z_fail"] == 1  # 90.0 < 95.0
    finally:
        conn.close()
