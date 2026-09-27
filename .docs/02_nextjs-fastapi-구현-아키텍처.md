# Next.js + FastAPI 구현 아키텍처

> **2026-09-10 스택 피벗**: 기존 계획은 "3일 집체 MVP는 Streamlit, 3일 이후 v2에서 디자인 완성을 위해 Next.js+FastAPI로 전환"이었다. 사용자 결정으로 **Streamlit 단계를 건너뛰고 3일 집체 MVP부터 Next.js+FastAPI로 시작**하기로 변경했다(3일 기한은 유지, `docs/design.md` 세방 CI도 MVP 단계부터 픽셀 단위로 구현). 이 문서는 이전 `02_streamlit-구현-아키텍처.md`를 대체한다 — 해당 파일은 삭제됨. `docs/prd.md` §11 "관련 문서"에서 링크된다.

## 1. 왜 이 구조인가

`analysis/`(회귀·VIF·p-value·원인진단)는 이미 pandas/numpy/scikit-learn/scipy로 설계돼 있고 (`docs/prd.md` §6, `docs/correlation-reliability-review.md`), 이 자산을 재사용하지 않고 TypeScript로 다시 짜면 3일 안에 정확도·구현 리스크가 커진다. 따라서 **분석 엔진은 FastAPI(Python)로 유지하고, 화면만 Next.js(React)로 처음부터 간다** — 이것이 원래 v2에서 하려던 전환을 그대로 MVP로 앞당기는 것뿐, 새로운 스택을 발명하는 것이 아니다.

- **역할 분리**: Next.js는 화면(App Router, React 컴포넌트, `docs/design.md` 토큰 적용)만 담당. 모든 데이터 처리·회귀·판정·진단은 FastAPI 엔드포인트가 담당.
- **로컬 전용**: FastAPI는 `127.0.0.1`에만 바인딩(`CLAUDE.md`·`docs/prd.md` §3 Non-goals의 사외반출 금지 원칙). Next.js 개발 서버도 로컬에서만 실행하고, 프로덕션에서도 창원공장 폐쇄망 내 로컬 PC 실행을 벗어나지 않는다.
- **단일 SQLite 파일**: 스키마는 `.docs/03_sqlite-스키마-설계.md` 그대로 유지. FastAPI 프로세스 하나만 SQLite에 쓰기 연결을 갖고, Next.js는 절대 SQLite에 직접 접근하지 않고 항상 FastAPI를 거친다(동시 접근 문제를 프로세스 경계로 단순화).

## 2. 폴더 구조

```
frontend/                         # Next.js (App Router, TypeScript)
  app/
    upload/page.tsx               # output/01_upload_matching.html 대응 — ① 업로드·매칭 + ② 수기입력(그룹 일괄 입력)까지 한 화면(2026-09-10 통합, 구 manual-entry/page.tsx는 없음)
    detail-analysis/page.tsx      # output/03_detail_analysis.html 대응 — ③-3/③-4
    prediction/page.tsx           # output/04_prediction.html 대응 — ④-1/④-2
    dashboard/page.tsx            # output/analysis_dashboard.html 대응 — ③-1/③-2/⑤
    layout.tsx                    # 공통 셸(내비게이션, docs/design.md 토큰 <style> 주입)
  lib/
    api-client.ts                 # FastAPI 호출 wrapper (fetch, 항상 http://127.0.0.1:<port>)
    theme.css                     # docs/design.md §6 CSS Custom Properties 이식(변수명 그대로)
  components/                     # KPI 카드, 배지, 테이블 등 output/*.html 패턴을 React 컴포넌트로 이식

backend/                          # FastAPI (Python)
  main.py                         # FastAPI 앱 엔트리, CORS는 localhost 프런트 origin만 허용
  routers/
    upload.py                     # ① 업로드·매칭 + ② 수기입력(그룹 일괄 입력) API — 2026-09-10 manual_entry.py를 여기로 통합
    dashboard.py                  # ③-1/③-2 회귀·KPI API
    detail_analysis.py            # ③-3/③-4 형명별 상세·추이 API
    prediction.py                 # ④-1/④-2 예측 API
    diagnosis.py                  # ⑤ SPEC 판정·원인진단 API
  analysis/                       # 순수 Python. FastAPI(웹 레이어)와도 분리 유지 — 라우터가 이 모듈만 호출.
    derive.py / regression.py / vif.py / significance.py / diagnosis.py / trend.py
    # 역할은 이전 Streamlit 아키텍처안과 동일(재사용). "UI 비의존"이라는 원래 원칙이
    # 이제는 "웹 프레임워크(FastAPI) 비의존"으로 한 단계 더 강화된 것뿐이다.
  db/
    schema.sql                    # `.docs/03_sqlite-스키마-설계.md`의 DDL 원본
    repository.py                 # CRUD + JSON 컬럼 직렬화/역직렬화, append-only 검증
  config/
    spec_thresholds.py
tests/
  backend/                        # pytest — analysis/ 각 함수 단위 테스트
  frontend/                       # (여유 있으면) 컴포넌트 테스트, 3일 범위에서는 선택사항
```

- `frontend/app/*/page.tsx`는 여전히 `output/*.html` 5개 목업과 1:1 대응시켜, 화면을 찾을 때 목업↔실 구현을 바로 교차 참조한다.
- `backend/analysis/`는 이전 Streamlit 아키텍처안의 모듈을 **그대로 재사용**한다 — 새로 설계하지 않는다.

## 3. 화면별 API 매핑 (docs/prd.md §6 요구사항 → FastAPI 엔드포인트)

| 화면(Next.js) | docs/prd.md 요구사항 | FastAPI 엔드포인트(예시) | 호출하는 analysis/ 함수 | 테이블 |
|---|---|---|---|---|
| `/upload` | ① CSV 업로드(파일 선택 + 드래그앤드롭) + lot_id 자동 매칭 | `POST /api/upload` | `derive.validate_columns` | `Lot`, `ProcessData`, `TestData` |
| `/upload` (같은 화면, 매칭 결과 아래) | ② 자동 채움 + 그룹 일괄 입력(2026-09-10부터 별도 화면 없이 `/upload`에 통합, 개별 편집 UI 제거 — `docs/prd.md` §10-20. `charge_amount`는 2026-09-21부터 이 대상에서 제외됨 — `ChargeProgramSpec`가 대체, `docs/prd.md` §6-② 참조) | `GET /api/manual-fields/groups?field=electrolyte_temp\|tank_temp`(그룹 목록·미입력 건수 조회), `PUT /api/manual-fields/batch`(그룹 필터+값 일괄 반영). `GET/PUT /api/lots/{lot_id}/manual-fields`(개별 편집, `charge_amount` 포함 3필드 모두 가능)는 화면에 연결하지 않고 API만 존치 | `derive.compute_lot_derived` | `ProcessData`, `TestData`, `LotDerived` |
| `/dashboard` (③-1) | X→Y 상관·회귀·VIF, KPI | `POST /api/analysis/x-to-y` | `regression.fit_x_to_y`, `vif.compute_vif`, `significance.pearson_p` | `LotDerived` → `AnalysisRun` |
| `/dashboard` (③-2) | X+Y→Z 회귀 + 베이스라인 | `POST /api/analysis/xy-to-z`, `POST /api/analysis/x-to-z-baseline` | `regression.fit_xy_to_z`, `fit_x_to_z_baseline` | `LotDerived`, `TestData` → `AnalysisRun` |
| `/detail-analysis` (③-3) | 형명별 X·Y·Z 비교 | `GET /api/models/summary` | 없음(조회) | `AnalysisRun`, `LotDerived` |
| `/detail-analysis` (③-4) | 형명별 Y 추이 | `GET /api/models/{model_name}/trend?period=day|month|year` | `trend.aggregate_by_period` | `LotDerived` |
| `/prediction` (④-1) | 미매칭 로트 Y 일괄 산출 | `POST /api/predict/y` | `regression.predict_y` | `AnalysisRun` → `Prediction` |
| `/prediction` (④-2) | Ŷ 기반 Z 일괄 예측 | `POST /api/predict/z` | `regression.predict_z` | `AnalysisRun`, `Prediction` |
| `/dashboard` (⑤) | Y·Z SPEC 판정 + 원인진단 | `POST /api/diagnosis` | `diagnosis.judge_spec`, `diagnosis.rank_causes` | `ConstantsByModel` → `SpecJudgment`, `CauseDiagnosis` |

이 표는 이전 Streamlit 아키텍처안의 "화면별 데이터 흐름" 표를 API 경계로 다시 그린 것뿐이며, `docs/prd.md` §6 요구사항을 새로 추가하지 않는다.

## 4. Next.js ↔ FastAPI 연동 원칙

- Next.js는 서버 컴포넌트/클라이언트 컴포넌트에서 `lib/api-client.ts`를 통해서만 FastAPI를 호출한다. 브라우저에서 SQLite나 파일시스템에 직접 접근하지 않는다.
- 개발 시 `next dev`(예: `:3000`)와 `uvicorn backend.main:app`(예: `:8000`)을 각각 로컬에서 띄우고, Next.js `rewrites` 또는 `lib/api-client.ts`의 base URL로 `127.0.0.1:8000`을 고정한다. 외부 origin으로의 프록시는 두지 않는다.
- **최신 모델 로드 원칙(Streamlit 안과 동일)**: 화면은 절대 클라이언트 상태를 "학습된 계수의 원천"으로 쓰지 않는다. 화면 진입 시 항상 FastAPI를 통해 `AnalysisRun.is_latest_for_stage=1`을 stage별로 조회해 최신 계수를 받는다. 1단(X→Y)과 2단(X+Y→Z)/베이스라인의 "최근 학습 시점"을 화면에 분리 표시하는 요구사항(`docs/prd.md` §6-③-2)은 동일하게 유지된다.

## 5. 디자인 이식 원칙 (docs/design.md 픽셀 단위 구현 — MVP부터 적용)

기존 Streamlit 안에서는 "1단계 목표는 디자인 완성도가 아니라 기능적 완결성"이었지만, **이번 피벗 결정으로 MVP부터 `docs/design.md` 세방 CI를 픽셀 단위로 구현하는 것이 목표로 격상**됐다.

- `docs/design.md` §6의 CSS Custom Properties(`--color-*`, `--space-*`, `--radius-*`, `--font-family-base`)를 `frontend/lib/theme.css`에 그대로 옮기고 `app/layout.tsx`에서 전역 로드한다.
- `output/*.html` 5개 목업의 마크업·클래스 구조를 React 컴포넌트로 그대로 이식한다(Streamlit 위젯 제약이 없으므로 100% 재현 가능 — 이전 안의 "위젯 형태 제약상 100% 동일하지 않을 수 있다"는 단서는 더 이상 적용되지 않는다).
- 오렌지·그린 동시 강조 금지, `sebang-gray-500` 본문 텍스트 금지 등 `docs/design.md` §7 금지사항은 동일하게 적용한다.
- Pretendard(국문)/Inter(영문) 웹폰트를 `next/font`로 로드한다.

## 6. 로컬 전용 원칙 재확인

- FastAPI 어디에도 외부 네트워크 호출(HTTP 클라이언트, 클라우드 SDK, 외부 LLM API)을 두지 않는다. `analysis/`는 pandas/numpy/scikit-learn/scipy만 사용(변경 없음).
- Next.js 프로덕션 빌드도 별도 클라우드 배포 없이 로컬 PC에서 `next start`로 서빙한다(`docs/prd.md` §3 Non-goals "다중 동시 편집을 위한 서버 인프라 구축" 범위 밖 유지).
- SQLite 파일은 FastAPI 프로세스가 있는 로컬 디스크 경로 하나로 고정.

## 7. 이번 피벗으로 사라진 것 / 남은 것

| 항목 | 상태 |
|---|---|
| `pages/*.py`(Streamlit), `st.session_state`, `st.markdown` 커스텀 CSS | **폐기** — Next.js `app/*/page.tsx` + React 상태로 대체 |
| `analysis/`(회귀·VIF·p-value·원인진단 순수 Python 모듈) | **그대로 유지** — FastAPI 라우터가 호출하는 형태로 재사용 |
| SQLite 스키마(`.docs/03_sqlite-스키마-설계.md`) | **그대로 유지** — 테이블·컬럼 변경 없음 |
| "1단계 기능 우선, 2단계 디자인 완성" 2단계 원칙 | **폐기** — 처음부터 `docs/design.md` 픽셀 단위 구현 목표로 통합 |
