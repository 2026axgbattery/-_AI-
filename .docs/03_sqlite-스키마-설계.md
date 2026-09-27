# SQLite 스키마 설계 (DDL)

> `docs/prd.md` §7 "데이터 모델 스케치"를 실제 SQLite `CREATE TABLE` 문으로 구체화한 문서입니다. 구현 시 아래 DDL을 그대로 `backend/db/schema.sql`(`02_nextjs-fastapi-구현-아키텍처.md` 참조)로 옮겨 사용합니다. `docs/prd.md` §11 "관련 문서"에서 링크됩니다.
>
> **2026-09-10 스택 피벗 반영**: 테이블 구조·DDL은 변경 없음(SQLite 유지 결정). 다만 이 스키마에 접근하는 주체가 Streamlit 앱 프로세스에서 **FastAPI 백엔드 프로세스**로 바뀌었다 — Next.js(프런트엔드)는 SQLite에 직접 접근하지 않고 항상 FastAPI API를 거친다(§3 참조).
>
> **2026-09-11 추가(업로드 이력 확인·선택 삭제·전체 삭제)**: 아래 DDL에는 반영돼 있지 않지만 `backend/db/schema.sql`에는 `UploadBatch` 테이블(`batch_id` PK, `file_type` 'process'|'test', `filename`, `row_count`, `uploaded_at`)이 추가됐고, `ProcessData`·`TestData`에 `upload_batch_id INTEGER REFERENCES UploadBatch(batch_id)` 컬럼이 추가됐다. 업로드 화면에서 파일 단위로 이력을 보고 선택 삭제할 수 있게 하기 위함이다(`GET/DELETE /api/upload/batches`, `DELETE /api/upload/data`). **이는 append-only 원칙(위 §1)을 깨는 것이 아니라 별개의 명시적 관리자 조작이다** — 정상적인 재업로드는 여전히 기존 이력을 지우지 않고 쌓이지만, 사용자가 "잘못 올린 파일을 선택해서 되돌리기"를 명시적으로 요청했을 때만 삭제가 일어난다. `process` 배치를 삭제해 어떤 로트의 `ProcessData`가 하나도 안 남으면 그 로트는 고아로 간주해 `Lot`/`LotDerived`/`TestData`/`Prediction`/`SpecJudgment`/`CauseDiagnosis`까지 함께 정리한다(`backend/db/repository.py`의 `delete_upload_batch` 참조).
>
> **2026-09-11 추가(실제 raw data 업로드 지원 — `fill_weight`/`water_loss` NOT NULL 완화)**: 아래 DDL·§6-③ 서술은 애초에 `fill_weight`/`water_loss`가 항상 존재한다고 가정했지만(더미 CSV는 실제로 항상 채워져 있었음), 현장 실제 raw data(`.docs/14_raw-data-업로드-지원-계획.md`)에는 해당 공정 단계(주액/전보충전 전 계량) 자체가 누락된 로트가 있다(전체 32,088행 중 fill_weight 332행·water_loss 94행 결측, 사용자 확인 후 적용). `ProcessData.fill_weight`/`water_loss`, `LotDerived.retention_rate`를 `NOT NULL`에서 `NULL` 허용으로 완화했고, `backend/analysis/derive.py`의 `compute_lot_derived`도 두 값이 없으면 `retention_rate`/`water_loss_rate`/`water_loss_residual`/`fill_per_rated`를 NULL로 반환하도록 수정했다(예외 대신) — 그런 로트는 Y가 없으므로 1단(X→Y) 분석 대상에서 자연스럽게 제외된다.

## 1. 설계 원칙

- **append-only**: `Lot`/`ProcessData`/`TestData`/`LotDerived`는 재업로드 시 덮어쓰지 않는다(`docs/prd.md` §7·§8). DB 레벨에서 `lot_id`를 유니크로 강제하면 재업로드 자체가 막혀버리므로, **`lot_id`는 유니크 제약을 걸지 않고 애플리케이션(`backend/db/repository.py`)이 삽입 전에 기존 `lot_id` 존재 여부를 조회해 경고를 띄운 뒤 사용자가 무시/교체를 선택**하게 한다(§8 "동일 lot_id가 재업로드됨" 엣지케이스). 대신 `(lot_id, ingested_at)` 복합 인덱스로 이력 조회를 지원한다.
- **JSON 컬럼**: `correlation_matrix`, `regression_coefficients`, `vif`, `spec_thresholds_used`, `ranked_factors`는 SQLite에 네이티브 JSON 타입이 없으므로 `TEXT`에 `json.dumps` 직렬화해 저장한다. 역직렬화는 `backend/db/repository.py`의 책임이며 `analysis/` 모듈은 이미 파싱된 dict/DataFrame만 다룬다.
- **enum은 CHECK 제약으로 강제**: 스키마 스케치에 문자열 enum으로 표기된 필드(`stage`, `target`, `saturation_basis` 등)는 `CHECK (col IN (...))`로 값 오탈자를 방지한다.
- **정규화 파생값은 저장, 재계산 안 함**: `LotDerived`는 `analysis/derive.py`가 계산한 결과를 저장하는 테이블이며, 화면은 원본 `ProcessData`/`TestData`를 매번 재계산하지 않고 이 테이블을 읽는다(성능·재현성 목적).

## 2. DDL

```sql
PRAGMA foreign_keys = ON;

-- =========================================================
-- Lot: 로트 마스터
-- =========================================================
CREATE TABLE Lot (
    lot_id          TEXT PRIMARY KEY,        -- 예: "105C26A016250954S3"
    model_name      TEXT NOT NULL,           -- 예: AGM105_S1
    rated_capacity  REAL NOT NULL,           -- Ah
    line_no         TEXT,
    prod_date       TEXT NOT NULL,           -- ISO 8601 date (YYYY-MM-DD) — 일/월/연 추이 집계 기준
    ingested_at     TEXT NOT NULL DEFAULT (datetime('now'))  -- 시스템 업로드 시각, prod_date와 별개
);
CREATE INDEX idx_lot_model_name  ON Lot(model_name);
CREATE INDEX idx_lot_prod_date   ON Lot(prod_date);

-- =========================================================
-- ProcessData: 공정 CSV 원본 (lot_id당 1행, append-only)
-- =========================================================
CREATE TABLE ProcessData (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    lot_id           TEXT NOT NULL REFERENCES Lot(lot_id),
    cell1_weight REAL, cell2_weight REAL, cell3_weight REAL,
    cell4_weight REAL, cell5_weight REAL, cell6_weight REAL,
    cell1_ginap  REAL, cell2_ginap  REAL, cell3_ginap  REAL,
    cell4_ginap  REAL, cell5_ginap  REAL, cell6_ginap  REAL,
    fill_weight      REAL NOT NULL,   -- Y(잔존율) 산출 원천 — 1단 X로 사용 금지 (docs/prd.md §6-③)
    water_loss       REAL NOT NULL,   -- 동일
    voltage_1st      REAL,
    voltage_2nd      REAL,
    bath_no          TEXT,            -- 통제/층(group) 변수, 회귀계수 대상 아님
    circuit_no       TEXT,            -- 동일
    soaking_time_sec REAL,
    aging_days       REAL,
    electrolyte_temp REAL,
    charge_amount    REAL,
    tank_temp        REAL,
    ingested_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_processdata_lot_id ON ProcessData(lot_id);

-- =========================================================
-- TestData: 시험 CSV 원본 (lot_id당 1행, process 대비 부분 매칭, append-only)
-- =========================================================
CREATE TABLE TestData (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    lot_id              TEXT NOT NULL REFERENCES Lot(lot_id),
    initial_voltage     REAL,
    initial_resistance  REAL,
    initial_weight      REAL,
    initial_cca         REAL,
    rated_capacity      REAL,
    discharge_amount    REAL NOT NULL,   -- Z(20시간 용량, Ah) 확정값
    charge_amount_20h   REAL,            -- charge_rate 산출용, Z 아님
    capacity_rate       REAL,            -- = discharge_amount / rated_capacity * 100
    charge_rate         REAL,            -- = charge_amount_20h / discharge_amount * 100
    mt_voltage          REAL,            -- 시험 전용, 1단 X 제외 대상
    mt_current          REAL,            -- 동일
    tested_at           TEXT,            -- 더미 CSV에는 없음 — §10 Open Question #14
    ingested_at         TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_testdata_lot_id ON TestData(lot_id);

-- =========================================================
-- ConstantsByModel: 모델별 물리 상수 + SPEC 하한 (saturation_calc 활성화 시 사용,
-- 담당자 확인 결과 공극 상수 확보는 스트레치 목표 — docs/domain-constants.md 참조)
-- =========================================================
CREATE TABLE ConstantsByModel (
    model_name              TEXT PRIMARY KEY,
    rated_capacity          REAL NOT NULL,
    saturation_basis_target TEXT CHECK (saturation_basis_target IN ('cell', 'separator')),
    void_volume_separator   REAL,   -- 더미 데이터에 없음, 확보 불투명
    void_volume_plate       REAL,   -- 동일
    free_volume             REAL,   -- 동일
    design_fill_weight      REAL,
    fill_sg                 REAL,
    spec_lower_y            REAL,   -- §10 Open Question #11 확정 전까지 NULL 허용
    spec_lower_z            REAL    -- 동일
);

-- =========================================================
-- LotDerived: 로트별 파생 인자 (analysis/derive.py 산출물, append-only)
-- =========================================================
CREATE TABLE LotDerived (
    lot_id                  TEXT PRIMARY KEY REFERENCES Lot(lot_id),
    retention_rate          REAL NOT NULL,  -- Y(잔존율, proxy)
    water_loss_rate         REAL,
    water_loss_per_ah       REAL,
    theoretical_water_loss  REAL,
    water_loss_residual     REAL,
    fill_per_rated          REAL,
    charge_ratio            REAL,
    cell_weight_mean        REAL,
    cell_weight_std         REAL,
    formation_dv            REAL,
    saturation_calc         REAL,            -- 담당자 확인 전까지 항상 NULL (§10-6)
    saturation_basis        TEXT NOT NULL DEFAULT 'proxy_retention'
                             CHECK (saturation_basis IN ('cell', 'separator', 'proxy_retention')),
    saturation_source       TEXT NOT NULL DEFAULT 'derived'
                             CHECK (saturation_source IN ('measured', 'derived')),
    derived_at              TEXT NOT NULL DEFAULT (datetime('now'))
);

-- =========================================================
-- AnalysisRun: 회귀분석 실행 이력
-- =========================================================
CREATE TABLE AnalysisRun (
    run_id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at                  TEXT NOT NULL DEFAULT (datetime('now')),
    stage                   TEXT NOT NULL CHECK (stage IN ('x_to_y', 'xy_to_z', 'x_to_z_baseline')),
    lot_range               TEXT,            -- 대상 로트 집합 설명 또는 JSON 배열(TEXT 직렬화)
    correlation_matrix      TEXT,            -- JSON
    regression_coefficients TEXT,            -- JSON
    vif                     TEXT,            -- JSON
    r_squared               REAL,            -- 참고용, v2에서 정식 검증
    is_latest_for_stage     INTEGER NOT NULL DEFAULT 0 CHECK (is_latest_for_stage IN (0, 1))
);
CREATE INDEX idx_analysisrun_stage_latest ON AnalysisRun(stage, is_latest_for_stage);

-- =========================================================
-- Prediction
-- =========================================================
CREATE TABLE Prediction (
    prediction_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    lot_id          TEXT REFERENCES Lot(lot_id),      -- 수동입력 예측은 NULL 허용
    run_id          INTEGER NOT NULL REFERENCES AnalysisRun(run_id),
    target          TEXT NOT NULL CHECK (target IN ('y', 'z')),
    predicted_value REAL NOT NULL,
    input_y_source  TEXT CHECK (input_y_source IN ('measured', 'predicted')),  -- target='z'일 때만 의미
    source          TEXT NOT NULL CHECK (source IN ('manual', 'batch_unmatched')),
    predicted_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_prediction_lot_id ON Prediction(lot_id);

-- =========================================================
-- SpecJudgment
-- =========================================================
CREATE TABLE SpecJudgment (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    lot_id               TEXT REFERENCES Lot(lot_id),
    prediction_id        INTEGER REFERENCES Prediction(prediction_id),
    target               TEXT NOT NULL CHECK (target IN ('y', 'z')),
    spec_result          TEXT NOT NULL CHECK (spec_result IN ('pass', 'fail')),
    spec_thresholds_used TEXT   -- JSON
);

-- =========================================================
-- CauseDiagnosis
-- =========================================================
CREATE TABLE CauseDiagnosis (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    lot_id             TEXT REFERENCES Lot(lot_id),
    prediction_id      INTEGER REFERENCES Prediction(prediction_id),
    target             TEXT NOT NULL CHECK (target IN ('y', 'z')),
    ranked_factors     TEXT,   -- JSON: [{factor, contribution, rank}, ...]
    recommendation_text TEXT,
    generated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
```

## 3. 조회 패턴 메모 (구현 시 참고)

- **화면 진입 시 최신 계수 로드**: `SELECT * FROM AnalysisRun WHERE stage = ? AND is_latest_for_stage = 1` — 새 `AnalysisRun`을 삽입할 때는 같은 `stage`의 기존 `is_latest_for_stage=1` 행을 0으로 갱신하는 트랜잭션을 `backend/db/repository.py`에 둔다.
- **형명별 상세 분석(③-3)**: 별도 집계 테이블 없이 `LotDerived JOIN Lot USING (lot_id)`를 `model_name`으로 group-by. 표본 수(n)는 이 쿼리의 `COUNT(*)`로 매 조회 시 함께 반환해, `docs/correlation-reliability-review.md` §4가 지적한 "표본 부족을 항상 표시" 요구를 만족시킨다.
- **일/월/연 추이(③-4)**: `LotDerived JOIN Lot USING (lot_id)`를 `Lot.prod_date`로 group-by(`strftime('%Y-%m-%d', prod_date)` / `strftime('%Y-%m', prod_date)` / `strftime('%Y', prod_date)`). 별도 집계 테이블 불필요(`docs/prd.md` §7 원칙과 동일).
- **동시 접근**: `docs/prd.md` §8 "SQLite 파일 동시 접근" 엣지케이스에 따라, 쓰기 연결은 FastAPI 백엔드 프로세스 하나만 열고(Next.js는 SQLite에 직접 접근하지 않음), 열람자 시나리오가 생기면 읽기 전용 연결(`sqlite3.connect(..., uri=True)` + `mode=ro`)만 허용한다. 이번 3일 MVP는 단일 담당자 사용을 기본 전제로 하므로 실제 다중 접속 처리는 §10 Open Question #13(유관부서 열람 경로 확정) 이후 반영한다.
