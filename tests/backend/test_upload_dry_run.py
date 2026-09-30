"""backend/db/repository.py의 ingest_process_rows/ingest_test_rows dry_run(업로드 미리보기,
.docs/35) 테스트 — 실제 반영 로직을 그대로 타면서 커밋 대신 롤백해 아무것도 저장하지 않아야
하고, 반환되는 요약(신규/중복/스킵 건수)은 실제 반영 때와 동일해야 한다."""
from backend.db import repository as repo


def _process_row(lot_id: str, model_name: str = "AGM90_S1") -> dict:
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
        "capacity_rate": "97.0", "charge_rate": "105.6",
        "mt_voltage": "12.86", "mt_current": "785",
    }


def _setup_db(tmp_path, monkeypatch):
    monkeypatch.setattr(repo, "DB_PATH", tmp_path / "test.db")
    repo.init_db()
    return repo.get_connection()


def test_dry_run_process_rows_leaves_db_untouched(tmp_path, monkeypatch):
    conn = _setup_db(tmp_path, monkeypatch)
    try:
        result = repo.ingest_process_rows(conn, [_process_row("LOT_A"), _process_row("LOT_B")], dry_run=True)

        assert result["preview"] is True
        assert result["inserted_lots"] == 2
        assert result["inserted_process_rows"] == 2
        assert conn.execute("SELECT COUNT(*) AS n FROM Lot").fetchone()["n"] == 0
        assert conn.execute("SELECT COUNT(*) AS n FROM ProcessData").fetchone()["n"] == 0
        assert conn.execute("SELECT COUNT(*) AS n FROM UploadBatch").fetchone()["n"] == 0
        assert conn.execute("SELECT COUNT(*) AS n FROM LotDerived").fetchone()["n"] == 0
    finally:
        conn.close()


def test_dry_run_process_rows_still_reports_invalid_rows(tmp_path, monkeypatch):
    """미리보기도 실제 반영과 똑같은 검증(model_name 파싱 실패 등)을 거쳐야 한다 — 별도의
    허술한 미리보기 전용 파서가 아니라 진짜 반영 로직을 그대로 타는 게 이 기능의 핵심."""
    conn = _setup_db(tmp_path, monkeypatch)
    try:
        result = repo.ingest_process_rows(
            conn, [_process_row("LOT_A"), _process_row("LOT_BAD", model_name="정체불명")], dry_run=True
        )
        assert result["inserted_process_rows"] == 1
        assert len(result["skipped_invalid_rows"]) == 1
        assert conn.execute("SELECT COUNT(*) AS n FROM Lot").fetchone()["n"] == 0
    finally:
        conn.close()


def test_dry_run_then_real_run_matches_preview_summary(tmp_path, monkeypatch):
    """미리보기가 보여준 숫자와 실제 반영 결과가 같아야(같은 로직을 두 번 태우는 구조이므로)
    사용자가 미리보기를 신뢰할 수 있다."""
    conn = _setup_db(tmp_path, monkeypatch)
    try:
        rows = [_process_row("LOT_A"), _process_row("LOT_B")]
        preview = repo.ingest_process_rows(conn, rows, dry_run=True)
        real = repo.ingest_process_rows(conn, rows, dry_run=False)

        assert preview["inserted_lots"] == real["inserted_lots"]
        assert preview["inserted_process_rows"] == real["inserted_process_rows"]
        assert real["preview"] is False
        assert conn.execute("SELECT COUNT(*) AS n FROM Lot").fetchone()["n"] == 2
    finally:
        conn.close()


def test_dry_run_test_rows_leaves_db_untouched(tmp_path, monkeypatch):
    conn = _setup_db(tmp_path, monkeypatch)
    try:
        repo.ingest_process_rows(conn, [_process_row("LOT_A")])  # 실제 매칭 대상 로트는 커밋
        result = repo.ingest_test_rows(conn, [_test_row("LOT_A")], dry_run=True)

        assert result["preview"] is True
        assert result["inserted_test_rows"] == 1
        assert conn.execute("SELECT COUNT(*) AS n FROM TestData").fetchone()["n"] == 0
    finally:
        conn.close()
