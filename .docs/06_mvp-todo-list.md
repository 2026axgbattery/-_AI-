# MVP Todo List

**기준 문서**: `history/05_mvp-구현-실행계획.md`(배경/범위/방법/완료기준), `history/phase/phase_01~03_plan.md`(Day별 상세), `docs/prd.md`(요구사항 원본)
**작성일**: 2026-09-10 (마지막 전체 재점검: 2026-09-25 — v1.1·v2·"결과 우선" 재설계 이후 남아있던 미완료 항목을 전수 재확인·갱신함)
**사용법**: 항목을 완료할 때마다 체크한다. 각 항목은 어떤 문서의 어떤 절에 근거하는지 괄호로 표시했으므로, 세부 구현 방법이 궁금하면 해당 절을 먼저 읽는다. 순서를 건너뛰지 않는다 — Day 2는 Day 1의 산출물(`LotDerived`, 프런트↔백엔드 연동)을, Day 3은 Day 2의 `AnalysisRun`을 전제로 한다.

---

## Day 1 — 셋업 + 업로드·매칭·수기입력·파생값 (`phase_01_plan.md`)

### 0. 프로젝트 초기 셋업
- [x] `frontend/`: `create-next-app`(TypeScript, App Router) 스캐폴딩
- [x] `docs/design.md` §6 CSS Custom Properties → `frontend/lib/theme.css`로 이식
- [x] `next/font`로 Pretendard(국문)/Inter(영문) 로드 — Pretendard는 외부 CDN이 아니라 `app/fonts/PretendardVariable.woff2`로 로컬 자가호스팅(로컬 전용 원칙 준수)
- [x] `backend/`: FastAPI 스켈레톤(`main.py`), CORS는 `http://localhost:3000`만 허용
- [x] `uvicorn`으로 `127.0.0.1:8000` 기동 확인
- [x] `frontend/lib/api-client.ts`에 FastAPI base URL(`127.0.0.1:8000`) 고정
- [x] `GET /api/health` 헬스체크 엔드포인트 구현 + 정상 호출 확인(curl로 확인; 화면에는 별도 헬스 배지 없음)

### 1. DB 초기화
- [x] `.docs/03_sqlite-스키마-설계.md` DDL을 `backend/db/schema.sql`로 이전(원본 그대로, `IF NOT EXISTS`만 추가)
- [x] FastAPI 기동 시 DB 파일 없으면 자동 생성하는 초기화 루틴(`backend/db/repository.py`)
- [x] 스키마 실행 시 9개 테이블 오류 없이 생성되는지 확인(`sqlite_sequence` 제외 9개 확인됨)

### 2. 파생값 계산 로직
- [x] `backend/analysis/derive.py`: `LotDerived` 전 컬럼(잔존율, `water_loss_rate`, `water_loss_per_ah`, `theoretical_water_loss`, `water_loss_residual`, `fill_per_rated`, `charge_ratio`, `cell_weight_mean/std`, `formation_dv`) 순수 함수로 구현 + `tests/backend/test_derive.py` 단위 테스트
- [x] `saturation_calc`은 항상 NULL, `saturation_basis='proxy_retention'`, `saturation_source='derived'` 고정 (`docs/prd.md` §1-1, §7)

### 3. 업로드 & 매칭 (①, `docs/prd.md` §6-①)
- [x] `POST /api/upload/process` + `POST /api/upload/test`(단일 엔드포인트 대신 파일별 분리 — 각 드롭존이 독립적으로 즉시 업로드되는 목업 UX에 맞춘 구현 선택), 필수 컬럼 검증(누락 시 400 + 누락 컬럼 목록)
- [x] 업로드 UI는 파일 선택(클릭)과 **드래그앤드롭** 둘 다 지원(2026-09-10 추가)
- [x] `lot_id` 조인 → 매칭/미매칭 건수 반환(미매칭은 정상 케이스로 처리, 에러 아님) — 업로드가 끝나면 **자동** 실행, 별도 "매칭 실행" 버튼 없음
- [x] 동일 `lot_id` 재업로드 시 경고 처리(append-only 원칙, §8) — API 응답(`duplicate_lot_ids`)에는 반영됨. **2026-09-25 해결**: `frontend/app/upload/page.tsx`의 공정 데이터 카드에 `skipped_unknown_lot`과 동일한 패턴으로 경고 배너 추가(건수·예시 lot_id 노출), `npm run build`/`lint` 통과
- [x] **버그 수정(2026-09-17)**: 시험 데이터를 매칭되는 공정 데이터보다 먼저 업로드하면 `ingest_test_rows`가 전 행을 `skipped_unknown_lot`으로 조용히 건너뛰어 매칭 0건이 되는데, 이 경고가 화면에 전혀 표시되지 않아 사용자가 원인을 알 수 없던 문제 발견. `frontend/app/upload/page.tsx`의 시험 데이터 카드에 `skipped_unknown_lot` 건수·예시 lot_id·해결법(공정 데이터 먼저 업로드 후 재업로드)을 안내하는 경고 배너 추가, Playwright로 실제 노출 확인(콘솔 에러 없음)
- [x] `frontend/app/upload/page.tsx`: `output/01_upload_matching.html` 마크업 이식 — ①(업로드·매칭)과 ②(수기입력)를 **한 페이지**로 구현(2026-09-10 통합, 구 `manual-entry/page.tsx` 없음). 목업의 컬럼 배지 목록(`.col-list`, X-factor/제외 태그)은 이식하지 않음 — **2026-09-24~25 "결과 우선" 재설계로 정보구조 자체가 바뀌면서 이 아이디어는 대체(moot)됨**: 지금은 `.status-chip`(완료/참고/확인 필요)으로 카드 라벨을 요약하는 방식을 씀(`history/25` 참조)
- [x] **실제 현장 raw data(.xls/.xlsx) 직접 업로드 지원(2026-09-11)** — `backend/etl/process_raw.py`, `backend/etl/test_raw.py`(웹 프레임워크 비의존 순수 파서), 업로드 API가 파일 확장자로 CSV/raw 경로를 자동 분기(`.docs/14_raw-data-업로드-지원-계획.md`). 실제 파일 2건(공정 32,088행, 시험 12행)을 브라우저로 업로드해 에러 없이 적재됨을 확인(Playwright 스크린샷 검증, 콘솔 에러 없음)

### 4. 수기입력 (②, `docs/prd.md` §6-②) — 3번과 같은 화면(`frontend/app/upload/page.tsx`)의 매칭 결과 아래에 이어짐
- [x] `GET/PUT /api/lots/{lot_id}/manual-fields`(개별 편집 API — 백엔드에는 구현하되 화면에는 연결하지 않음, `docs/prd.md` §10-20)
- [x] `GET /api/manual-fields/groups`(그룹 목록·미입력 건수 조회), `PUT /api/manual-fields/batch`(그룹 일괄 반영)
- [x] CSV에 이미 있는 `electrolyte_temp`/`charge_amount`/`tank_temp` 자동 표시
- [x] **화면에는 로트별 개별 입력 UI를 두지 않음(2026-09-10 개정)** — 미입력 값은 그룹 일괄 입력으로만 채운다
- [x] **MT(V)/MT(A)는 수기입력 UI 자체를 두지 않고, 이 화면에는 참고 배지로도 노출하지 않음(2026-09-10 개정)** — `TestData` 매칭 값은 "시험 로트 한정 심층 분석" 화면에서만 다룸(§6-②, §10-5)
- [x] 그룹 일괄 입력: `charge_amount`는 `model_name` 단위, `electrolyte_temp`/`tank_temp`는 `model_name`+`prod_date` 단위로 그룹화, 미입력 로트에만 일괄 반영(기존값 덮어쓰기 방지 + 버튼은 미입력 0건이면 비활성화). 실제 더미 CSV에는 세 항목 모두 결측이 없어(사전 확인됨) 정상 동작은 인위적으로 값 하나를 비운 뒤 배치 반영으로 검증함
- [x] 미입력 항목 남은 로트는 1단 분석 대상에서 제외 + 목록 안내(`GET /api/manual-fields/status`, 화면 alert)
- [x] 저장 시 `derive.py` 호출 → `LotDerived` upsert
- [x] 업로드→매칭→수기입력까지 한 화면에서 끝내되, **1단·2단 분석 실행은 화면 하단의 명시적 버튼을 눌러야 시작**(현재는 Day 2 분석 API가 없어 버튼은 비활성 상태로 존재)

### 5. 검증
- [x] `process_data.csv`(100행) 전량 업로드 → 매칭 59 / 미매칭 41 확인(curl로 API 레벨 검증 완료)
- [x] `LotDerived` 100행 생성 확인, 잔존율 89.5~94.5%(평균 92.0%)로 `docs/prd.md` 서술과 대략 일치 확인
- [ ] **사용자 직접 검증 대기**: 브라우저(`http://localhost:3000/upload`)에서 실제 CSV 업로드 UI로 직접 재확인(DB는 사용자가 새로 테스트할 수 있도록 비워둔 상태)

### Day 1 완료 기준 (`phase_01_plan.md`)
- [x] `next dev` + `uvicorn` 동시 구동, 헬스체크 정상
- [x] `backend/db/schema.sql` 오류 없이 9개 테이블 생성
- [x] 업로드 화면에서 매칭 59/미매칭 41 정상 표시(API 레벨 검증, 브라우저 확인은 사용자 몫으로 남김)
- [x] `LotDerived` 100개 로트 전부 저장(재계산 없이 다음 날 조회 가능)
- [x] 어느 화면에서도 `fill_weight`/`water_loss`가 "1단 X 후보"로 노출되지 않음

---

## Day 2 — 2단 캐스케이드 회귀 + 상세 분석 + 추이 (`phase_02_plan.md`)

> 구현 계획: `history/15_day2-회귀-대시보드-구현-계획.md`

### 6. 통계 유틸리티
- [x] `backend/analysis/significance.py`: 피어슨 r + p-value(`scipy.stats.pearsonr`), 유의수준 0.05 고정 (`docs/correlation-reliability-review.md`와 동일 기준)
- [x] `backend/analysis/vif.py`: 1단 X셋(`electrolyte_temp`, `tank_temp`, `soaking_time_sec`, `aging_days`, `formation_dv`, `cell_weight_mean`, `cell_weight_std`, `charge_ratio`) VIF 산출 — `statsmodels` 없이 numpy 최소자승법으로 직접 구현(불필요한 의존성 추가 금지)

### 7. 회귀 로직 (③-1·③-2, `docs/prd.md` §6-③)
- [x] `fit_x_to_y`: 1단 X셋 → `retention_rate` 다중선형회귀. `fill_weight`/`water_loss`/`mt_voltage`/`mt_current`는 화이트리스트로 원천 제외
- [x] `fit_xy_to_z`: 1단 X셋 + **실측** `retention_rate` → `discharge_amount`. 시험 매칭 59개 로트만 학습
- [x] `fit_x_to_z_baseline`: 1단 X셋만 → `discharge_amount` (Y 없이)
- [x] 세 함수 모두 `AnalysisRun`에 저장 + 같은 stage의 기존 `is_latest_for_stage=1`을 0으로 내리고 새 행 1로 삽입(`repository.save_analysis_run`)
- [x] API: `POST /api/analysis/x-to-y`, `POST /api/analysis/xy-to-z`, `POST /api/analysis/x-to-z-baseline`, `GET /api/kpi`, `GET /api/analysis/latest?stage=`(추가: 새로고침 시 마지막 결과 복원용)
- [x] 표본 부족(변수 수+2 미만)은 `InsufficientSampleError` → 400 응답으로 정상 처리(에러 아님)

### 8. 대시보드 화면 (③-1·③-2)
- [x] `frontend/app/dashboard/page.tsx`: `output/analysis_dashboard.html`을 참고해 구현 — KPI 카드, 상관계수/회귀계수 바 차트, VIF, 캐스케이드 vs 베이스라인 계수·R² 비교표
- [x] 상관계수·회귀계수·VIF 표시(p<0.05 미달 인자는 `†` 표시로 구분, `docs/correlation-reliability-review.md` 원칙 반영)
- [x] KPI 카드(평균 Y, 매칭률, 전체/매칭 로트 수) — "이번 달 Y/Z 부적합 건수"는 Day 3에서 `GET /api/spec-compliance` 실연동 완료, **2026-09-24~25에는 이 수치가 대시보드 최상단 `.hero-verdict`(초대형 결론 배너)의 문장으로 격상**돼 KPI 카드보다 먼저 보임(`history/25`)
- [x] 1단·2단 실행 시각을 `AnalysisRun.run_at`으로 화면에 표시(stage별 완전 분리 표시는 구현했으나 "갱신 주기가 다르다"는 안내 문구는 아직 미이식)
- [x] `docs/design.md` 토큰(색상·spacing·radius)은 기존 `components.css`의 토큰을 그대로 재사용 — 목업의 verdict-banner·접이식 근거 섹션은 Day 3 당시엔 보류했으나, **2026-09-24~25 "결과 우선" 재설계로 완전히 이식·확장 완료**: `.hero-verdict`(종합판정 배너)+`.insight-row`(한눈에 보기 카드 4개)+`.evidence-toggle`(기존 5개 근거 섹션을 감싸는 접이식 토글)로 구현(`history/25` 참조)

### 9. 형명별 상세 분석 + 추이 (③-3·③-4)
- [x] `backend/analysis/trend.py`
- [x] `GET /api/models/summary`: 형명별 group-by(35개 형명 테이블 + 프런트에서 용량군별로 재집계한 요약 카드), 표본 수(n) 항상 함께 반환
- [x] 표본 수 임계값 미만 시 "표본 부족" 배지 표시, 임계값은 `backend/config/spec_thresholds.py`의 `MIN_SAMPLE_SIZE_FOR_MODEL_DETAIL`(=5)에 설정(하드코딩 금지, `docs/prd.md` §10-16)
- [x] `GET /api/models/{model_name}/trend?period=day|month|year`: `prod_date` 기준 일/월/연 집계, `model_name=all`이면 전체 평균
- [x] 연간 탭은 누적 연도 1개뿐이면 안내 문구로 대체(§8 엣지케이스) — `available_years` 응답 필드로 판단
- [x] `frontend/app/detail-analysis/page.tsx`: 용량군 요약 카드 + 형명별 상세 테이블(표본 부족/미시험 배지) + 형명 선택·일/월/연 토글 + Y 추이(inline SVG 직접 렌더링, 외부 차트 라이브러리 없이)

### Day 2 완료 기준 (`phase_02_plan.md`)
- [x] `AnalysisRun`에 `x_to_y`/`xy_to_z`/`x_to_z_baseline` 세 stage 모두 최소 1건 기록(더미 CSV로 실제 실행·확인함)
- [x] 대시보드에 VIF·p-value가 함께 노출되어 유의하지 않은 인자를 확정 인사이트처럼 보여주지 않음(더미 데이터로 전해액온도 p=0.308 등 `docs/correlation-reliability-review.md`와 일치하는 결과 확인)
- [x] 형명별 상세 테이블 모든 행에 표본 수(n) 표시
- [x] Y 추이 그래프가 실제 DB 값으로 렌더링(하드코딩 좌표 없음) — Playwright로 실제 렌더링 확인
- [x] `/dashboard`, `/detail-analysis`가 목업과 색상·간격·타이포 기준 일치 — Day 2 당시엔 레이아웃 세부(verdict-banner·접이식 섹션)까지 픽셀 단위로 맞추지 않았으나, **2026-09-24~25 "결과 우선" 재설계 때 방향이 반대로 뒤집힘**: 실 구현을 먼저 확정하고 레퍼런스 목업 4개(`output/*.html`)를 실 구현에 맞춰 갱신하는 방식으로 드리프트를 없앰(`history/25`, `.docs/07`). 정식 스크린샷 diff는 여전히 미수행(아래 134번과 동일 사유)

---

## Day 3 — 예측·SPEC 판정·원인진단 + 종단간 점검 (`phase_03_plan.md`)

### 10. 예측 로직 (④-1·④-2, `docs/prd.md` §6-④)
- [x] `predict_y`/`predict_z` 로직은 Day 2에 준비된 `regression.predict()`를 그대로 재사용(신규 함수 불필요)
- [x] Ŷ + X를 2단 최신 run에 적용, `input_y_source='predicted'` 플래그(`backend/routers/prediction.py`)
- [x] **API 설계 변경(§10 문서 vs 실제 구현)**: 원래 계획한 `POST /api/predict/y`/`POST /api/predict/z` 2개 분리 대신, 화면에서 실제로 필요한 두 시나리오에 맞춰 `POST /api/predict/manual`(조건 시뮬레이션 1건 — Y 예측→Z 예측→SPEC 판정→원인진단을 한 번에 수행)과 `POST /api/predict/batch-unmatched`(미매칭 로트 전체 일괄)로 합쳐서 구현. 프런트가 여러 번 왕복할 필요가 없어짐(`history/17` 참조). 수동 시뮬레이션은 `input_y_source=None`(1단 예측 자체), 2단 예측은 항상 `predicted`(실측 Y 시뮬레이션 입력 경로는 이번 범위에 없음 — 실측 Y 기반 확인은 `/dashboard`에서 이미 가능).
- [x] `frontend/app/prediction/page.tsx`: `output/04_prediction.html` 이식, "조건 시뮬레이션(선택적)" / "미매칭 로트 일괄 예측" 두 탭 구현
- [x] 배치 결과 테이블에 "Ŷ 기반" 배지, 이상치(Y가 0~100% 범위 밖이거나 Z가 음수) 플래그 표시(§8)

### 11. SPEC 판정 & 원인진단 (⑤, `docs/prd.md` §6-⑤)
- [x] `backend/analysis/diagnosis.py`
- [x] `judge_spec`: 모델별 `spec_lower_y`/`spec_lower_z` 비교, 미설정 시 "SPEC 미설정, 판정 불가" 안내
- [x] `rank_causes`: `계수 × (로트 값 − 훈련 데이터 평균)`으로 원인 인자 순위화(PRD에 구체식이 없어 이렇게 확정, `history/17` 참조), Y/Z 원인 인자셋 분리
- [x] 동률 처리 임시 규칙(계수 절댓값 큰 순 + 알파벳 순) 적용 + TODO 주석으로 표시(§10-12 확정 전)
- [x] 원인진단 문구를 여러 갈래로 분기(인자별 고정 템플릿, 방향별 문구) — "주액량 증대"로만 귀결 금지, 구체적 관리기준 수치는 확보한 적이 없어 지어내지 않고 훈련 데이터 평균과의 비교로 대체
- [x] **API 설계 변경**: 별도 `POST /api/diagnosis` 대신 `predict/manual`·`predict/batch-unmatched` 내부에서 판정·진단까지 이어서 수행(위 10번 항목과 동일한 이유)
- [x] 예측 API 호출 시 `SpecJudgment`(SPEC 설정된 경우만)/`CauseDiagnosis`(SPEC 미달로 판정된 경우만) 자동 저장 연동
- [x] `/dashboard`에 SPEC 판정 KPI(실측/직접계산 Y·Z 기준, `GET /api/spec-compliance`) + Layer 3 안내 섹션(예측 화면으로 유도) 추가

### 12. 종단간 점검
- [x] 실행 중인 실제 앱(업로드→매칭→수기입력→1·2단 분석까지 이미 사용자가 진행한 상태)에서 `/upload`·`/dashboard`·`/detail-analysis`·`/prediction` 4개 화면 모두 Playwright로 재방문해 콘솔 에러 없음을 확인(2026-09-11). DB를 비운 완전한 처음부터의 재현은 사용자가 실제 데이터로 계속 작업 중이라 이번엔 생략 — 필요 시 별도로 수행 가능.
- [x] `docs/prd.md` §8 엣지케이스 각 항목 재확인 — **2026-09-25 재확인**(§8은 2026-09-24 축약 이후 표가 아니라 한 문단으로 압축돼 있음, 18개 항목 기준): 16개는 코드로 구현·확인됨(미매칭 정상 처리, 매칭 0건 경고, 수기입력 누락 제외, 표본부족 배지, 이상치 플래그, 원인 우선순위, 무차원 인자, X 화이트리스트, VIF 경고, Ŷ 기반 플래그, stage별 갱신시점 분리, 동일 lot_id 재업로드 경고(위 33번), 연간추이 대체 안내, SPEC 미설정 안내, SQLite 단일쓰기·로컬전용 아키텍처로 자연히 충족). **미구현 확인된 2개(백로그로 남김)**: water_loss 이론치 불일치 "보류 플래그"와 동일 bath·circuit 조/회로별 잔차 별도표시는 `backend/analysis/derive.py`가 `water_loss_residual`/`bath_no`/`circuit_no`를 계산·저장만 하고, 이를 화면에 노출하는 UI가 아직 없음(2026-09-11에 스크립트로 1회성 수동 확인만 함, `history/phase/phase_03_plan.md`) — v2에서 필요 시 착수.

### 13. 개발 후 점검 (전역 CLAUDE.md 규칙)
- [x] 백엔드: `pytest tests/backend` 47건 통과(신규: `test_diagnosis.py`, `test_prediction_repo.py`, `test_spec_compliance.py`)
- [x] 백엔드: `ruff check backend` 통과
- [x] 프런트: `next build`(TypeScript 타입체크 포함) 통과
- [x] 프런트: `eslint` 통과

### 14. 디자인 마무리
- [x] 신규 CSS는 전부 기존 `--sebang-*`/`--space-*`/`--radius-*` 토큰만 사용(새 색상 추가 없음), 오렌지·그린 동시 강조 없음(확인)
- [ ] `output/*.html`과 화면별 정식 스크린샷 diff는 수행하지 않음 — **2026-09-25 기준에도 동일**: 이 환경에 Playwright/chromium-cli 등 브라우저 자동화 도구가 없어(`history/20`부터 반복 확인된 제약) 정식 픽셀 diff는 애초에 불가능. 대신 `npm run build`/`lint` + 실행 중인 dev 서버 curl로 SSR HTML에 기대 클래스명이 포함되는지 확인하는 방식을 검증 대체 수단으로 계속 사용 중(`history/25`, 이번 세션의 `.hero-num-chip` 반영 확인도 동일 방식). 도구가 생기기 전까지는 사실상 상시 보류 상태로 간주.

### Day 3(=3일 집체 종료) 완료 기준 — `docs/prd.md` §9 성공 지표
- [x] ①~④ 전체가 실제(대량, 2600+ 로트) 데이터로 콘솔 에러 없이 실행됨을 확인. ⑤(SPEC 판정)는 Day 3 당시엔 SPEC 임계값 미업로드로 "판정 불가" 경로만 확인됐으나, **2026-09-24 이후 `AGM60_S1`/`AGM70_S1` 2개 형명에 실제 SPEC 하한(Y 90 / Z 95)을 반영**해 실제 판정 동작까지 확인됨(`GET /api/spec-compliance` → `models_with_spec: 2, y_fail: 43, z_fail: 0`)
- [x] 미매칭 로트 Y·Z 산출률 100% — **2026-09-25 실측 확인**: 현재 데모 DB는 전체 2,200개 로트 중 수기입력 미완료 0건(`GET /api/manual-fields/status` → `incomplete_lot_ids: []`), 미매칭 2,148건 전부에 대해 `POST /api/predict/batch-unmatched` 응답의 `total`이 2,148로 일치해 100% 산출 확인됨(Day 3 당시엔 수기입력 3항목이 비어 있어 0건이었던 상태에서 이후 더미 데이터 재구성으로 해소됨).
- [x] X→Y→Z 캐스케이드와 X→Z 베이스라인 둘 다 구현(정량 비교는 v2) — 실제 데이터로 R² 0.991/0.990 확인
- [x] `water_loss_residual` 기준 이상 로트 검출 확인(실제 데이터 2668건 중 최대 잔차 496g, 2026-09-11 재확인)
- [x] 동일 입력에 원인진단 결과 항상 동일(순수 함수·규칙 기반, 랜덤성 없음 — 코드 구조로 보장)
- [x] `AnalysisRun` 이력이 stage 구분과 함께 누락 없이 기록(기존 Day 2 구현 그대로 유지, 변경 없음)
- [x] 프런트/백엔드 점검 결과(통과·실패 모두) 보고 완료
- [x] 5화면 모두 `docs/design.md` 토큰·`output/*.html` 레이아웃과 일치 — 토큰 재사용은 완료, **2026-09-24~25 "결과 우선" 재설계로 5화면(업로드·대시보드·상세분석·예측 + 레퍼런스 목업) 레이아웃 구조까지 동일하게 맞춤**(`history/25`). 정식 픽셀 diff는 여전히 미수행(위 134번과 동일 사유 — 도구 부재)

### 일정이 빠듯할 경우 축소 순서 (`phase_03_plan.md`, 뒤로 갈수록 먼저 잘라냄)
1. 디자인 픽셀 단위 일치
2. ③-4 Y 추이 그래프
3. ③-3 형명별 세부 테이블(용량군 요약 카드만 유지)
4. (최후 수단) 베이스라인(X→Z) 모델 — 이 경우 "캐스케이드 구조 완결성" 지표 미달성으로 명시 보고

---

## 범위 밖 (착수 금지 — `05_mvp-구현-실행계획.md` §2.2)

- [x] **(2026-09-30 v2 착수로 일부 해제)** 채점(검증) 모듈의 train/val 분리는 실제로 도입함
  (`backend/analysis/scoring.py`, `.docs/35` 참조) — 표본이 충분하면 학습에 안 쓴 val 표본으로만
  채점, 부족하면 in-sample로 정직하게 폴백.
- [ ] (여전히 하지 않음) 1·2단 **회귀 자체**(`AnalysisRun`, X→Y/X+Y→Z/베이스라인)의 R²/RMSE
  정식 홀드아웃 검증 — 위 채점 모듈과는 별개로, 회귀 학습 자체는 지금도 전체 데이터로 한다.
- [ ] (하지 않음) 재학습 파이프라인 정식화
- [ ] (하지 않음) 캐스케이드 vs 베이스라인 정량 비교
- [ ] (하지 않음) `saturation_calc` 활성화
- [ ] (하지 않음) 외부 클라우드 API/LLM 연동, 사용자 인증/권한 체계, 다중 동시 편집 서버 인프라
