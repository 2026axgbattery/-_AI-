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
