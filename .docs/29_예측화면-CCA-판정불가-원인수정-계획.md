# 29. `/prediction` SAE·EN CCA "판정불가" 원인 수정 — 작업 계획서

## 배경/동기

- 사용자가 미매칭 로트 일괄 예측 결과에서 Z2(SAE CCA)·Z3(EN CCA)가 전부 "판정불가"로 뜨는 것을 발견하고 원인 확인을 요청.
- 조사 결과: `backend/routers/prediction.py`의 `_predict_cca_block`이 CCA 예측값(`sae_cca`/`en_cca`, 방전량 Ah)을 `judge_spec(predicted_value, None)`로 판정하고 있었음 — `spec_lower` 인자가 **하드코딩된 `None`**이라 `judge_spec`은 정의상 항상 `spec_result: None`("판정 불가")을 반환한다. `ConstantsByModel`에는애초에 `spec_lower_sae_cca`/`spec_lower_en_cca` 같은 컬럼 자체가 없어(Y/Z만 있음) 구조적으로 판정이 불가능했다 — 버그라기보다 "판정 대상 값 자체를 잘못 골랐다"는 설계 결함.
- 실제 EN 50342/SAE J537 합격/불합격은 방전량(Ah)이 아니라 전압·지속시간 체크포인트(`en_cca_10s_voltage`/`en_cca_6v_hold_sec`/`sae_cca_7v2_hold_sec`)로 판정한다(`analysis/cca_spec.py`의 `judge_en_cca`/`judge_sae_cca`, CLAUDE.md 함정 문단에 이미 문서화된 사실). 이 체크포인트를 예측하는 회귀(`fit_xy_to_en_cca_voltage10s`/`fit_xy_to_en_cca_hold6v`/`fit_xy_to_sae_cca_hold7v2`, `backend/analysis/regression.py`)는 이미 `history/24`(채점 모듈)에서 구현돼 있었지만, **`/prediction` 라우터는 이 함수들을 전혀 호출하지 않고** 방전량(Ah) 회귀만 쓰고 있었다.

## 범위

- `backend/routers/prediction.py`만 수정 — `analysis/regression.py`·`analysis/cca_spec.py`의 기존 순수 함수를 그대로 재사용(새 회귀 로직 없음).
- **스키마 변경 없음**: 체크포인트 회귀는 `AnalysisRun`에 영속화하지 않고(채점 모듈과 동일하게 매 요청 시 in-sample로 그때그때 학습), `AnalysisRun.stage` CHECK 제약(`x_to_y`/`xy_to_z`/`x_to_z_baseline`/`xy_to_sae_cca`/`xy_to_en_cca` 5종 고정)을 건드리지 않는다 — enum 추가는 테이블 재생성이 필요한 위험한 작업이라 이번 범위에서 제외(v2에서 필요성이 확인되면 별도 마이그레이션으로).
- `Prediction`/`SpecJudgment`/`CauseDiagnosis` 저장은 계속 **기존 방전량(Ah) 회귀의 `run_id`/`prediction_id`**에 연결한다(스키마의 `target CHECK IN ('y','z','sae_cca','en_cca')`도 그대로 유지) — 판정 소스만 체크포인트 회귀로 바꾸고 저장 스키마는 손대지 않는다.

## 방법

1. `repo.get_scoring_rows(conn)`(이미 존재, `history/24`)를 재사용해 체크포인트 회귀 3개(`fit_xy_to_en_cca_voltage10s`/`_hold6v`, `fit_xy_to_sae_cca_hold7v2`)를 요청마다 1회 학습(`InsufficientSampleError`면 `None` — 표본 부족 시 "판정 불가"가 여전히 정상 상태로 남음, 정직하게 유지).
2. 기존 `_predict_cca_block`을 `_predict_en_cca_block`/`_predict_sae_cca_block`으로 분리:
   - 방전량(Ah) 예측값은 기존과 동일하게 계산·저장(참고 정보로 유지, `predicted_value`).
   - **판정(`spec`)은 체크포인트 예측값을 `judge_en_cca`/`judge_sae_cca`에 넣어 계산** — `SpecJudgmentResult`와 동일한 필드명(`spec_result`/`spec_lower`/`deviation`/`note`)으로 감싸 프런트 타입 변경 없이 재사용(`spec_lower`/`deviation`은 단일 임계값이 아니라 항상 `None`).
   - 원인진단(`causes`)도 방전량 회귀가 아니라 체크포인트 회귀(EN은 전압+지속시간 2개 회귀의 `rank_causes` 결과를 합쳐 `|contribution|` 기준 재정렬 후 상위 3개)로 다시 계산 — 판정에 실제로 쓰인 값 기준으로 원인을 설명해야 의미가 있기 때문.
3. `predict_manual`/`predict_batch_unmatched` 양쪽에서 체크포인트 회귀를 요청당 1회만 학습해 재사용(배치는 로트마다 다시 학습하지 않음, 기존 `_load_cca_run_and_means`와 동일한 절약 패턴).
4. 프런트(`frontend/lib/api-client.ts`)의 `CcaPredictionBlock`에 `predicted_voltage_10s`/`predicted_hold_6v_sec`(EN)·`predicted_hold_7v2_sec`(SAE) 선택 필드만 추가(타입 확장, breaking change 아님) — `frontend/app/prediction/page.tsx`의 verdict-card에 체크포인트 예측값을 보조 텍스트로 표시.

## 완료 기준

- 실행 중인 데모 DB로 `POST /api/predict/batch-unmatched` 호출 시 Z2/Z3 `spec.spec_result`가 `null`이 아니라 실제 `"pass"`/`"fail"`로 나오는지 확인(현재 10k 데이터 규모면 체크포인트 회귀 표본이 충분해 성공할 것으로 예상 — 실패하면 `InsufficientSampleError` 메시지로 정직하게 표시되는지 확인).
- `pytest tests/backend`·`ruff check backend`·`npm run build`/`npm run lint` 통과.
