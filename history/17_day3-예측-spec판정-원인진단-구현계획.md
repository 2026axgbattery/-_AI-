# 17. Day 3 — 예측·SPEC 판정·원인진단 구현 계획

> **완료(2026-09-11)**: 아래 계획대로 6단계를 모두 구현했다. `pytest tests/backend`(47건)·`ruff check backend`·`next build`·`eslint` 전부 통과, 실제 실행 중인 앱(실 데이터 2600+ 로트)에서 4개 화면 모두 Playwright로 콘솔 에러 없음 확인. 계획 대비 API 설계를 일부 변경했다(`POST /api/predict/y`/`z`/`POST /api/diagnosis` 3개 분리 대신 `POST /api/predict/manual`/`POST /api/predict/batch-unmatched` 2개로 통합 — 화면이 실제로 필요로 하는 두 시나리오에 맞춤). 상세 내용은 `.docs/06_mvp-todo-list.md` Day 3 섹션·`.docs/07_디자인-수정-이력.md` 참조.

## 배경/동기

`.docs/phase/phase_03_plan.md`(Day 3 실행계획)·`prd.md` §6 ④-1/④-2/⑤·§7 데이터 모델(`Prediction`/`SpecJudgment`/`CauseDiagnosis`, 이미 `backend/db/schema.sql`에 DDL 존재)·`.docs/02_nextjs-fastapi-구현-아키텍처.md`(화면-API 매핑표)을 근거로 Day 3를 시작한다. Day 1·2는 완료됐고(`CLAUDE.md`), 이번이 마지막 Day다.

미리 확인한 사실:
- 스키마(`Prediction`/`SpecJudgment`/`CauseDiagnosis`/`ConstantsByModel.spec_lower_y/z`)는 이미 Day 1 때 만들어져 있어 마이그레이션이 필요 없다.
- `backend/analysis/regression.py`에 `predict(coefficients, intercept, x)` 함수가 이미 Day 2 때 준비돼 있다(재사용).
- SPEC 임계값 업로드 기반구조(`.docs/12`, `POST /api/spec-thresholds/upload`)는 이미 있지만, **이 앱 인스턴스에는 아직 실제 SPEC 값이 채워진 적이 없다**(담당자 미확정, `prd.md` §10-11) — 즉 Day 3 작업 내내 "SPEC 미설정" 상태를 정상 경로로 취급해야 한다(§8 엣지케이스: "판정 불가 안내").
- `output/04_prediction.html`(예측 화면 목업)과 `output/analysis_dashboard.html`의 `evi-cause`/`evi-batch` 섹션(Day 2에서 실제 연동을 보류해 둔 부분, `CLAUDE.md` "Layer 3(원인진단)·미매칭 로트 일괄 예측 표는 여전히 Day 3 디자인 마무리 항목")이 이번 작업의 디자인 목표치다.

## 범위

**포함**
1. `backend/analysis/diagnosis.py` — `judge_spec`, `rank_causes` (순수 함수, 웹 프레임워크 비의존).
2. `backend/db/repository.py` 확장 — 미매칭 로트 X 조회, `Prediction`/`SpecJudgment`/`CauseDiagnosis` 저장·조회.
3. `backend/routers/prediction.py`(신규) — `POST /api/predict/manual`(조건 시뮬레이션 1건), `POST /api/predict/batch-unmatched`(미매칭 로트 일괄).
4. `frontend/app/prediction/page.tsx`(신규) — `output/04_prediction.html` 이식, 두 탭.
5. `/dashboard`에 Layer 3(`evi-cause`: SPEC 판정 & 원인진단)·`evi-batch`(미매칭 로트 일괄 결과 미리보기) 추가, KPI 카드의 "SPEC 판정: Day 3 연동 예정" 문구를 실제 판정으로 교체(단, SPEC 미설정 시 "SPEC 미설정, 판정 불가"로 정직하게 표시).
6. 종단간 점검 + 개발 후 점검(`pytest`/`ruff`/`next build`/`eslint`) + 디자인 확인 + 문서 갱신.

**비범위(v2 이관, 이미 확정된 원칙 유지)**
- `saturation_calc`(실포화도) 활성화, R²/RMSE 정식 검증, 캐스케이드 vs 베이스라인 정량 비교, 재학습 파이프라인.
- 동률 처리 규칙 확정(§10-12 미확정) — 임시로 "계수 절댓값 큰 순 + 동률 시 인자명 알파벳 순"을 적용하고 TODO로 남긴다(phase_03_plan 명시 사항).

## 방법 — 원인진단(rank_causes) 설계 결정 (PRD에 수식이 명시돼 있지 않아 직접 정함)

`prd.md` §6-⑤는 "회귀계수 × SPEC 이탈 정도"로 원인 인자를 순위화하라고만 되어 있고 구체적 수식은 없다. "이탈 정도"를 (predicted − spec) 스칼라로 전 인자에 동일하게 곱하면 순위가 전혀 안 바뀌므로(상수배), 실제로 의미 있으려면 **인자별** 이탈 정도가 필요하다. 그래서 다음 방식을 채택한다:

```
contribution_i = coefficient_i × (x_i − mean_i)
```

`mean_i`는 그 회귀를 학습한 표본(훈련 데이터)에서의 해당 인자 평균이다. 이는 선형회귀 예측값을 "평균 대비 각 인자의 기여분"으로 분해하는 표준적인 방법이고(절편 + Σcontribution_i ≈ predicted_value), "이 로트가 평균적인 로트보다 왜 낮게/높게 나왔는지"를 인자별로 정직하게 설명한다. `output/analysis_dashboard.html`의 목업처럼 "관리기준 30~35℃" 같은 구체적 관리기준 수치는 **실제로 확보한 값이 아니므로 지어내지 않고**, 대신 우리가 실제로 가진 훈련 데이터 평균과 비교하는 문구("실측 38.4℃로 평균 31.2℃보다 높음")를 쓴다.

권고 문구는 인자별 고정 템플릿(방향에 따라 문구 분기, `prd.md` §6-③ 하단 표의 잔차 해석 방향과 §6-⑤ "주액량 증대로만 귀결되지 않도록" 원칙 반영)을 쓰고, 실제 수치(로트 값 vs 훈련 평균)만 채워 넣는다.

## 작업 순서 (단계마다 보고)

1. **`backend/analysis/diagnosis.py` + `tests/backend/test_diagnosis.py`**: `judge_spec(value, spec_lower)`, `rank_causes(x_columns, coefficients, x_values, factor_means, top_n=3)`, 권고 문구 템플릿. 순수 함수라 이 단계에서 바로 유닛테스트 가능.
2. **`backend/db/repository.py` 확장**: `get_unmatched_lots_x`(미매칭 로트 X 조회, `get_x_to_y_training_rows`와 동일한 완결성 조건 재사용), `save_prediction`/`save_spec_judgment`/`save_cause_diagnosis`, `get_spec_threshold_for_model`.
3. **`backend/routers/prediction.py`**: `POST /api/predict/manual`, `POST /api/predict/batch-unmatched`. `backend/main.py`에 등록.
4. **`frontend/app/prediction/page.tsx`**: 목업 이식(두 탭), `TopBar`의 "예측" 탭을 실제 링크로 전환.
5. **`/dashboard` Layer 3 연동**: KPI 카드 실제 판정 교체, `evi-cause`/`evi-batch` 섹션 추가.
6. **종단간 점검 + 개발 후 점검 + 문서 갱신**(`.docs/06`, `.docs/07`, `CLAUDE.md`, `phase_03_plan.md` 체크).

## 완료 기준

`phase_03_plan.md`의 "Day 3 완료 기준" 체크리스트를 그대로 따른다(①~⑤ 종단간 실행, 미매칭 41건 Y·Z 산출률 100%, 캐스케이드+베이스라인 둘 다 구현됨, `water_loss_residual` 이상 로트 1건 이상 검출, 원인진단 재현성, `AnalysisRun` 이력 누락 없음, 프런트/백엔드 점검 결과 보고, 5화면 디자인 토큰 일치).
