PRAGMA foreign_keys = ON;

-- =========================================================
-- Lot: 로트 마스터
-- =========================================================
CREATE TABLE IF NOT EXISTS Lot (
    lot_id          TEXT PRIMARY KEY,        -- 예: "105C26A016250954S3"
    model_name      TEXT NOT NULL,           -- 예: AGM105_S1
    rated_capacity  REAL NOT NULL,           -- Ah
    line_no         TEXT,
    prod_date       TEXT NOT NULL,           -- ISO 8601 date (YYYY-MM-DD) — 일/월/연 추이 집계 기준
    ingested_at     TEXT NOT NULL DEFAULT (datetime('now'))  -- 시스템 업로드 시각, prod_date와 별개
);
CREATE INDEX IF NOT EXISTS idx_lot_model_name  ON Lot(model_name);
CREATE INDEX IF NOT EXISTS idx_lot_prod_date   ON Lot(prod_date);

-- =========================================================
-- UploadBatch: 업로드 이력 (.docs/13 — 업로드 파일 단위 확인·선택 삭제·전체 삭제 지원용).
-- append-only 원칙(재업로드해도 기존 이력을 덮어쓰지 않음)과는 별개로, 잘못 올린 파일을
-- 되돌리기 위한 명시적 관리자 조작의 단위다.
-- =========================================================
CREATE TABLE IF NOT EXISTS UploadBatch (
    batch_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    file_type   TEXT NOT NULL CHECK (file_type IN ('process', 'test')),
    filename    TEXT NOT NULL,
    row_count   INTEGER NOT NULL,
    uploaded_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- =========================================================
-- ProcessData: 공정 CSV 원본 (lot_id당 1행, append-only)
-- =========================================================
CREATE TABLE IF NOT EXISTS ProcessData (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    lot_id           TEXT NOT NULL REFERENCES Lot(lot_id),
    upload_batch_id  INTEGER REFERENCES UploadBatch(batch_id),
    cell1_weight REAL, cell2_weight REAL, cell3_weight REAL,
    cell4_weight REAL, cell5_weight REAL, cell6_weight REAL,
    cell1_ginap  REAL, cell2_ginap  REAL, cell3_ginap  REAL,
    cell4_ginap  REAL, cell5_ginap  REAL, cell6_ginap  REAL,
    fill_weight      REAL,            -- Y(잔존율) 산출 원천 — 1단 X로 사용 금지 (prd.md §6-③)
                                       -- 2026-09-11: 실제 raw data에는 해당 공정 단계 자체가
                                       -- 누락된 로트가 있어 NULL 허용으로 완화(.docs/14). NULL이면
                                       -- LotDerived의 Y 관련 파생값도 NULL로 남아 분석에서 제외된다.
    water_loss       REAL,            -- 동일
    voltage_1st      REAL,
    bath_no          TEXT,            -- 통제/층(group) 변수, 회귀계수 대상 아님
    circuit_no       TEXT,            -- 동일
    soaking_time_sec REAL,
    aging_days       REAL,
    voltage_2nd      REAL,
    electrolyte_temp REAL,
    charge_amount    REAL,
    tank_temp        REAL,
    ingested_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_processdata_lot_id ON ProcessData(lot_id);
CREATE INDEX IF NOT EXISTS idx_processdata_batch ON ProcessData(upload_batch_id);

-- =========================================================
-- TestData: 시험 CSV 원본 (lot_id당 1행, process 대비 부분 매칭, append-only)
-- =========================================================
CREATE TABLE IF NOT EXISTS TestData (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    lot_id              TEXT NOT NULL REFERENCES Lot(lot_id),
    upload_batch_id     INTEGER REFERENCES UploadBatch(batch_id),
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
    sae_cca             REAL,            -- 2026-09-21: 신뢰성 시험 raw data 'SAE CCA(1차) 18℃
                                          -- 24H 방치' 구간의 방전량(Ah). Z 후보(Z2), initial_cca와는
                                          -- 단위·성격이 달라 별도 컬럼(.docs/19)
    en_cca               REAL,           -- 동일, 'EN CCA 18℃' 구간의 방전량(Ah). Z 후보(Z3)
    en_cca_10s_voltage   REAL,           -- 2026-09-21(.docs/20): EN CCA 10초 시점 전압(V) — 규격
                                          -- 판정용(analysis/cca_spec.py)
    en_cca_6v_hold_sec   REAL,           -- EN CCA 6.0V까지 지속시간(초) — 동일
    sae_cca_7v2_hold_sec REAL,           -- SAE CCA 7.2V까지 지속시간(초) — 동일
    tested_at           TEXT,            -- 더미 CSV에는 없음 — §10 Open Question #14
    ingested_at         TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_testdata_lot_id ON TestData(lot_id);
CREATE INDEX IF NOT EXISTS idx_testdata_batch ON TestData(upload_batch_id);

-- =========================================================
-- ConstantsByModel: 모델별 물리 상수 + SPEC 하한 (saturation_calc 활성화 시 사용,
-- 담당자 확인 결과 공극 상수 확보는 스트레치 목표 — domain-constants.md 참조)
-- =========================================================
CREATE TABLE IF NOT EXISTS ConstantsByModel (
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
CREATE TABLE IF NOT EXISTS LotDerived (
    lot_id                  TEXT PRIMARY KEY REFERENCES Lot(lot_id),
    retention_rate          REAL,           -- Y(잔존율, proxy). 2026-09-11: 원본에 fill_weight/
                                             -- water_loss가 없는 로트는 NULL(.docs/14) — 해당
                                             -- 로트는 1단(X→Y) 분석 대상에서 자연스럽게 제외
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
    charge_program_deviation_pct REAL,   -- 신규(2026-09-21, .docs/19 Phase B) — 실제 charge_amount가
                                          -- 해당 형명·바이어의 충전 STEP 프로그램 Total 충전량[Ah]
                                          -- 대비 얼마나 벗어났는지(%). 매칭되는 프로그램이 없으면 NULL
    derived_at              TEXT NOT NULL DEFAULT (datetime('now'))
);

-- =========================================================
-- ChargeProgramSpec: 형명(정격용량)·바이어 코드별 충전 STEP 프로그램 기준표
-- (신규, 2026-09-21, .docs/19 Phase B — 팀장 피드백 "충전 방법 SPEC/STEP 반영")
-- 참조/마스터 테이블 — 기준 파일을 재업로드하면 전체를 교체한다(append-only 아님).
-- =========================================================
CREATE TABLE IF NOT EXISTS ChargeProgramSpec (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    rated_capacity       REAL NOT NULL,     -- 정격용량(Ah). 원본 파일의 "92" 라벨은 사용자 확인에
                                             -- 따라 90으로 정규화해 저장(.docs/19)
    buyer_code           TEXT NOT NULL,     -- model_name 접미 문자와 매칭. 'All'이면 해당
                                             -- 용량군 전체에 적용(형명별 접미 코드 구분 없음)
    program_label        TEXT NOT NULL,     -- 원본 블록 제목(예: "AGM70_H, Y, Z, C_35hr")
    is_variant           INTEGER NOT NULL DEFAULT 0 CHECK (is_variant IN (0, 1)),
                                             -- 임시/변경 버전이면 1. 같은 (rated_capacity, buyer_code)에
                                             -- 기본·변형 프로그램이 공존할 수 있어 조회 시 기본을 우선한다
    charge_hours         REAL,              -- Total 시간[Hr]
    total_charge_ah       REAL,             -- Total 충전량[Ah] — 이탈도 계산 기준
    total_electricity_c  REAL,              -- Total 전기량[C]
    steps_json           TEXT,              -- STEP별 구분/전류[A]/시간[Hr]/충전량[Ah]/전기량[C] 원본(JSON)
    source_file          TEXT,
    ingested_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_chargeprogramspec_lookup
    ON ChargeProgramSpec(rated_capacity, buyer_code);

-- =========================================================
-- AnalysisRun: 회귀분석 실행 이력
-- =========================================================
CREATE TABLE IF NOT EXISTS AnalysisRun (
    run_id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at                  TEXT NOT NULL DEFAULT (datetime('now')),
    stage                   TEXT NOT NULL CHECK (stage IN (
                                'x_to_y', 'xy_to_z', 'x_to_z_baseline',
                                'xy_to_sae_cca', 'xy_to_en_cca'  -- 신규(.docs/19 Phase C)
                            )),
    lot_range               TEXT,            -- 대상 로트 집합 설명 또는 JSON 배열(TEXT 직렬화)
    correlation_matrix      TEXT,            -- JSON
    regression_coefficients TEXT,            -- JSON
    vif                     TEXT,            -- JSON
    r_squared               REAL,            -- 참고용, v2에서 정식 검증
    is_latest_for_stage     INTEGER NOT NULL DEFAULT 0 CHECK (is_latest_for_stage IN (0, 1))
);
CREATE INDEX IF NOT EXISTS idx_analysisrun_stage_latest ON AnalysisRun(stage, is_latest_for_stage);

-- =========================================================
-- Prediction
-- =========================================================
CREATE TABLE IF NOT EXISTS Prediction (
    prediction_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    lot_id          TEXT REFERENCES Lot(lot_id),      -- 수동입력 예측은 NULL 허용
    run_id          INTEGER NOT NULL REFERENCES AnalysisRun(run_id),
    target          TEXT NOT NULL CHECK (target IN ('y', 'z', 'sae_cca', 'en_cca')),  -- sae_cca/en_cca 신규(.docs/19 Phase C)
    predicted_value REAL NOT NULL,
    input_y_source  TEXT CHECK (input_y_source IN ('measured', 'predicted')),  -- target='z'일 때만 의미
    source          TEXT NOT NULL CHECK (source IN ('manual', 'batch_unmatched')),
    predicted_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_prediction_lot_id ON Prediction(lot_id);

-- =========================================================
-- SpecJudgment
-- =========================================================
CREATE TABLE IF NOT EXISTS SpecJudgment (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    lot_id               TEXT REFERENCES Lot(lot_id),
    prediction_id        INTEGER REFERENCES Prediction(prediction_id),
    target               TEXT NOT NULL CHECK (target IN ('y', 'z', 'sae_cca', 'en_cca')),
    spec_result          TEXT NOT NULL CHECK (spec_result IN ('pass', 'fail')),
    spec_thresholds_used TEXT   -- JSON
);

-- =========================================================
-- CauseDiagnosis
-- =========================================================
CREATE TABLE IF NOT EXISTS CauseDiagnosis (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    lot_id             TEXT REFERENCES Lot(lot_id),
    prediction_id      INTEGER REFERENCES Prediction(prediction_id),
    target             TEXT NOT NULL CHECK (target IN ('y', 'z', 'sae_cca', 'en_cca')),
    ranked_factors     TEXT,   -- JSON: [{factor, contribution, rank}, ...]
    recommendation_text TEXT,
    generated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- =========================================================
-- ScoringRun / ScoringResult: 검증·성공기준 채점 이력 (.docs/24, 2026-09-24)
-- 튜터 조언(.docs/23) + 사용자 확정 기준(.docs/22 §0) 반영 — 시험 매칭 로트를 대상으로
-- "예측 SPEC 판정 == 실측 SPEC 판정" 일치율을 채점한다. AnalysisRun과 달리 학습은 비영속
-- (그때그때 재학습, in-sample) 이라 이 두 테이블은 채점 실행 이력·결과 로그 전용이다.
-- =========================================================
CREATE TABLE IF NOT EXISTS ScoringRun (
    run_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at           TEXT NOT NULL DEFAULT (datetime('now')),
    target           TEXT NOT NULL CHECK (target IN ('y', 'z', 'en_cca_spec', 'sae_cca_spec')),
    threshold_pct    REAL NOT NULL,   -- "신뢰 가능" 기준 일치율(%), config/spec_thresholds.py
    error_tolerance_pct REAL,         -- 참고용 오차율 기준(%), y/z/체크포인트 값 전용(있으면)
    n_total          INTEGER NOT NULL,  -- 시험 매칭 로트 전체 건수
    n_scorable       INTEGER NOT NULL,  -- SPEC 판정 가능(spec_lower 존재 등) 건수
    n_matched        INTEGER NOT NULL,  -- 예측 판정 == 실측 판정
    n_mismatched     INTEGER NOT NULL,
    success_rate_pct REAL,             -- n_matched / n_scorable * 100, n_scorable=0이면 NULL
    reliable         INTEGER CHECK (reliable IN (0, 1))  -- success_rate_pct >= threshold_pct, 판정불가면 NULL
);

CREATE TABLE IF NOT EXISTS ScoringResult (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id                 INTEGER NOT NULL REFERENCES ScoringRun(run_id),
    lot_id                 TEXT NOT NULL REFERENCES Lot(lot_id),
    predicted_value        REAL,    -- 단일 스칼라 타깃(y/z/sae_cca_spec)만 채움. en_cca_spec은 체크포인트
    actual_value            REAL,   -- 2개(전압+지속시간) 조합 판정이라 스칼라가 아니므로 NULL로 둔다 —
    error_pct              REAL,    -- 대신 predicted_spec_result/actual_spec_result/matched로만 채점.
    predicted_spec_result  TEXT CHECK (predicted_spec_result IN ('pass', 'fail')),
    actual_spec_result     TEXT CHECK (actual_spec_result IN ('pass', 'fail')),
    matched                INTEGER CHECK (matched IN (0, 1))  -- 판정 불가면 NULL(집계 제외)
);
CREATE INDEX IF NOT EXISTS idx_scoringresult_run_id ON ScoringResult(run_id);
