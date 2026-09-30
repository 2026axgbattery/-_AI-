"""backend/db/repository.py의 batch_update_manual_field 테스트.

ProcessData는 append-only라 같은 lot_id가 여러 행을 가질 수 있는데, 기존 구현은 선택·갱신
둘 다 "그 로트의 아무 ProcessData 행"을 기준으로 해서 (1) 최신 행에 이미 값이 있어도 옛 행이
NULL이면 overwrite=False를 어기고 선택되고, (2) 선택되면 최신 행까지 포함해 전부 덮어써
이미 채워진 최신 값을 조용히 되돌리는 버그가 있었다(코드 리뷰로 발견, 2026-09-30). 로트당
최신 행(id 최댓값)만 보도록 고친 것을 여기서 고정한다.
"""
from backend.db import repository as repo


def _process_row(lot_id: str, electrolyte_temp: str | None) -> dict:
    return {
        "lot_id": lot_id, "model_name": "AGM90_S1", "prod_date": "2026-09-01", "line_no": "1",
        "cell1_weight": "3.0", "cell2_weight": "3.0", "cell3_weight": "3.0",
        "cell4_weight": "3.0", "cell5_weight": "3.0", "cell6_weight": "3.0",
        "cell1_ginap": "50", "cell2_ginap": "50", "cell3_ginap": "50",
        "cell4_ginap": "50", "cell5_ginap": "50", "cell6_ginap": "50",
        "fill_weight": "5900", "water_loss": "250",
        "voltage_1st": "12.8", "bath_no": "1", "circuit_no": "1",
        "soaking_time_sec": "90", "aging_days": "7", "voltage_2nd": "12.9",
        "electrolyte_temp": electrolyte_temp, "charge_amount": "100.0", "tank_temp": "27.0",
    }


def _setup_db(tmp_path, monkeypatch):
    monkeypatch.setattr(repo, "DB_PATH", tmp_path / "test.db")
    repo.init_db()
    return repo.get_connection()


def test_batch_update_ignores_stale_row_when_latest_already_has_value(tmp_path, monkeypatch):
    """옛 행이 NULL이어도 최신 행에 이미 값이 있으면 overwrite=False에서 선택·갱신되지 않는다."""
    conn = _setup_db(tmp_path, monkeypatch)
    try:
        repo.ingest_process_rows(conn, [_process_row("LOT_A", None)])
        repo.ingest_process_rows(conn, [_process_row("LOT_A", "31.5")])  # 재업로드(최신 행)

        result = repo.batch_update_manual_field(
            conn, "electrolyte_temp", {"model_name": "AGM90_S1", "prod_date": "2026-09-01"}, 99.0,
            overwrite=False,
        )

        assert result["updated_lot_ids"] == []
        latest = conn.execute(
            "SELECT electrolyte_temp FROM ProcessData WHERE lot_id = 'LOT_A' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert latest["electrolyte_temp"] == 31.5  # 그대로 유지, 99.0으로 덮이지 않음
    finally:
        conn.close()


def test_batch_update_only_touches_latest_row_not_history(tmp_path, monkeypatch):
    """overwrite=True로 갱신될 때도 최신 행만 바뀌고 과거 행은 그대로 남아야 한다."""
    conn = _setup_db(tmp_path, monkeypatch)
    try:
        repo.ingest_process_rows(conn, [_process_row("LOT_A", "20.0")])
        repo.ingest_process_rows(conn, [_process_row("LOT_A", "21.0")])  # 최신 행

        result = repo.batch_update_manual_field(
            conn, "electrolyte_temp", {"model_name": "AGM90_S1", "prod_date": "2026-09-01"}, 30.0,
            overwrite=True,
        )

        assert result["updated_lot_ids"] == ["LOT_A"]
        rows = conn.execute(
            "SELECT id, electrolyte_temp FROM ProcessData WHERE lot_id = 'LOT_A' ORDER BY id ASC"
        ).fetchall()
        assert [r["electrolyte_temp"] for r in rows] == [20.0, 30.0]  # 과거 행은 그대로, 최신 행만 갱신
    finally:
        conn.close()


def test_batch_update_missing_group_key_raises_value_error(tmp_path, monkeypatch):
    conn = _setup_db(tmp_path, monkeypatch)
    try:
        repo.ingest_process_rows(conn, [_process_row("LOT_A", None)])
        try:
            repo.batch_update_manual_field(conn, "electrolyte_temp", {"model_name": "AGM90_S1"}, 30.0)
            assert False, "prod_date 누락이면 ValueError가 나야 한다"
        except ValueError:
            pass
    finally:
        conn.close()
