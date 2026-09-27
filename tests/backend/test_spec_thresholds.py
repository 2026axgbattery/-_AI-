from backend.db import repository as repo


def test_upsert_and_get_spec_thresholds(tmp_path, monkeypatch):
    monkeypatch.setattr(repo, "DB_PATH", tmp_path / "test.db")
    repo.init_db()
    conn = repo.get_connection()
    try:
        result = repo.upsert_spec_thresholds(
            conn,
            [
                {"model_name": "AGM105_H1", "rated_capacity": "", "spec_lower_y": "91.5", "spec_lower_z": "96.0"},
                {"model_name": "AGM50_H1", "rated_capacity": "", "spec_lower_y": "", "spec_lower_z": ""},
            ],
        )
        assert result["updated_models"] == ["AGM105_H1", "AGM50_H1"]

        rows = {r["model_name"]: r for r in repo.get_spec_thresholds(conn)}
        assert rows["AGM105_H1"]["rated_capacity"] == 105.0  # model_name에서 자동 역산
        assert rows["AGM105_H1"]["spec_lower_y"] == 91.5
        assert rows["AGM105_H1"]["spec_lower_z"] == 96.0
        # 값이 비어 있으면 NULL로 저장되어야 한다(§10-11 미확정 상태 허용)
        assert rows["AGM50_H1"]["spec_lower_y"] is None
        assert rows["AGM50_H1"]["spec_lower_z"] is None
    finally:
        conn.close()
