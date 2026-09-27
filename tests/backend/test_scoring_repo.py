"""backend/db/repository.py의 get_scoring_rows/save_scoring_run/get_latest_scoring_run 테스트(.docs/24)."""
from backend.db import repository as repo


def _process_row(lot_id: str, model_name: str) -> dict:
    return {
        "lot_id": lot_id, "model_name": model_name, "prod_date": "2026-09-01", "line_no": "1",
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
        "en_cca_10s_voltage": "7.7", "en_cca_6v_hold_sec": "95", "sae_cca_7v2_hold_sec": "33",
    }


def _setup_db(tmp_path, monkeypatch):
    monkeypatch.setattr(repo, "DB_PATH", tmp_path / "test.db")
    repo.init_db()
    return repo.get_connection()


def test_get_scoring_rows_returns_matched_lots_with_checkpoint_fields(tmp_path, monkeypatch):
    conn = _setup_db(tmp_path, monkeypatch)
    try:
        repo.ingest_process_rows(conn, [_process_row("LOT_A", "AGM90_S1")])
        repo.ingest_test_rows(conn, [_test_row("LOT_A")])

        rows = repo.get_scoring_rows(conn)
        assert len(rows) == 1
        row = rows[0]
        assert row["lot_id"] == "LOT_A"
        assert row["rated_capacity"] == 90.0
        assert row["retention_rate"] is not None
        assert row["en_cca_10s_voltage"] == 7.7
        assert row["en_cca_6v_hold_sec"] == 95.0
        assert row["sae_cca_7v2_hold_sec"] == 33.0
        assert row["spec_lower_y"] is None  # SPEC 하한 미설정이면 NULL(지어내지 않음)
    finally:
        conn.close()


def _fake_scoring_result() -> dict:
    return {
        "target": "y",
        "threshold_pct": 90.0,
        "error_tolerance_pct": 10.0,
        "n_total": 2,
        "n_scorable": 2,
        "n_matched": 1,
        "n_mismatched": 1,
        "success_rate_pct": 50.0,
        "reliable": False,
        "results": [
            {
                "lot_id": "LOT_A", "predicted_value": 91.0, "actual_value": 90.5,
                "error_pct": 0.55, "within_error_tolerance": True,
                "predicted_spec_result": "pass", "actual_spec_result": "pass", "matched": True,
            },
            {
                "lot_id": "LOT_B", "predicted_value": 60.0, "actual_value": 40.0,
                "error_pct": 50.0, "within_error_tolerance": False,
                "predicted_spec_result": "pass", "actual_spec_result": "fail", "matched": False,
            },
        ],
    }


def test_save_and_get_latest_scoring_run_round_trip(tmp_path, monkeypatch):
    conn = _setup_db(tmp_path, monkeypatch)
    try:
        repo.ingest_process_rows(conn, [_process_row("LOT_A", "AGM90_S1"), _process_row("LOT_B", "AGM90_S1")])
        repo.ingest_test_rows(conn, [_test_row("LOT_A"), _test_row("LOT_B")])

        run_id = repo.save_scoring_run(conn, _fake_scoring_result())
        assert run_id is not None

        latest = repo.get_latest_scoring_run(conn, "y")
        assert latest["run_id"] == run_id
        assert latest["target"] == "y"
        assert latest["n_matched"] == 1
        assert latest["n_mismatched"] == 1
        # SQLite에는 0/1 INTEGER로 저장되지만, get_latest_scoring_run이 다시 bool로 되돌려야
        # `POST /api/scoring/run`(DB를 안 거친 진짜 bool)과 타입이 일치해 프런트의 엄격 비교
        # (`reliable === true/false`)가 오작동하지 않는다.
        assert latest["reliable"] is False
        assert len(latest["mismatched_lots"]) == 1
        assert latest["mismatched_lots"][0]["lot_id"] == "LOT_B"
    finally:
        conn.close()


def test_get_latest_scoring_run_returns_none_when_never_run(tmp_path, monkeypatch):
    conn = _setup_db(tmp_path, monkeypatch)
    try:
        assert repo.get_latest_scoring_run(conn, "z") is None
    finally:
        conn.close()


def test_delete_all_data_clears_scoring_tables(tmp_path, monkeypatch):
    conn = _setup_db(tmp_path, monkeypatch)
    try:
        repo.ingest_process_rows(conn, [_process_row("LOT_A", "AGM90_S1"), _process_row("LOT_B", "AGM90_S1")])
        repo.ingest_test_rows(conn, [_test_row("LOT_A"), _test_row("LOT_B")])
        repo.save_scoring_run(conn, _fake_scoring_result())

        repo.delete_all_data(conn)

        assert conn.execute("SELECT COUNT(*) FROM ScoringRun").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM ScoringResult").fetchone()[0] == 0
    finally:
        conn.close()
