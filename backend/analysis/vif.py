"""분산팽창계수(VIF) 산출. `statsmodels` 없이 numpy 최소자승법만으로 직접 계산한다
(불필요한 의존성 추가 금지 원칙, `history/15_day2-회귀-대시보드-구현-계획.md` 참조).

VIF_i = 1 / (1 - R_i^2), R_i^2은 컬럼 i를 나머지 컬럼들로 회귀했을 때의 결정계수.
"""
from __future__ import annotations

import numpy as np

# 완전한 다중공선성(R_i^2 == 1)이면 수학적으로 VIF는 무한대다. 그대로 float("inf")를 반환하면
# 표준 JSON(그리고 FastAPI의 기본 JSONResponse)이 Infinity를 직렬화하지 못해 API가 500으로
# 죽는다(history/19 Phase B에서 charge_program_deviation_pct 추가 중 실제로 재현·확인). "매우
# 크다"는 의미만 보존하면 되므로 JSON에 안전한 큰 유한값으로 캡핑한다.
_VIF_INF_CAP = 9999.0


def compute_vif(data: dict[str, list[float]]) -> dict[str, float | None]:
    """data: {컬럼명: 값 리스트(전부 같은 길이)}. 각 컬럼의 VIF를 반환한다.

    나머지 컬럼이 없거나(단일 변수) 표본이 부족하면 해당 컬럼은 None으로 둔다.
    """
    columns = list(data.keys())
    n = len(next(iter(data.values()))) if data else 0

    result: dict[str, float | None] = {}
    for col in columns:
        others = [c for c in columns if c != col]
        if not others or n <= len(others) + 1:
            result[col] = None
            continue

        y = np.array(data[col], dtype=float)
        design = np.column_stack([np.ones(n), *[np.array(data[c], dtype=float) for c in others]])
        try:
            coef, *_ = np.linalg.lstsq(design, y, rcond=None)
        except np.linalg.LinAlgError:
            result[col] = None
            continue

        y_pred = design @ coef
        ss_res = float(np.sum((y - y_pred) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        if ss_tot == 0:
            result[col] = None
            continue
        r_squared = 1 - ss_res / ss_tot
        result[col] = _VIF_INF_CAP if r_squared >= 1 else min(float(1 / (1 - r_squared)), _VIF_INF_CAP)
    return result
