"""backend/db/repository.py의 delete_upload_batch 테스트.

이 함수는 이력이 길다(2026-09-24 데모 DB 대량 삭제 사고 — CLAUDE.md "알아두면 좋은 함정" 참조)에도
불구하고 이번까지 전용 테스트가 없었다. 2026-09-26에 대량 배치(로트 수천~수만 건) 삭제가 로트당
개별 SQL 루프 때문에 실측 27초가 걸려 "Failed to fetch"로 오인되는 성능 문제를 배치 SQL로
고치면서, 회귀 방지를 위해 정상 동작(고아 로트 정리/잔존 로트 재계산/test 배치)을 함께 검증한다.
"""
from backend.db import repository as repo


def _process_row(lot_id: str, model_name: str = "AGM90_S1", fill_weight: str = "5900", water_loss: str = "250") -> dict:
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


def test_delete_test_batch_only_removes_test_data(tmp_path, monkeypatch):
    conn = _setup_db(tmp_path, monkeypatch)
    try:
        result = repo.ingest_process_rows(conn, [_process_row("LOT_A")])
        process_batch_id = result["batch_id"]
        test_result = repo.ingest_test_rows(conn, [_test_row("LOT_A")])

        delete_result = repo.delete_upload_batch(conn, test_result["batch_id"])
        assert delete_result == {
            "batch_id": test_result["batch_id"], "file_type": "test", "orphaned_lot_count": 0,
        }
        assert conn.execute("SELECT COUNT(*) AS n FROM TestData").fetchone()["n"] == 0
        assert conn.execute("SELECT COUNT(*) AS n FROM Lot").fetchone()["n"] == 1
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM ProcessData WHERE upload_batch_id = ?", (process_batch_id,)
        ).fetchone()["n"] == 1
    finally:
        conn.close()


def test_delete_sole_process_batch_orphans_lot_and_cleans_up(tmp_path, monkeypatch):
    conn = _setup_db(tmp_path, monkeypatch)
    try:
        result = repo.ingest_process_rows(conn, [_process_row("LOT_A"), _process_row("LOT_B")])
        repo.ingest_test_rows(conn, [_test_row("LOT_A")])

        delete_result = repo.delete_upload_batch(conn, result["batch_id"])
        assert delete_result["file_type"] == "process"
        assert delete_result["orphaned_lot_count"] == 2

        assert conn.execute("SELECT COUNT(*) AS n FROM Lot").fetchone()["n"] == 0
        assert conn.execute("SELECT COUNT(*) AS n FROM ProcessData").fetchone()["n"] == 0
        assert conn.execute("SELECT COUNT(*) AS n FROM LotDerived").fetchone()["n"] == 0
        assert conn.execute("SELECT COUNT(*) AS n FROM TestData").fetchone()["n"] == 0
        assert conn.execute("SELECT COUNT(*) AS n FROM UploadBatch WHERE batch_id = ?", (result["batch_id"],)).fetchone()["n"] == 0
    finally:
        conn.close()


def test_delete_process_batch_keeps_lot_when_other_batch_remains(tmp_path, monkeypatch):
    """같은 lot_id가 두 번 업로드된 경우(append-only) — 한쪽 배치만 지워도 로트는 남고,
    남은 값 기준으로 LotDerived가 재계산돼야 한다(고아 처리되면 안 됨)."""
    conn = _setup_db(tmp_path, monkeypatch)
    try:
        first = repo.ingest_process_rows(conn, [_process_row("LOT_A", fill_weight="5900", water_loss="250")])
        repo.ingest_process_rows(conn, [_process_row("LOT_A", fill_weight="5900", water_loss="300")])

        delete_result = repo.delete_upload_batch(conn, first["batch_id"])
        assert delete_result["orphaned_lot_count"] == 0

        assert conn.execute("SELECT COUNT(*) AS n FROM Lot WHERE lot_id = 'LOT_A'").fetchone()["n"] == 1
        derived = conn.execute("SELECT * FROM LotDerived WHERE lot_id = 'LOT_A'").fetchone()
        # 남아 있는 두 번째 배치 값(water_loss=300) 기준으로 재계산됐는지 확인
        assert derived["retention_rate"] == (5900 - 300) / 5900 * 100
    finally:
        conn.close()


def test_delete_nonexistent_batch_raises(tmp_path, monkeypatch):
    conn = _setup_db(tmp_path, monkeypatch)
    try:
        try:
            repo.delete_upload_batch(conn, 9999)
            assert False, "ValueError가 발생해야 합니다"
        except ValueError:
            pass
    finally:
        conn.close()


def test_delete_large_process_batch_is_fast(tmp_path, monkeypatch):
    """2026-09-26 성능 수정 회귀 방지 — 로트 수천 건 규모에서도 로트당 개별 루프 없이
    빠르게 끝나야 한다(이전 구현은 1만 로트 기준 실측 27초, 이 테스트는 그보다 훨씬 작은
    규모로도 O(n) 개별 SQL 루프가 되살아나면 눈에 띄게 느려짐을 잡아낸다)."""
    import time

    conn = _setup_db(tmp_path, monkeypatch)
    try:
        rows = [_process_row(f"LOT_{i:05d}") for i in range(2000)]
        result = repo.ingest_process_rows(conn, rows)

        start = time.perf_counter()
        delete_result = repo.delete_upload_batch(conn, result["batch_id"])
        elapsed = time.perf_counter() - start

        assert delete_result["orphaned_lot_count"] == 2000
        assert conn.execute("SELECT COUNT(*) AS n FROM Lot").fetchone()["n"] == 0
        assert elapsed < 3.0, f"2,000 로트 삭제에 {elapsed:.1f}초 소요 — 로트당 개별 루프가 되살아났을 가능성"
    finally:
        conn.close()
