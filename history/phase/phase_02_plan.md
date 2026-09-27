# Day 2 — 2단 캐스케이드 회귀 + 상세 분석 + 추이 그래프

> `prd.md` §6 ③-1~③-4를 구현하는 날. Day 1의 `LotDerived` + 프런트/백엔드 연동이 전제 조건. **2026-09-10 스택 피벗 반영**: 화면은 `frontend/app/*`(Next.js), 계산은 `backend/analysis/*`(FastAPI 뒤 Python) — 분석 로직 자체는 스택 피벗과 무관하게 그대로다.

## 목표

- X→Y(1단), X+Y→Z(2단), X→Z(베이스라인) 세 회귀가 모두 API로 실행되고 `AnalysisRun`에 이력으로 저장된다.
- 형명별 상세 분석과 Y 추이 그래프가 `design.md` 토큰을 적용한 Next.js 화면에서 실제 DB 값으로 렌더링된다.

## 작업 순서

1. **`backend/analysis/significance.py`**: 피어슨 r + p-value(`scipy.stats.pearsonr`) 계산 함수. `correlation-reliability-review.md`와 동일한 유의수준(0.05) 고정.
2. **`backend/analysis/vif.py`**: 1단 X셋(`electrolyte_temp`, `tank_temp`, `soaking_time_sec`, `aging_days`, `formation_dv`, `cell_weight_mean`, `cell_weight_std`, `charge_ratio`)에 대해 VIF 산출.
3. **`backend/analysis/regression.py`**:
   - `fit_x_to_y`: 1단 X셋 → `retention_rate` 다중선형회귀. `fill_weight`/`water_loss`/`mt_voltage`/`mt_current`는 입력에서 원천 제외(§6-③, 코드 레벨에서 컬럼 화이트리스트로 강제).
   - `fit_xy_to_z`: 1단 X셋 + **실측** `retention_rate` → `discharge_amount` 회귀. 시험 매칭 59개 로트만 학습 데이터로 사용.
   - `fit_x_to_z_baseline`: 1단 X셋만 → `discharge_amount` 회귀(Y 없이). 캐스케이드와 베이스라인 비교 구조는 마련하되 정량 비교는 v2(§3 Non-goals).
   - 세 함수 모두 결과를 `AnalysisRun`에 저장하고, 저장 시 같은 `stage`의 기존 `is_latest_for_stage=1`을 0으로 내린 뒤 새 행을 1로 삽입.
4. **API**: `POST /api/analysis/x-to-y`, `POST /api/analysis/xy-to-z`, `POST /api/analysis/x-to-z-baseline`, `GET /api/kpi`(대시보드 KPI 카드용 집계).
5. **`frontend/app/dashboard/page.tsx` (③-1, ③-2)**: `output/analysis_dashboard.html`을 React로 이식 — 상관계수·회귀계수·VIF 바 차트, KPI 카드(평균 Y, 이번 달 Y/Z 부적합 건수, 매칭률), 1단/2단 갱신 시점을 분리 표시. `design.md` 토큰(색상·spacing·radius)을 목업과 동일하게 적용(이번 피벗으로 "위젯 제약상 다를 수 있다"는 단서가 없어졌으므로 픽셀 단위로 맞춘다).
6. **`backend/analysis/trend.py` + `frontend/app/detail-analysis/page.tsx` (③-3, ③-4)**:
   - `GET /api/models/summary`: 형명별 group-by 조회(용량군 요약 카드 + 35개 형명 테이블), **표본 수(n)를 항상 함께 반환**하고 임계값 미만이면 프런트에서 SPEC 배지 대신 "표본 부족" 표시(`correlation-reliability-review.md` §4, `prd.md` §10-16 — 임계값은 `backend/config/spec_thresholds.py`에 설정 가능한 값으로 둠).
   - `GET /api/models/{model_name}/trend?period=day|month|year`: `prod_date` 기준 일/월/연 집계 후 그래프. `output/03_detail_analysis.html`의 inline SVG 패턴을 React 컴포넌트(예: 간단한 SVG 렌더링, 외부 차트 라이브러리 없이)로 이식. 연간 탭은 누적 연도 1개뿐이면 안내 문구로 대체(§8).

## Day 2 완료 기준

- [ ] `AnalysisRun`에 `x_to_y`/`xy_to_z`/`x_to_z_baseline` 세 stage 모두 최소 1건씩 기록됨
- [ ] 대시보드에 회귀계수와 함께 VIF, (있다면) p-value가 노출되어 "유의하지 않은 인자"를 확정된 인사이트처럼 보여주지 않음(`correlation-reliability-review.md` 원칙)
- [ ] 형명별 상세 테이블에 표본 수(n)가 모든 행에 표시됨
- [ ] Y 추이 그래프가 실제 `LotDerived`/`Lot.prod_date` 값으로 그려짐(하드코딩된 더미 좌표 없음)
- [ ] `/dashboard`, `/detail-analysis` 화면이 `output/*.html` 목업과 색상·간격·타이포 토큰 기준으로 육안상 일치함

## 다음날 연계

Day 3의 예측(④)은 `AnalysisRun`의 `x_to_y`/`xy_to_z` 최신 run을 API로 그대로 재사용한다. Day 2에서 만든 회귀 결과가 없으면 Day 3 예측 화면은 동작할 수 없다.
