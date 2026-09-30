"""피어슨 상관계수 + p-value. `docs/correlation-reliability-review.md`와 동일한 유의수준(0.05)을 쓴다.

순수 함수만 둔다(웹 프레임워크·DB 비의존) — `backend/analysis/derive.py`와 같은 원칙.
"""
from __future__ import annotations

import math

from scipy.stats import pearsonr

SIGNIFICANCE_LEVEL = 0.05


def pearson_r_p(x: list[float], y: list[float]) -> dict:
    """x, y 사이 피어슨 r과 p-value. 표본이 3개 미만이면 계산 불가로 None을 반환한다."""
    n = len(x)
    if n < 3 or n != len(y):
        return {"r": None, "p_value": None, "significant": False, "n": n}
    r, p = pearsonr(x, y)
    r_value, p_value = float(r), float(p)
    # x 또는 y의 분산이 0(값이 전부 동일)이면 scipy가 예외 없이 nan/nan을 반환한다 — 표준 JSON은
    # NaN 리터럴을 지원하지 않아 그대로 내보내면 프런트 res.json() 파싱이 깨진다(vif.py가
    # Infinity를 캡핑하는 것과 같은 문제 클래스). 계산 불가로 None 처리한다.
    if math.isnan(r_value) or math.isnan(p_value):
        return {"r": None, "p_value": None, "significant": False, "n": n}
    return {"r": r_value, "p_value": p_value, "significant": bool(p_value < SIGNIFICANCE_LEVEL), "n": n}
