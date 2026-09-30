"""로트별 파생 인자(LotDerived) 계산. 순수 함수만 두고 웹 프레임워크·DB에 의존하지 않는다.

근거: docs/prd.md §7 "LotDerived", §6-③ 공통(감액 분해), .docs/03_sqlite-스키마-설계.md.
"""
from __future__ import annotations

from statistics import mean, pstdev

WATER_LOSS_PER_OVERCHARGE_AH = 0.336  # 과충전 1Ah당 물 전기분해 손실(g), docs/domain-constants.md


def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def compute_lot_derived(row: dict) -> dict:
    """row: ProcessData 컬럼(dict) + rated_capacity. 반환값은 LotDerived 테이블 컬럼과 1:1.

    fill_weight/water_loss는 DDL상 NOT NULL이라 항상 존재하지만, charge_amount는
    수기입력 대상이라 아직 비어 있을 수 있다(§6-②) — 이 경우 charge_amount에 의존하는
    파생값은 NULL로 두고, 이후 그룹 일괄 입력으로 채워지면 재계산(UPSERT)한다.
    """
    fill_weight = row["fill_weight"]
    water_loss = row["water_loss"]
    rated_capacity = row["rated_capacity"]
    charge_amount = row.get("charge_amount")
    charge_program_total_ah = row.get("charge_program_total_ah")

    # fill_weight/water_loss는 원칙적으로 항상 있어야 하지만(Y 산출 원천), 실제 raw data에는
    # 해당 공정 단계 자체가 누락된 로트가 있다(.docs/14) — 이 경우 Y 관련 파생값은 모두 NULL로
    # 두고, 그 로트는 1단(X→Y) 분석 대상에서 자연스럽게 제외된다. fill_weight=0(센서/입력 오류)도
    # 같은 취급 — 나눗셈 분모라 0이면 ZeroDivisionError로 업로드 전체가 죽는다.
    has_fill_data = fill_weight is not None and water_loss is not None and fill_weight != 0
    retention_rate = (fill_weight - water_loss) / fill_weight * 100 if has_fill_data else None

    # theoretical_water_loss/water_loss_residual: 이론치 대비 실측이 ~139배 차이 나는 것을 사용자가
    # 데이터 오류로 확인(§10-7, 2026-09-27) — SOP 자체가 규명된 것은 아니라 계산은 그대로 두되(값
    # 자체가 나쁘진 않으니 저장은 계속), 원인진단·이상탐지 등 해석에는 당분간 쓰지 않는다(어디서도
    # 소비하지 않음, docs/prd.md §10 참조).
    overcharge_ah = (charge_amount - rated_capacity) if charge_amount is not None else None
    theoretical_water_loss = (
        WATER_LOSS_PER_OVERCHARGE_AH * overcharge_ah if overcharge_ah is not None else None
    )
    water_loss_residual = (
        water_loss - theoretical_water_loss
        if theoretical_water_loss is not None and water_loss is not None
        else None
    )
    water_loss_per_ah = _safe_div(water_loss, overcharge_ah)

    fill_per_rated = _safe_div(fill_weight, rated_capacity)
    charge_ratio_raw = _safe_div(charge_amount, rated_capacity)
    charge_ratio = charge_ratio_raw * 100 if charge_ratio_raw is not None else None

    cell_weights = [
        row.get(f"cell{i}_weight") for i in range(1, 7) if row.get(f"cell{i}_weight") is not None
    ]
    cell_weight_mean = mean(cell_weights) if cell_weights else None
    cell_weight_std = pstdev(cell_weights) if len(cell_weights) > 1 else None

    voltage_1st = row.get("voltage_1st")
    voltage_2nd = row.get("voltage_2nd")
    formation_dv = (
        voltage_2nd - voltage_1st if voltage_1st is not None and voltage_2nd is not None else None
    )

    # 신규(history/19 Phase B): 실제 총 충전량이 형명·바이어별 충전 STEP 프로그램의 Total
    # 충전량[Ah] 대비 얼마나 벗어났는지(%). 매칭되는 프로그램이 없으면(ChargeProgramSpec에
    # 해당 정격용량·바이어 코드가 없음) NULL로 남긴다 — 지어내지 않음.
    charge_program_deviation_pct = (
        (charge_amount - charge_program_total_ah) / charge_program_total_ah * 100
        if charge_amount is not None and charge_program_total_ah not in (None, 0)
        else None
    )

    return {
        "retention_rate": retention_rate,
        "water_loss_rate": water_loss / fill_weight * 100 if has_fill_data else None,
        "water_loss_per_ah": water_loss_per_ah,
        "theoretical_water_loss": theoretical_water_loss,
        "water_loss_residual": water_loss_residual,
        "fill_per_rated": fill_per_rated,
        "charge_ratio": charge_ratio,
        "cell_weight_mean": cell_weight_mean,
        "cell_weight_std": cell_weight_std,
        "formation_dv": formation_dv,
        "saturation_calc": None,
        "saturation_basis": "proxy_retention",
        "saturation_source": "derived",
        "charge_program_deviation_pct": charge_program_deviation_pct,
    }


def parse_rated_capacity_from_model_name(model_name: str) -> float:
    """model_name(예: AGM105_S1)의 숫자 접두부를 정격용량(Ah)으로 파싱.

    docs/prd.md §7: "model_name과 1:1 매핑되는 정격용량(Ah), 실측 확인됨". process_data.csv에는
    rated_capacity 컬럼이 없어 model_name에서 역산한다(6개 용량군 50/60/70/80/90/105Ah 확인됨).
    """
    import re

    match = re.match(r"[A-Za-z]+(\d+)_", model_name)
    if not match:
        raise ValueError(f"model_name에서 정격용량을 추출할 수 없습니다: {model_name!r}")
    return float(match.group(1))


def extract_buyer_code_from_model_name(model_name: str) -> str | None:
    """model_name(예: AGM70_H2)의 접미부에서 바이어/스펙 구분 코드(문자만)를 추출한다.

    docs/prd.md §6: 접미 문자(S/H/K 등)가 바이어(고객사)/스펙 구분 코드 역할. 뒤따르는 숫자는
    버전/로트 순번 등 다른 구분이라 충전 프로그램 매칭에는 영향 없음(history/19 Phase B 확인).
    형식을 인식 못 하면 None(호출 측에서 매칭 없이 NULL 처리).
    """
    import re

    match = re.match(r"[A-Za-z]+\d+_([A-Za-z]+)", model_name)
    return match.group(1) if match else None
