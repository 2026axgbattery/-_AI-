"""기준표 자동 시드·표본 부족 원인 설명 회귀 테스트(.docs/41)."""

import pytest

from backend.db import repository as repo


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(repo, "DB_PATH", tmp_path / "t.db")
    repo.init_db()  # 빈 DB 기동 → 시드 자동 적재
    c = repo.get_connection()
    yield c
    c.close()


def test_init_db_seeds_empty_charge_program(conn):
    n = conn.execute("SELECT COUNT(*) AS n FROM ChargeProgramSpec").fetchone()["n"]
    assert n > 0


def test_seed_is_noop_when_specs_exist(conn):
    assert repo.seed_charge_program_if_empty(conn)["seeded"] is False


def test_seed_recovers_after_spec_wiped_and_backfills_lots(conn):
    spec = conn.execute(
        "SELECT rated_capacity, buyer_code FROM ChargeProgramSpec LIMIT 1"
    ).fetchone()
    model = f"AGM{int(spec['rated_capacity'])}_{spec['buyer_code']}1"
    conn.execute("DELETE FROM ChargeProgramSpec")
    row = {
        "lot_id": "L1", "model_name": model, "rated_capacity": spec["rated_capacity"],
        "prod_date": "2026-01-01", "line_no": "1", "electrolyte_temp": 25, "tank_temp": 25,
        "soaking_time_sec": 100, "aging_days": 1, "charge_amount": 70, "fill_weight": 100,
        "water_loss": 5, "voltage_1st": 2.0, "voltage_2nd": 2.1,
        **{f"cell{i}_weight": 1000 + i for i in range(1, 7)},
    }
    repo.ingest_process_rows(conn, [{k: str(v) for k, v in row.items()}])
    assert repo.get_charge_program_coverage(conn)["unmatched_lot_count"] == 1
    assert "비어 있어" in repo.explain_charge_program_shortage(conn)
    assert repo.seed_charge_program_if_empty(conn)["seeded"] is True
    assert repo.get_charge_program_coverage(conn)["unmatched_lot_count"] == 0


def test_shortage_message_lists_unmatched_combo(conn):
    row = {
        "lot_id": "L2", "model_name": "AGM50_Q1", "rated_capacity": "50", "prod_date": "2026-01-01",
        "line_no": "1", "electrolyte_temp": "25", "tank_temp": "25", "soaking_time_sec": "1",
        "aging_days": "1", "charge_amount": "55", "fill_weight": "100", "water_loss": "5",
        "voltage_1st": "2.0", "voltage_2nd": "2.1", **{f"cell{i}_weight": "1000" for i in range(1, 7)},
    }
    repo.ingest_process_rows(conn, [row])
    msg = repo.explain_charge_program_shortage(conn)
    assert "50Ah/Q" in msg
