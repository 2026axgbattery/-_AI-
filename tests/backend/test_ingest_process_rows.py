"""backend/db/repository.py의 ingest_process_rows 행 검증/배치 조회 리팩터 회귀 테스트.

코드 리뷰(2026-09-30)로 두 가지가 발견됐다: (1) 헤더보다 짧은/빈 셀이 있는 행은
raw["lot_id"].strip()에서 AttributeError로 배치 전체가 죽었다(이제 그 행만 건너뛴다). (2) 대량
업로드 성능을 위해 "기존 lot_id 조회"를 행마다 SELECT하던 것을 배치 시작 시 한 번만 불러온
집합으로 바꿨는데, 이 리팩터가 같은 배치 안의 중복 lot_id(재조회 없이 집합만 갱신)까지 여전히
잡아내는지 함께 확인한다.
"""
from backend.db import repository as repo


def _process_row(lot_id, model_name="AGM90_S1", prod_date="2026-09-01") -> dict:
    return {
        "lot_id": lot_id, "model_name": model_name, "prod_date": prod_date, "line_no": "1",
        "cell1_weight": "3.0", "cell2_weight": "3.0", "cell3_weight": "3.0",
        "cell4_weight": "3.0", "cell5_weight": "3.0", "cell6_weight": "3.0",
        "cell1_ginap": "50", "cell2_ginap": "50", "cell3_ginap": "50",
        "cell4_ginap": "50", "cell5_ginap": "50", "cell6_ginap": "50",
        "fill_weight": "5900", "water_loss": "250",
        "voltage_1st": "12.8", "bath_no": "1", "circuit_no": "1",
        "soaking_time_sec": "90", "aging_days": "7", "voltage_2nd": "12.9",
        "electrolyte_temp": "31.0", "charge_amount": "100.0", "tank_temp": "27.0",
    }


def _setup_db(tmp_path, monkeypatch):
    monkeypatch.setattr(repo, "DB_PATH", tmp_path / "test.db")
    repo.init_db()
    return repo.get_connection()


def test_blank_lot_id_row_is_skipped_not_a_crash(tmp_path, monkeypatch):
    conn = _setup_db(tmp_path, monkeypatch)
    try:
        blank_row = _process_row(None)  # csv.DictReader가 헤더보다 짧은 행에 채워 넣는 None을 흉내
        result = repo.ingest_process_rows(conn, [blank_row, _process_row("LOT_A")])

        assert result["inserted_process_rows"] == 1
        assert len(result["skipped_invalid_rows"]) == 1
        assert result["skipped_invalid_rows"][0]["lot_id"] is None
        assert conn.execute("SELECT COUNT(*) AS n FROM Lot").fetchone()["n"] == 1
    finally:
        conn.close()


def test_unparseable_model_name_row_is_skipped_not_a_crash(tmp_path, monkeypatch):
    conn = _setup_db(tmp_path, monkeypatch)
    try:
        bad_row = _process_row("LOT_BAD", model_name="정체불명")
        result = repo.ingest_process_rows(conn, [bad_row, _process_row("LOT_A")])

        assert result["inserted_process_rows"] == 1
        assert len(result["skipped_invalid_rows"]) == 1
        assert result["skipped_invalid_rows"][0]["lot_id"] == "LOT_BAD"
        assert conn.execute("SELECT COUNT(*) AS n FROM Lot WHERE lot_id = 'LOT_BAD'").fetchone()["n"] == 0
    finally:
        conn.close()


def test_duplicate_lot_id_within_same_batch_is_still_detected(tmp_path, monkeypatch):
    """기존 lot_id 조회를 행마다 SELECT하지 않고 배치 시작 시 한 번만 집합으로 올리도록 바꿨어도,
    같은 배치 안에서 나중에 나오는 중복 lot_id는 여전히 duplicate로 잡혀야 한다(집합에 즉시 추가)."""
    conn = _setup_db(tmp_path, monkeypatch)
    try:
        result = repo.ingest_process_rows(conn, [_process_row("LOT_A"), _process_row("LOT_A")])

        assert result["inserted_lots"] == 1
        assert result["duplicate_lot_ids"] == ["LOT_A"]
        assert result["inserted_process_rows"] == 2  # ProcessData는 append-only라 둘 다 저장됨
    finally:
        conn.close()
