# CCA EN/SAE 규격 판정 — 대시보드·상세분석 반영 계획

## 배경

`.docs/19` Phase C로 SAE/EN CCA(방전량, Ah)를 Z2/Z3 예측 타겟까지 연결했지만, 화면에는 "포화도(Y)
↔ CCA 관계" 참고 표(대시보드)만 있고 CCA 자체가 업계 규격(EN 50342, SAE J537)을 만족하는지 여부는
어디에도 표시되지 않았다. 사용자 요청(2026-09-21):

- 대시보드·상세분석 화면 모두에 CCA 데이터를 확인할 수 있게 할 것.
- CCA 규격은 **형명 무관 고정 기준**이며 다음을 만족하면 합격:
  - **EN CCA**: 10초 시점 전압 ≥ 7.5V **AND** 6.0V까지 지속시간 ≥ 90초
  - **SAE CCA**: 7.2V까지 지속시간 ≥ 30초

조사 결과, DB(`TestData.sae_cca`/`en_cca`)에는 최종 방전량(Ah)만 저장돼 있고 판정에 필요한
전압·시간 체크포인트는 저장돼 있지 않다. 다만 원본 `AGM 시험현황_raw data.xlsx`의 `EN CCA 18℃`/
`SAE CCA(1차)\n18℃ 24H 방치` 구간에 `10초 전압`, `6.0V 지속시간(17초 포함)`, `7.2V 지속시간`
필드가 실제로 존재함을 확인했다 — ETL 파서가 지금까지 뽑지 않았을 뿐이다.

## 범위

1. `TestData`에 체크포인트 3개 컬럼 추가, ETL 파서가 실제로 채워서 저장.
2. 형명 무관 고정 임계값으로 EN/SAE 합격·불합격을 판정하는 순수 함수 추가.
3. 대시보드의 기존 "포화도↔CCA 관계" 표에 합격/불합격 배지 컬럼 추가.
4. 상세분석의 로트별 드릴다운 표(요약 화면 + 전체보기 화면)에 CCA 값·합격여부 컬럼 추가.
5. 표본이 SAE/EN 각 2건뿐이므로 회귀·통계가 아니라 "배지 표시"로만 구현(과설계 금지).

## 방법

- **스키마** (`backend/db/schema.sql`): `TestData`에 `en_cca_10s_voltage REAL`,
  `en_cca_6v_hold_sec REAL`, `sae_cca_7v2_hold_sec REAL` 추가(NULL 허용). 로컬 `app.db`는
  `CREATE TABLE IF NOT EXISTS`라 기존 파일엔 반영 안 됨 — 커밋 안 되는 로컬 산출물이므로
  `.docs/19`와 동일하게 **삭제 후 재생성**(CSV·raw 파일 재업로드)로 처리.
- **ETL** (`backend/etl/test_raw.py`): 같은 (구간, 필드) 반복 시 표기가 살짝 달라지는 문제
  ("6.0V 지속시간\n(17초 포함)" vs "6.0V 지속시간")를 흡수하는 필드명 정규화를 `_build_row_map`에
  추가하고, `_best_row`로 `10초 전압`/`6.0V 지속시간`(EN)·`7.2V 지속시간`(SAE)을 추출.
- **설정** (`backend/config/spec_thresholds.py`): `EN_CCA_10S_VOLTAGE_MIN`, `EN_CCA_6V_HOLD_SEC_MIN`,
  `SAE_CCA_7V2_HOLD_SEC_MIN` 하드코딩 상수 추가(형명별 테이블이 아니라 업계 표준 고정값이므로
  `ConstantsByModel`과는 분리).
- **분석 모듈** (`backend/analysis/cca_spec.py`, 신규): `judge_en_cca(voltage_10s, hold_6v_sec)`,
  `judge_sae_cca(hold_7v2_sec)` — 값 없으면 "판정 불가", 있으면 pass/fail. 웹 프레임워크 비의존.
- **저장소** (`backend/db/repository.py`): `get_y_vs_cca_pairs`·`get_model_lot_rows`의 SELECT에
  체크포인트 3컬럼 추가. `TEST_DATA_COLUMNS`/`OPTIONAL_TEST_COLUMNS`에도 추가(CSV 업로드 경로는
  헤더 없어도 그대로 동작해야 함 — `sae_cca`/`en_cca`와 동일한 선택 컬럼 철학).
- **라우터**: `dashboard.py`의 `/analysis/y-vs-cca`, `detail_analysis.py`의
  `/models/{model_name}/lots` 응답에 `cca_spec.judge_*` 결과를 덧붙임.
- **프런트**: `api-client.ts`의 `YVsCcaPair`/`ModelLotRow` 타입 확장. `dashboard/page.tsx`의
  CCA 표에 "EN 규격"/"SAE 규격" 배지 컬럼, `detail-analysis/page.tsx`와
  `detail-analysis/lots/[model]/page.tsx`의 로트 드릴다운 표에 CCA 값·배지 컬럼 추가.
- **테스트**: `tests/backend/test_test_raw.py`에 필드명 표기 차이 케이스 추가,
  `tests/backend/test_cca_spec.py`(신규) 추가.

## 완료 기준

- `pytest tests/backend -q`, `ruff check backend`, `next build`/`eslint` 통과.
- 실제 raw 워크북 재업로드 후 대시보드·상세분석 두 화면에서 EN/SAE 합격·불합격 배지가
  실제 값 기준으로 노출됨을 Playwright로 확인.
