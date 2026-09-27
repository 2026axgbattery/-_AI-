import pytest

from backend.analysis.regression import (
    X_COLUMNS,
    InsufficientSampleError,
    fit_x_to_y,
    fit_x_to_z_baseline,
    fit_xy_to_z,
    predict,
)


def _make_rows(n: int) -> list[dict]:
    rows = []
    for i in range(n):
        electrolyte_temp = 30 + i * 0.1
        charge_ratio = 100 + (i % 8) * 0.5
        row = {
            "electrolyte_temp": electrolyte_temp,
            "tank_temp": 35 + (i % 5) * 0.2,
            "soaking_time_sec": 80 + (i % 7),
            "aging_days": 5 + (i % 3),
            "formation_dv": 0.05 + (i % 4) * 0.01,
            "cell_weight_mean": 4.0 + (i % 6) * 0.05,
            "cell_weight_std": 0.1 + (i % 3) * 0.02,
            "charge_ratio": charge_ratio,
            "charge_program_deviation_pct": (i % 9) * 0.7 - 2.5,
        }
        # 정확한 선형식(잡음 없음): electrolyte_temp·charge_ratio만 실제 영향을 준다.
        row["retention_rate"] = 50 + 2 * electrolyte_temp - 1 * charge_ratio
        row["discharge_amount"] = 10 + 0.5 * electrolyte_temp + 3 * row["retention_rate"] / 100
        rows.append(row)
    return rows


def test_fit_x_to_y_recovers_known_linear_relationship():
    rows = _make_rows(30)
    result = fit_x_to_y(rows)

    assert result["n"] == 30
    assert result["r_squared"] > 0.999
    assert round(result["coefficients"]["electrolyte_temp"], 3) == 2.0
    assert round(result["coefficients"]["charge_ratio"], 3) == -1.0
    for col in X_COLUMNS:
        if col not in ("electrolyte_temp", "charge_ratio"):
            assert abs(result["coefficients"][col]) < 1e-6
    assert set(result["vif"].keys()) == set(X_COLUMNS)
    assert set(result["significance"].keys()) == set(X_COLUMNS)


def test_fit_x_to_y_raises_on_insufficient_sample():
    rows = _make_rows(3)  # X_COLUMNS(9개)+2 = 11건 미만
    with pytest.raises(InsufficientSampleError):
        fit_x_to_y(rows)


def test_fit_x_to_y_skips_rows_with_missing_values():
    rows = _make_rows(15)
    rows[0]["electrolyte_temp"] = None  # 수기입력 미완료 로트 시뮬레이션
    result = fit_x_to_y(rows)
    assert result["n"] == 14


def test_fit_xy_to_z_uses_retention_rate_as_extra_input():
    rows = _make_rows(30)
    result = fit_xy_to_z(rows)
    assert result["x_columns"] == [*X_COLUMNS, "retention_rate"]
    assert result["target"] == "discharge_amount"
    assert result["r_squared"] > 0.999


def test_fit_x_to_z_baseline_excludes_retention_rate():
    rows = _make_rows(30)
    result = fit_x_to_z_baseline(rows)
    assert result["x_columns"] == X_COLUMNS
    assert "retention_rate" not in result["coefficients"]


def test_predict_applies_coefficients_and_intercept():
    value = predict({"a": 2.0, "b": -1.0}, intercept=5.0, x={"a": 10.0, "b": 3.0})
    assert value == 5.0 + 2.0 * 10.0 - 1.0 * 3.0
