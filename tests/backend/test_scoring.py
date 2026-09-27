"""backend/analysis/scoring.py 단위 테스트(.docs/24).

시험 매칭 로트를 "그때그때 재학습 + 예측 판정 vs 실측 판정 비교"로 채점하는 순수 함수들을
검증한다. 회귀가 노이즈 없는 선형관계를 정확히 재현하는 성질을 이용해, 의도적으로 이상치를
하나 섞어 "불일치(실패 케이스)"가 실제로 잡히는지 확인한다.
"""
from __future__ import annotations

from backend.analysis import scoring
from backend.analysis.regression import X_COLUMNS


def _x_values(i: int) -> dict:
    return {
        "electrolyte_temp": 30 + i * 0.5,
        "tank_temp": 35 + i * 0.3,
        "soaking_time_sec": 70 + i * 1.0,
        "aging_days": 6 + (i % 3),
        "formation_dv": 0.05 + i * 0.001,
        "cell_weight_mean": 3.0 + i * 0.01,
        "cell_weight_std": 0.05 + (i % 4) * 0.005,
        "charge_ratio": 100 + i * 0.2,
        "charge_program_deviation_pct": -2 + i * 0.3,
    }


def _linear(x: dict, intercept: float, coeffs: dict[str, float]) -> float:
    return intercept + sum(coeffs[c] * x[c] for c in coeffs)


_Y_COEFFS = {
    "electrolyte_temp": 0.3, "tank_temp": -0.2, "soaking_time_sec": 0.1,
    "aging_days": 0.5, "formation_dv": 10.0, "cell_weight_mean": 2.0,
    "cell_weight_std": -1.0, "charge_ratio": 0.05, "charge_program_deviation_pct": 0.02,
}
_DISCHARGE_COEFFS = {**{c: 0.01 for c in X_COLUMNS}, "retention_rate": 0.8}
_VOLTAGE_COEFFS = {**{c: 0.001 for c in X_COLUMNS}, "retention_rate": 0.02}
_HOLD6V_COEFFS = {**{c: 0.05 for c in X_COLUMNS}, "retention_rate": 1.0}
_HOLD72_COEFFS = {**{c: 0.02 for c in X_COLUMNS}, "retention_rate": 0.3}


def _base_row(i: int, lot_id: str) -> dict:
    x = _x_values(i)
    retention_rate = _linear(x, 40.0, _Y_COEFFS)
    x_with_y = {**x, "retention_rate": retention_rate}
    discharge_amount = _linear(x_with_y, 40.0, _DISCHARGE_COEFFS)
    rated_capacity = 70.0
    return {
        "lot_id": lot_id,
        "rated_capacity": rated_capacity,
        "retention_rate": retention_rate,
        "discharge_amount": discharge_amount,
        "capacity_rate": discharge_amount / rated_capacity * 100,
        "en_cca_10s_voltage": _linear(x_with_y, 7.0, _VOLTAGE_COEFFS),
        "en_cca_6v_hold_sec": _linear(x_with_y, 30.0, _HOLD6V_COEFFS),
        "sae_cca_7v2_hold_sec": _linear(x_with_y, 10.0, _HOLD72_COEFFS),
        "spec_lower_y": 55.0,
        "spec_lower_z": 100.0,
        **x,
    }


def _rows(n: int, outlier_index: int | None = None, outlier_delta: float = 500.0) -> list[dict]:
    rows = [_base_row(i, f"LOT_{i}") for i in range(n)]
    if outlier_index is not None:
        rows[outlier_index]["retention_rate"] += outlier_delta
    return rows


def test_score_y_all_match_on_clean_linear_data():
    rows = _rows(13)
    result = scoring.score_target("y", rows)
    assert result["target"] == "y"
    assert result["n_total"] == 13
    assert result["n_scorable"] == 13
    assert result["n_mismatched"] == 0
    assert result["success_rate_pct"] == 100.0
    assert result["reliable"] is True
    assert result["mismatched_lots"] == []


def test_score_y_detects_outlier_as_mismatch():
    # 이상치 한 건(LOT_5)의 실측 retention_rate를 크게 틀어놓으면, 회귀선(다른 12건에 맞춰짐)이
    # 예측한 값과 실측값이 spec_lower_y=55를 사이에 두고 서로 다른 쪽에 위치해 불일치가 발생한다.
    rows = _rows(13, outlier_index=5, outlier_delta=-40.0)
    result = scoring.score_target("y", rows)
    assert result["n_mismatched"] >= 1
    mismatched_lot_ids = {r["lot_id"] for r in result["mismatched_lots"]}
    assert "LOT_5" in mismatched_lot_ids
    assert result["success_rate_pct"] < 100.0


def test_score_y_insufficient_sample_returns_empty_result_with_note():
    rows = _rows(3)
    result = scoring.score_target("y", rows)
    assert result["n_scorable"] == 0
    assert result["n_matched"] == 0
    assert result["success_rate_pct"] is None
    assert result["reliable"] is None
    assert result["note"] is not None


def test_score_z_uses_capacity_rate_and_rated_capacity():
    rows = _rows(14)
    result = scoring.score_target("z", rows)
    assert result["target"] == "z"
    assert result["n_scorable"] == 14
    assert result["n_mismatched"] == 0
    assert result["reliable"] is True


def test_score_en_cca_spec_has_no_scalar_value_only_spec_result():
    rows = _rows(14)
    result = scoring.score_target("en_cca_spec", rows)
    assert result["target"] == "en_cca_spec"
    assert result["n_scorable"] == 14
    for r in result["results"]:
        assert r["predicted_value"] is None
        assert r["actual_value"] is None
        assert r["predicted_spec_result"] in ("pass", "fail")
        assert r["actual_spec_result"] in ("pass", "fail")


def test_score_sae_cca_spec_matches_on_clean_linear_data():
    rows = _rows(14)
    result = scoring.score_target("sae_cca_spec", rows)
    assert result["target"] == "sae_cca_spec"
    assert result["n_scorable"] == 14
    assert result["n_mismatched"] == 0


def test_score_target_rejects_unknown_target():
    try:
        scoring.score_target("bogus", [])
    except ValueError as exc:
        assert "bogus" in str(exc)
    else:
        raise AssertionError("ValueError를 기대했지만 발생하지 않았습니다")
