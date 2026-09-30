"""하드코딩 금지 설정값(docs/prd.md §10-16). 형명별 상세 분석에서 표본 부족 여부를 가릴 임계값.

표본 수가 이 값 미만인 형명은 SPEC 배지 대신 "표본 부족"으로 표시한다(형명당 표본 중앙값이
2~3건으로 매우 작기 때문 — `docs/prd.md` §10, `docs/correlation-reliability-review.md` 참조).
"""
from __future__ import annotations

MIN_SAMPLE_SIZE_FOR_MODEL_DETAIL = 5

# Y·Z SPEC 하한(§10 Open Question #11, 2026-09-27 사용자 확정) — 35개 형명 전체 공통 적용.
# `ConstantsByModel.spec_lower_y/z`에 형명별로 다른 값을 명시적으로 넣어두면 그 값이 우선하고
# (override), 값이 없는(NULL, 또는 해당 형명 행 자체가 없는) 형명은 전부 이 기본값을 쓴다.
DEFAULT_SPEC_LOWER_Y = 90.0  # %, 포화도(잔존율 proxy) 하한
DEFAULT_SPEC_LOWER_Z = 95.0  # %, 20시간 용량(capacity_rate) 하한

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

# 홀드아웃(train/val) 검증(.docs/35, 2026-09-30, v2 착수 — docs/prd.md §3에서 애초 "→v2, 10월"로
# 미룬 항목). 학습(train)에 쓰지 않은 val 표본으로만 채점해야 "이 모델이 새 로트에도 통할지"를
# 정직하게 보여준다 — 시험 매칭 표본이 이 값의 5배(val 최소 표본 ÷ 20%)에도 못 미치면 분할 자체가
# 무의미해(val이 몇 건 안 남아 일치율이 우연에 크게 좌우됨) 정직하게 in-sample로 폴백한다.
MIN_HOLDOUT_VAL_SIZE = 5
HOLDOUT_VAL_RATIO = 0.2
HOLDOUT_SPLIT_SEED = 42  # 재현성(docs/prd.md §9 "재현성: 규칙기반 100% 동일결과") 유지용 고정 시드
