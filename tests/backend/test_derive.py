from backend.analysis.derive import (
    compute_lot_derived,
    extract_buyer_code_from_model_name,
    parse_rated_capacity_from_model_name,
)


def test_parse_rated_capacity_from_model_name():
    assert parse_rated_capacity_from_model_name("AGM105_S1") == 105.0
    assert parse_rated_capacity_from_model_name("AGM50_H3") == 50.0


def test_extract_buyer_code_from_model_name():
    """history/19 Phase B: 접미 문자만 바이어 코드로 본다(뒤 숫자는 무시, 사용자 확인)."""
    assert extract_buyer_code_from_model_name("AGM70_H2") == "H"
    assert extract_buyer_code_from_model_name("AGM105_S1") == "S"
    assert extract_buyer_code_from_model_name("AGM90_All") == "All"
    assert extract_buyer_code_from_model_name("이상한형식") is None


def test_compute_lot_derived_charge_program_deviation_pct():
    """history/19 Phase B: 실제 충전량이 충전 프로그램 Total 충전량[Ah] 대비 얼마나 벗어났는지(%)."""
    row = {
        "fill_weight": 100.0, "water_loss": 10.0, "rated_capacity": 70.0,
        "charge_amount": 470.0, "charge_program_total_ah": 456.5,
    }
    result = compute_lot_derived(row)
    assert round(result["charge_program_deviation_pct"], 4) == round((470.0 - 456.5) / 456.5 * 100, 4)


def test_compute_lot_derived_charge_program_deviation_pct_null_when_no_program_match():
    row = {
        "fill_weight": 100.0, "water_loss": 10.0, "rated_capacity": 70.0,
        "charge_amount": 470.0, "charge_program_total_ah": None,
    }
    result = compute_lot_derived(row)
    assert result["charge_program_deviation_pct"] is None


def test_compute_lot_derived_retention_rate():
    row = {
        "fill_weight": 100.0,
        "water_loss": 10.0,
        "rated_capacity": 50.0,
        "charge_amount": 60.0,
        "voltage_1st": 2.10,
        "voltage_2nd": 2.15,
        "cell1_weight": 4.0, "cell2_weight": 4.2, "cell3_weight": 4.1,
        "cell4_weight": 4.0, "cell5_weight": 4.3, "cell6_weight": 4.1,
    }
    result = compute_lot_derived(row)

    assert result["retention_rate"] == 90.0  # (100-10)/100*100
    assert result["water_loss_rate"] == 10.0
    overcharge_ah = 60.0 - 50.0
    assert result["theoretical_water_loss"] == 0.336 * overcharge_ah
    assert result["water_loss_residual"] == 10.0 - 0.336 * overcharge_ah
    assert result["charge_ratio"] == 60.0 / 50.0 * 100
    assert result["fill_per_rated"] == 100.0 / 50.0
    assert round(result["formation_dv"], 10) == round(2.15 - 2.10, 10)
    assert result["saturation_calc"] is None
    assert result["saturation_basis"] == "proxy_retention"
    assert result["saturation_source"] == "derived"


def test_compute_lot_derived_missing_charge_amount_is_null_not_error():
    row = {
        "fill_weight": 100.0,
        "water_loss": 10.0,
        "rated_capacity": 50.0,
        "charge_amount": None,
        "voltage_1st": None,
        "voltage_2nd": None,
    }
    result = compute_lot_derived(row)

    assert result["retention_rate"] == 90.0  # charge_amount 없이도 계산 가능해야 함
    assert result["charge_ratio"] is None
    assert result["theoretical_water_loss"] is None
    assert result["water_loss_residual"] is None
    assert result["formation_dv"] is None


def test_compute_lot_derived_missing_fill_weight_is_null_not_error():
    """실제 raw data에는 Filling/Pre Test(Weight) 단계 자체가 누락된 로트가 있다(.docs/14).
    이 경우 Y(retention_rate) 관련 파생값은 모두 NULL이어야 하며 예외가 나면 안 된다."""
    row = {
        "fill_weight": None,
        "water_loss": None,
        "rated_capacity": 50.0,
        "charge_amount": 60.0,
        "voltage_1st": 2.10,
        "voltage_2nd": 2.15,
    }
    result = compute_lot_derived(row)

    assert result["retention_rate"] is None
    assert result["water_loss_rate"] is None
    assert result["water_loss_residual"] is None
    assert result["fill_per_rated"] is None
    assert result["formation_dv"] is not None  # fill_weight와 무관한 값은 그대로 계산됨


def test_compute_lot_derived_zero_fill_weight_is_null_not_zero_division_error():
    """fill_weight=0(센서/입력 오류로 인한 값, None이 아니라 유효한 float 0.0)도 missing_fill_weight
    케이스와 동일하게 NULL로 처리해야 한다 — None 체크만으로는 못 막아 ZeroDivisionError로
    업로드 전체가 500이 나던 버그(코드 리뷰로 발견, 2026-09-30)."""
    row = {
        "fill_weight": 0.0,
        "water_loss": 5.0,
        "rated_capacity": 50.0,
        "charge_amount": 60.0,
        "voltage_1st": 2.10,
        "voltage_2nd": 2.15,
    }
    result = compute_lot_derived(row)

    assert result["retention_rate"] is None
    assert result["water_loss_rate"] is None
    assert result["fill_per_rated"] == 0.0  # fill_weight가 분자일 뿐이라 0/rated_capacity는 정상 계산
