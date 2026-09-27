# Day 1 — 프로젝트 셋업 + 데이터 기반 다지기 (업로드·매칭·수기입력·파생값)

> **2026-09-10 스택 피벗 반영**: Streamlit 단일 프로세스 대신 **Next.js(프런트) + FastAPI(백엔드)** 2-프로세스 구성으로 시작한다(`.docs/02_nextjs-fastapi-구현-아키텍처.md`, `.docs/03_sqlite-스키마-설계.md` 전제). 3일 기한은 그대로 유지하기로 했으므로, Streamlit 안에는 없던 **프로젝트 초기 셋업(0번 작업)**이 Day 1 맨 앞에 추가된 것이 가장 큰 차이다.
>
> ⚠️ **일정 리스크**: Next.js+FastAPI를 처음부터 쓰면 Streamlit 대비 초기 셋업(프로젝트 스캐폴딩, CORS/API 연동, 디자인 토큰 이식)에 드는 시간이 늘어난다. Day 1 안에 0~2번 작업이 끝나지 않으면 Day 2/3 일정이 그대로 밀리므로, **0번(셋업)은 최대한 빨리, 필요하면 최소 기능(업로드 화면 하나)만으로 먼저 API 연동을 검증한 뒤 나머지 화면을 붙이는 순서로 진행**한다.

## 목표

- Next.js 프런트와 FastAPI 백엔드가 로컬에서 서로 통신하고, SQLite DB가 생성되며, 더미 CSV 업로드부터 `LotDerived` 계산까지 종단간으로 1회 이상 동작한다.

## 작업 순서

0. **프로젝트 초기 셋업 (신규, Streamlit 안에는 없던 작업)**
   - `frontend/`: `create-next-app`(TypeScript, App Router)로 스캐폴딩, `design.md` §6 CSS Custom Properties를 `lib/theme.css`로 이식, `next/font`로 Pretendard/Inter 로드.
   - `backend/`: FastAPI 앱 스켈레톤(`main.py`, CORS는 `http://localhost:3000` origin만 허용), `uvicorn`으로 `127.0.0.1:8000` 기동 확인.
   - `frontend/lib/api-client.ts`에 FastAPI base URL(`127.0.0.1:8000`) 고정, 헬스체크 엔드포인트(`GET /api/health`)로 프런트↔백엔드 연동을 가장 먼저 검증한다 — 이게 되기 전까지 화면 기능 구현에 들어가지 않는다.
2. **DB 초기화**: `.docs/03_sqlite-스키마-설계.md`의 DDL을 `backend/db/schema.sql`로 옮기고, FastAPI 앱 기동 시 파일이 없으면 자동 생성하는 초기화 루틴(`backend/db/repository.py`)을 만든다.
3. **`backend/analysis/derive.py` 구현**: `prd.md` §7 `LotDerived` 컬럼 전부(잔존율, water_loss_rate, water_loss_per_ah, theoretical_water_loss, water_loss_residual, fill_per_rated, charge_ratio, cell_weight_mean/std, formation_dv)를 순수 함수로 계산. `saturation_calc`은 항상 NULL, `saturation_basis='proxy_retention'`, `saturation_source='derived'` 고정.
4. **업로드 API + 화면**: `POST /api/upload`(공정/시험 CSV 업로드 → 필수 컬럼 검증(누락 시 400 + 누락 컬럼 목록, `prd.md` §6-①) → `lot_id` 조인 → 매칭/미매칭 건수 반환, 업로드 즉시 **자동** 매칭 — 별도 실행 버튼 없음) + `frontend/app/upload/page.tsx`(`output/01_upload_matching.html` 마크업을 React로 이식, 업로드 UI는 파일 선택+**드래그앤드롭** 둘 다 지원). **동일 `lot_id` 재업로드 시 경고**(append-only 원칙, §8).
5. **수기입력 API + 화면 (2026-09-10부터 4번과 한 화면에 통합, 구 `output/02_manual_entry.html`은 `history/`로 이동)**: `GET/PUT /api/lots/{lot_id}/manual-fields`(개별 편집 API는 존치하되 화면에는 연결하지 않음, §10-20) + `GET /api/manual-fields/groups`, `PUT /api/manual-fields/batch`(그룹 일괄 입력) + `frontend/app/upload/page.tsx`의 매칭 결과 아래에 그룹 일괄 입력 패널을 이어 붙임(로트별 개별 입력 표 없음). CSV에 이미 있는 `electrolyte_temp`/`charge_amount`/`tank_temp`는 자동 표시, 비어있는 로트는 그룹 일괄 입력으로만 채운다. **MT(V)/MT(A)는 수기입력 대상이 아니며 이 화면에 전혀 노출하지 않는다**(2026-09-10 개정) — `TestData` 매칭 값은 "시험 로트 한정 심층 분석" 화면에서만 참고 지표로 다룬다(§6-②). **그룹 일괄 입력**: `charge_amount`는 `model_name` 단위, `electrolyte_temp`/`tank_temp`는 `model_name`+`prod_date` 단위로 그룹화해 값 하나를 그룹 내 미입력 로트 전체에 일괄 반영(이미 값 있는 로트는 덮어쓰지 않음, 확인 다이얼로그 필수). 미입력 항목이 남은 로트는 1단 분석 대상 제외 목록으로 안내(§6-②). 저장 시 `derive.py` 호출 → `LotDerived` 삽입. **업로드·매칭·수기입력이 한 화면에서 끝나도 1단·2단 분석 실행은 화면 하단의 명시적 버튼을 눌러야 시작**된다(자동 실행 아님).
6. **더미 데이터로 검증**: `process_data.csv`(100행) 전량 업로드 → 매칭 59건/미매칭 41건 확인 → `LotDerived` 100행 생성 확인(잔존율 값이 `prd.md`에 기록된 범위와 대략 일치하는지 육안 확인).

## Day 1 완료 기준

- [ ] `next dev`(프런트)와 `uvicorn`(백엔드)이 동시에 떠 있고, 헬스체크 API가 프런트에서 정상 호출됨
- [ ] `backend/db/schema.sql` 실행 시 오류 없이 9개 테이블 생성됨
- [ ] `process_data.csv`/`test_data.csv` 업로드 → 매칭 59/미매칭 41 화면에 정상 표시(`output/01_upload_matching.html` 톤 그대로)
- [ ] `LotDerived`에 100개 로트 전부 파생값이 계산되어 저장됨(재계산 없이 다음 날 바로 조회 가능)
- [ ] `fill_weight`/`water_loss`가 어느 화면에서도 "1단 X 후보"로 노출되지 않음(§6-③ 원칙이 UI 단계부터 지켜지는지 확인)

## 다음날 연계

Day 2는 `LotDerived`가 이미 채워져 있고, 프런트↔백엔드 연동(0번 작업)이 끝나 있다는 것을 전제로 시작한다. 0번 작업이 끝나지 않은 상태로 Day 2를 시작하지 않는다 — 이 경우 남은 화면 수를 줄이는 것을 우선 검토한다(`.docs/04_기술-스택-정의서.md` §3 참조).
