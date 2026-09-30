"""EN/SAE CCA 규격(형명 무관 고정 기준) 판정. 순수 함수만 둔다(웹 프레임워크·DB 비의존).

`history/20_cca-en-sae-규격판정-대시보드-상세분석-반영-계획.md` 기준 — `ConstantsByModel`의
형명별 SPEC(Y/Z)과는 별개로, EN 50342/SAE J537 표준이 정한 고정 전압·시간 임계값을 만족하는지만
판정한다. 표본이 극히 적어(SAE/EN 각 2건) 회귀가 아니라 배지 표시 목적이다.
"""
from __future__ import annotations

from backend.config.spec_thresholds import (
    EN_CCA_6V_HOLD_SEC_MIN,
    EN_CCA_10S_VOLTAGE_MIN,
    SAE_CCA_7V2_HOLD_SEC_MIN,
)


def judge_en_cca(voltage_10s: float | None, hold_6v_sec: float | None) -> dict:
    """EN CCA 합격 조건: 10초 전압 ≥7.5V AND 6.0V까지 지속시간 ≥90초(둘 다 있어야 판정 가능)."""
    if voltage_10s is None or hold_6v_sec is None:
        return {
            "result": None,
            "voltage_10s": voltage_10s,
            "hold_6v_sec": hold_6v_sec,
            "voltage_10s_min": EN_CCA_10S_VOLTAGE_MIN,
            "hold_6v_sec_min": EN_CCA_6V_HOLD_SEC_MIN,
            "note": "측정값 없음, 판정 불가",
        }
    passed = voltage_10s >= EN_CCA_10S_VOLTAGE_MIN and hold_6v_sec >= EN_CCA_6V_HOLD_SEC_MIN
    return {
        "result": "pass" if passed else "fail",
        "voltage_10s": voltage_10s,
        "hold_6v_sec": hold_6v_sec,
        "voltage_10s_min": EN_CCA_10S_VOLTAGE_MIN,
        "hold_6v_sec_min": EN_CCA_6V_HOLD_SEC_MIN,
        "note": None,
    }


def judge_sae_cca(hold_7v2_sec: float | None) -> dict:
    """SAE CCA 합격 조건: 7.2V까지 지속시간 ≥30초."""
    if hold_7v2_sec is None:
        return {
            "result": None,
            "hold_7v2_sec": hold_7v2_sec,
            "hold_7v2_sec_min": SAE_CCA_7V2_HOLD_SEC_MIN,
            "note": "측정값 없음, 판정 불가",
        }
    passed = hold_7v2_sec >= SAE_CCA_7V2_HOLD_SEC_MIN
    return {
        "result": "pass" if passed else "fail",
        "hold_7v2_sec": hold_7v2_sec,
        "hold_7v2_sec_min": SAE_CCA_7V2_HOLD_SEC_MIN,
        "note": None,
    }


def _empty_cca_pass_rate_agg() -> dict:
    return {"en_cca_evaluated": 0, "en_cca_pass": 0, "sae_cca_evaluated": 0, "sae_cca_pass": 0}


def aggregate_cca_pass_rates(checkpoints: list[dict], group_by: str | None = None) -> dict:
    """체크포인트 행 목록에 `judge_en_cca`/`judge_sae_cca`를 적용해 평가/합격 건수를 집계한다.

    `routers/dashboard.py`의 `GET /api/kpi`(형명 구분 없는 전체 집계)와
    `routers/detail_analysis.py`의 `GET /api/models/summary`(형명별 집계)가 이 판정 로직을
    각자 인라인으로 중복 구현하고 있었다 — 판정 기준이 바뀌면 두 곳을 따로 고쳐야 하는 문제를
    막기 위해 하나로 합친다. `group_by`를 안 주면 전체 합계 dict 하나, 주면 그 컬럼(예:
    "model_name") 값별로 나눈 dict[값, 집계]를 반환한다."""
    if group_by is None:
        agg = _empty_cca_pass_rate_agg()
        for c in checkpoints:
            en = judge_en_cca(c["en_cca_10s_voltage"], c["en_cca_6v_hold_sec"])
            if en["result"] is not None:
                agg["en_cca_evaluated"] += 1
                agg["en_cca_pass"] += en["result"] == "pass"
            sae = judge_sae_cca(c["sae_cca_7v2_hold_sec"])
            if sae["result"] is not None:
                agg["sae_cca_evaluated"] += 1
                agg["sae_cca_pass"] += sae["result"] == "pass"
        return agg

    by_group: dict[str, dict] = {}
    for c in checkpoints:
        agg = by_group.setdefault(c[group_by], _empty_cca_pass_rate_agg())
        en = judge_en_cca(c["en_cca_10s_voltage"], c["en_cca_6v_hold_sec"])
        if en["result"] is not None:
            agg["en_cca_evaluated"] += 1
            agg["en_cca_pass"] += en["result"] == "pass"
        sae = judge_sae_cca(c["sae_cca_7v2_hold_sec"])
        if sae["result"] is not None:
            agg["sae_cca_evaluated"] += 1
            agg["sae_cca_pass"] += sae["result"] == "pass"
    return by_group
