from backend.analysis.diagnosis import compute_factor_means, judge_spec, rank_causes


def test_compute_factor_means_averages_non_null_values():
    rows = [
        {"electrolyte_temp": 30.0, "tank_temp": 25.0},
        {"electrolyte_temp": 32.0, "tank_temp": None},
        {"electrolyte_temp": 34.0, "tank_temp": 27.0},
    ]
    means = compute_factor_means(rows, ["electrolyte_temp", "tank_temp"])
    assert means["electrolyte_temp"] == 32.0
    assert means["tank_temp"] == 26.0


def test_compute_factor_means_omits_column_with_no_values():
    rows = [{"electrolyte_temp": None}]
    means = compute_factor_means(rows, ["electrolyte_temp"])
    assert "electrolyte_temp" not in means


def test_judge_spec_pass_when_value_meets_lower_bound():
    result = judge_spec(95.0, spec_lower=91.0)
    assert result["spec_result"] == "pass"
    assert result["deviation"] == 4.0


def test_judge_spec_fail_when_value_below_lower_bound():
    result = judge_spec(90.4, spec_lower=91.0)
    assert result["spec_result"] == "fail"
    assert round(result["deviation"], 2) == -0.6


def test_judge_spec_returns_not_configured_when_spec_lower_missing():
    result = judge_spec(90.4, spec_lower=None)
    assert result["spec_result"] is None
    assert result["note"] == "SPEC 미설정, 판정 불가"


def test_judge_spec_handles_missing_value():
    result = judge_spec(None, spec_lower=91.0)
    assert result["spec_result"] is None
    assert result["note"] == "예측값 없음"


def test_rank_causes_orders_by_absolute_contribution_descending():
    x_columns = ["electrolyte_temp", "cell_weight_std", "charge_ratio"]
    coefficients = {"electrolyte_temp": 0.22, "cell_weight_std": -0.35, "charge_ratio": 0.17}
    x_values = {"electrolyte_temp": 38.4, "cell_weight_std": 1.4, "charge_ratio": 108.0}
    factor_means = {"electrolyte_temp": 31.2, "cell_weight_std": 0.8, "charge_ratio": 112.0}

    ranked = rank_causes(x_columns, coefficients, x_values, factor_means, top_n=3)

    # 기여도: electrolyte_temp=0.22*7.2=1.584, cell_weight_std=-0.35*0.6=-0.21, charge_ratio=0.17*-4=-0.68
    assert [r["factor"] for r in ranked] == ["electrolyte_temp", "charge_ratio", "cell_weight_std"]
    assert ranked[0]["rank"] == 1
    assert "훈련 데이터 평균보다 높습니다" in ranked[0]["recommendation"]


def test_rank_causes_respects_top_n():
    x_columns = ["electrolyte_temp", "cell_weight_std", "charge_ratio", "tank_temp"]
    coefficients = {
        "electrolyte_temp": 0.22, "cell_weight_std": -0.35, "charge_ratio": 0.17, "tank_temp": 0.06,
    }
    x_values = {"electrolyte_temp": 38.4, "cell_weight_std": 1.4, "charge_ratio": 108.0, "tank_temp": 30.0}
    factor_means = {
        "electrolyte_temp": 31.2, "cell_weight_std": 0.8, "charge_ratio": 112.0, "tank_temp": 27.0,
    }

    ranked = rank_causes(x_columns, coefficients, x_values, factor_means, top_n=2)
    assert len(ranked) == 2


def test_rank_causes_skips_columns_missing_from_inputs():
    x_columns = ["electrolyte_temp", "unknown_col"]
    coefficients = {"electrolyte_temp": 0.22}
    x_values = {"electrolyte_temp": 38.4}
    factor_means = {"electrolyte_temp": 31.2}

    ranked = rank_causes(x_columns, coefficients, x_values, factor_means)
    assert len(ranked) == 1
    assert ranked[0]["factor"] == "electrolyte_temp"


def test_rank_causes_tie_break_uses_coefficient_then_alphabetical():
    # 두 인자의 |contribution|이 같도록 구성(0.1*10=1.0, 0.2*5=1.0) — 계수 절댓값 큰 쪽이 우선
    x_columns = ["low_coef_factor", "high_coef_factor"]
    coefficients = {"low_coef_factor": 0.1, "high_coef_factor": 0.2}
    x_values = {"low_coef_factor": 10.0, "high_coef_factor": 5.0}
    factor_means = {"low_coef_factor": 0.0, "high_coef_factor": 0.0}

    ranked = rank_causes(x_columns, coefficients, x_values, factor_means)
    assert ranked[0]["factor"] == "high_coef_factor"
    assert ranked[1]["factor"] == "low_coef_factor"
