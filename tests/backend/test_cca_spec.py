"""backend/analysis/cca_spec.py 단위 테스트(history/20)."""
from __future__ import annotations

from backend.analysis.cca_spec import judge_en_cca, judge_sae_cca


def test_en_cca_passes_when_both_criteria_met():
    result = judge_en_cca(voltage_10s=7.8, hold_6v_sec=95)
    assert result["result"] == "pass"


def test_en_cca_fails_when_voltage_criterion_not_met():
    result = judge_en_cca(voltage_10s=7.4, hold_6v_sec=95)
    assert result["result"] == "fail"


def test_en_cca_fails_when_hold_time_criterion_not_met():
    result = judge_en_cca(voltage_10s=7.8, hold_6v_sec=89)
    assert result["result"] == "fail"


def test_en_cca_boundary_values_pass():
    result = judge_en_cca(voltage_10s=7.5, hold_6v_sec=90)
    assert result["result"] == "pass"


def test_en_cca_missing_measurement_is_undetermined_not_fail():
    result = judge_en_cca(voltage_10s=None, hold_6v_sec=95)
    assert result["result"] is None
    assert result["note"] is not None


def test_sae_cca_passes_when_hold_time_criterion_met():
    assert judge_sae_cca(hold_7v2_sec=30)["result"] == "pass"
    assert judge_sae_cca(hold_7v2_sec=45)["result"] == "pass"


def test_sae_cca_fails_when_hold_time_criterion_not_met():
    assert judge_sae_cca(hold_7v2_sec=29.9)["result"] == "fail"


def test_sae_cca_missing_measurement_is_undetermined_not_fail():
    result = judge_sae_cca(hold_7v2_sec=None)
    assert result["result"] is None
