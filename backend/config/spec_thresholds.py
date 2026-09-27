"""하드코딩 금지 설정값(docs/prd.md §10-16). 형명별 상세 분석에서 표본 부족 여부를 가릴 임계값.

표본 수가 이 값 미만인 형명은 SPEC 배지 대신 "표본 부족"으로 표시한다(형명당 표본 중앙값이
2~3건으로 매우 작기 때문 — `docs/prd.md` §10, `docs/correlation-reliability-review.md` 참조).
"""
from __future__ import annotations

MIN_SAMPLE_SIZE_FOR_MODEL_DETAIL = 5

# EN 50342 / SAE J537 CCA 규격 고정 임계값(history/20, 2026-09-21 사용자 확인) — 형명별로 다르지
# 않은 업계 표준 판정 기준이라 `ConstantsByModel`(형명별 SPEC 테이블)과는 분리해 둔다.
EN_CCA_10S_VOLTAGE_MIN = 7.5    # V, 10초 시점 전압 하한
EN_CCA_6V_HOLD_SEC_MIN = 90.0   # sec, 6.0V까지 지속시간 하한
SAE_CCA_7V2_HOLD_SEC_MIN = 30.0  # sec, 7.2V까지 지속시간 하한

# 채점 모듈(.docs/24, 2026-09-24) — 튜터 조언(.docs/23) + 사용자 확정 기준(.docs/22 §0).
# "예측 SPEC 판정 == 실측 SPEC 판정" 일치율이 이 값 이상이면 "신뢰 가능"으로 표시한다.
SCORING_SUCCESS_RATE_THRESHOLD_PCT = 90.0
# 참고용(성공/실패 판정 축은 아님) — 예측값이 실측값 대비 이 오차율 이내인지 별도로 기록한다.
SCORING_ERROR_TOLERANCE_PCT = 10.0
