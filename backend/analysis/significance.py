"""피어슨 상관계수 + p-value. `docs/correlation-reliability-review.md`와 동일한 유의수준(0.05)을 쓴다.

순수 함수만 둔다(웹 프레임워크·DB 비의존) — `backend/analysis/derive.py`와 같은 원칙.
"""
from __future__ import annotations

from scipy.stats import pearsonr

SIGNIFICANCE_LEVEL = 0.05


def pearson_r_p(x: list[float], y: list[float]) -> dict:
    """x, y 사이 피어슨 r과 p-value. 표본이 3개 미만이면 계산 불가로 None을 반환한다."""
    n = len(x)
    if n < 3 or n != len(y):
        return {"r": None, "p_value": None, "significant": False, "n": n}
    r, p = pearsonr(x, y)
    return {"r": float(r), "p_value": float(p), "significant": bool(p < SIGNIFICANCE_LEVEL), "n": n}
