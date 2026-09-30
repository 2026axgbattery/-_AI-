// FastAPI 호출 wrapper. 기본은 127.0.0.1 로컬 백엔드(.docs/02 §4)이며,
// NEXT_PUBLIC_API_BASE_URL 환경변수로 외부 배포 백엔드 주소를 지정할 수 있다
// (심사용 외부 배포 전환, .docs/37 참조 — 미설정 시 기존과 동일하게 로컬만 바라봄).
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail: unknown;
    try {
      const body: unknown = await res.json();
      // FastAPI는 에러 본문을 항상 {"detail": ...} 봉투로 감싼다 — 호출부(dashboard/prediction/
      // upload 페이지)는 전부 그 안쪽 값(문자열 또는 {missing_columns: [...]} 같은 객체)을
      // ApiError.detail로 기대하므로 여기서 한 번 벗겨내야 한다. 봉투 형태가 아니면 본문 그대로 사용.
      detail =
        body !== null && typeof body === "object" && "detail" in body
          ? (body as { detail: unknown }).detail
          : body;
    } catch {
      detail = await res.text();
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
    this.status = status;
    this.detail = detail;
  }
}

export interface UploadResult {
  file: string;
  row_count: number;
  inserted_lots?: number;
  duplicate_lot_ids?: string[];
  inserted_process_rows?: number;
  inserted_test_rows?: number;
  skipped_unknown_lot?: string[];
  /** 필수 항목 누락·model_name 파싱 실패 등으로 건너뛴 행(.docs/35 미리보기 요약에도 그대로 씀). */
  skipped_invalid_rows?: { lot_id: string | null; reason: string }[];
  /** true면 dry_run=true로 호출한 미리보기 응답 — 실제로는 아무것도 저장되지 않았다. */
  preview?: boolean;
}

export interface UploadSummary {
  total_lots: number;
  matched: number;
  unmatched: number;
  match_rate: number;
  preview_rows: Array<{
    lot_id: string;
    model_name: string;
    has_process: number;
    has_test: number;
  }>;
}

export interface ManualFieldGroup {
  model_name: string;
  prod_date?: string;
  total: number;
  missing: number;
}

export interface UploadBatch {
  batch_id: number;
  file_type: "process" | "test";
  filename: string;
  row_count: number;
  remaining_row_count: number;
  uploaded_at: string;
}

// Day 2 — ③-1/③-2 회귀 + KPI (history/15_day2-회귀-대시보드-구현-계획.md)
export interface RegressionSignificance {
  r: number | null;
  p_value: number | null;
  significant: boolean;
  n: number;
}

export interface AnalysisRunResult {
  run_id: number;
  run_at?: string;
  target: string;
  x_columns: string[];
  coefficients: Record<string, number>;
  intercept: number;
  r_squared: number;
  vif: Record<string, number | null>;
  significance: Record<string, RegressionSignificance>;
  n: number;
}

export interface KpiSummary {
  total_lots: number;
  matched_lots: number;
  match_rate: number;
  avg_retention_rate: number | null;
  avg_capacity_rate: number | null;
  en_cca_evaluated: number;
  en_cca_pass: number;
  sae_cca_evaluated: number;
  sae_cca_pass: number;
}

export interface SpecComplianceSummary {
  y_evaluated: number;
  y_fail: number;
  z_evaluated: number;
  z_fail: number;
  models_with_spec: number;
  spec_lower_y_min: number | null;
  spec_lower_y_max: number | null;
  spec_lower_z_min: number | null;
  spec_lower_z_max: number | null;
}

// Day 2 — ③-3/③-4 형명별 상세·추이
export interface ModelSummaryRow {
  model_name: string;
  rated_capacity: number;
  lot_count: number;
  avg_retention_rate: number | null;
  matched_count: number;
  avg_discharge_amount: number | null;
  avg_capacity_rate: number | null;
  sample_sufficient: boolean;
  en_cca_evaluated: number;
  en_cca_pass: number;
  sae_cca_evaluated: number;
  sae_cca_pass: number;
}

export interface ModelsSummaryResponse {
  min_sample_size: number;
  models: ModelSummaryRow[];
}

export interface TrendPoint {
  period: string;
  avg_retention_rate: number;
  n: number;
}

export interface ModelTrendResponse {
  model_name: string;
  period: string;
  points: TrendPoint[];
  available_years: string[];
}

/** EN/SAE CCA 규격(형명 무관 고정 기준, history/20) 판정 결과. result가 null이면 측정값이
 * 없어 판정 불가(불합격 아님) — note에 이유가 담긴다. */
export interface CcaSpecJudgment {
  result: "pass" | "fail" | null;
  note: string | null;
}

export interface ModelLotRow {
  lot_id: string;
  prod_date: string;
  retention_rate: number | null;
  has_test: number;
  discharge_amount: number | null;
  capacity_rate: number | null;
  sae_cca: number | null;
  en_cca: number | null;
  en_cca_10s_voltage: number | null;
  en_cca_6v_hold_sec: number | null;
  sae_cca_7v2_hold_sec: number | null;
  en_cca_spec: CcaSpecJudgment;
  sae_cca_spec: CcaSpecJudgment;
}

export interface ModelLotsResponse {
  model_name: string;
  limit: number;
  total_count: number;
  rows: ModelLotRow[];
}

// Day 3 — ④ 예측 + ⑤ SPEC 판정·원인진단 (history/17_day3-예측-spec판정-원인진단-구현계획.md)
export interface SpecJudgmentResult {
  spec_result: "pass" | "fail" | null;
  spec_lower: number | null;
  deviation: number | null;
  note: string | null;
}

export interface CauseFactor {
  factor: string;
  contribution: number;
  value: number;
  mean: number;
  deviation: number;
  recommendation: string;
  rank: number;
}

/** 실측값(예측 아님) 기준 SPEC 판정 + 원인진단 — `GET /api/models/failing-lots`(.docs/27). */
export interface FailingLotTarget {
  value: number | null;
  spec: SpecJudgmentResult;
  causes: CauseFactor[];
}

export interface FailingLotDiagnosis {
  lot_id: string;
  model_name: string;
  y: FailingLotTarget;
  z: FailingLotTarget;
}

export interface FailingLotsResponse {
  total_count: number;
  shown_count: number;
  by_model: Record<string, number>;
  y_run_available: boolean;
  z_run_available: boolean;
  lots: FailingLotDiagnosis[];
}

/** SAE/EN CCA(Z2/Z3, history/19 Phase C) 예측 블록 — 학습된 run이 없으면(표본 부족 등) available:false.
 * 판정(`spec`)은 방전량(Ah, `predicted_value`)이 아니라 EN 50342/SAE J537 체크포인트 회귀
 * (`predicted_voltage_10s`/`predicted_hold_6v_sec`/`predicted_hold_7v2_sec`) 기준이다(.docs/29) —
 * 체크포인트 회귀 표본이 부족하면 `predicted_value`만 있고 `run_id`/체크포인트 값은 없을 수 있다. */
export type CcaPredictionBlock =
  | { available: false }
  | {
      available: true;
      run_id: number | null;
      run_at?: string;
      predicted_value: number | null;
      predicted_voltage_10s?: number;
      predicted_hold_6v_sec?: number;
      predicted_hold_7v2_sec?: number;
      input_y_source: "predicted";
      spec: SpecJudgmentResult;
      causes: CauseFactor[];
    };

export interface ManualPredictResponse {
  model_name: string;
  y: {
    run_id: number;
    run_at?: string;
    predicted_value: number;
    spec: SpecJudgmentResult;
    causes: CauseFactor[];
  };
  z:
    | { available: false }
    | {
        available: true;
        run_id: number;
        run_at?: string;
        predicted_discharge_amount: number;
        predicted_capacity_rate: number | null;
        input_y_source: "predicted";
        spec: SpecJudgmentResult;
        causes: CauseFactor[];
      };
  sae_cca: CcaPredictionBlock;
  en_cca: CcaPredictionBlock;
}

export interface BatchUnmatchedResultRow {
  lot_id: string;
  model_name: string;
  /** 예측에 쓰인 최신 공정 데이터 행이 시스템에 들어온 날짜(YYYY-MM-DD) — `/upload` 업로드
   * 이력 날짜별 그룹핑과 동일 기준. "그날 넣은 데이터"를 예측 화면에서 골라 볼 때 쓴다. */
  uploaded_date: string;
  y: { predicted_value: number; spec: SpecJudgmentResult };
  z:
    | { available: false }
    | {
        available: true;
        predicted_discharge_amount: number;
        predicted_capacity_rate: number | null;
        spec: SpecJudgmentResult;
        input_y_source: "predicted";
      };
  sae_cca: CcaPredictionBlock;
  en_cca: CcaPredictionBlock;
  is_outlier: boolean;
}

export interface BatchUnmatchedResponse {
  total: number;
  y_run: { run_id: number; run_at?: string; n: number };
  z_run: { run_id: number; run_at?: string; n: number } | null;
  sae_cca_run: { run_id: number; run_at?: string; n: number } | null;
  en_cca_run: { run_id: number; run_at?: string; n: number } | null;
  results: BatchUnmatchedResultRow[];
}

export interface YVsCcaPair {
  lot_id: string;
  model_name: string;
  retention_rate: number;
  sae_cca: number | null;
  en_cca: number | null;
  en_cca_10s_voltage: number | null;
  en_cca_6v_hold_sec: number | null;
  sae_cca_7v2_hold_sec: number | null;
  en_cca_spec: CcaSpecJudgment;
  sae_cca_spec: CcaSpecJudgment;
}

// 검증·채점 모듈(history/24) — target별 "예측 SPEC 판정 == 실측 SPEC 판정" 일치율.
export type ScoringTarget = "y" | "z" | "en_cca_spec" | "sae_cca_spec";

export interface ScoringResultRow {
  lot_id: string;
  predicted_value: number | null;
  actual_value: number | null;
  error_pct: number | null;
  predicted_spec_result: "pass" | "fail" | null;
  actual_spec_result: "pass" | "fail" | null;
  matched: boolean | null;
}

export interface ScoringRunResult {
  run_id: number;
  run_at?: string;
  target: ScoringTarget;
  threshold_pct: number;
  error_tolerance_pct: number;
  n_total: number;
  n_scorable: number;
  n_matched: number;
  n_mismatched: number;
  success_rate_pct: number | null;
  reliable: boolean | null;
  note?: string | null;
  results?: ScoringResultRow[];
  mismatched_lots: ScoringResultRow[];
  /** "holdout"이면 val_n건은 train_n건 학습에 전혀 쓰이지 않은 표본으로만 채점한 것(.docs/35,
   * 2026-09-30 v2 착수) — "in_sample"(표본 부족 폴백)이면 학습에 쓴 행을 그대로 다시 채점한 것. */
  validation_mode?: "holdout" | "in_sample";
  train_n?: number;
  val_n?: number;
}

export const apiClient = {
  health: () => fetch(`${API_BASE_URL}/api/health`).then((r) => handle<{ status: string }>(r)),

  uploadProcessCsv: (file: File, opts?: { dryRun?: boolean }) => {
    const form = new FormData();
    form.append("file", file);
    const qs = opts?.dryRun ? "?dry_run=true" : "";
    return fetch(`${API_BASE_URL}/api/upload/process${qs}`, { method: "POST", body: form }).then((r) =>
      handle<UploadResult>(r)
    );
  },

  uploadTestCsv: (file: File, opts?: { dryRun?: boolean }) => {
    const form = new FormData();
    form.append("file", file);
    const qs = opts?.dryRun ? "?dry_run=true" : "";
    return fetch(`${API_BASE_URL}/api/upload/test${qs}`, { method: "POST", body: form }).then((r) =>
      handle<UploadResult>(r)
    );
  },

  getUploadSummary: () =>
    fetch(`${API_BASE_URL}/api/upload/summary`).then((r) => handle<UploadSummary>(r)),

  getManualFieldsStatus: () =>
    fetch(`${API_BASE_URL}/api/manual-fields/status`).then((r) =>
      handle<{ total_lots: number; incomplete_lot_ids: string[]; complete_lots: number }>(r)
    ),

  getManualFieldGroups: (field: string) =>
    fetch(`${API_BASE_URL}/api/manual-fields/groups?field=${encodeURIComponent(field)}`).then(
      (r) => handle<ManualFieldGroup[]>(r)
    ),

  batchUpdateManualField: (
    field: string,
    groupValues: Record<string, string>,
    value: number,
    overwrite = false
  ) =>
    fetch(`${API_BASE_URL}/api/manual-fields/batch`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ field, group_values: groupValues, value, overwrite }),
    }).then((r) => handle<{ field: string; updated_lot_ids: string[] }>(r)),

  getUploadBatches: () =>
    fetch(`${API_BASE_URL}/api/upload/batches`).then((r) => handle<UploadBatch[]>(r)),

  deleteUploadBatch: (batchId: number) =>
    fetch(`${API_BASE_URL}/api/upload/batches/${batchId}`, { method: "DELETE" }).then((r) =>
      handle<{ batch_id: number; file_type: string; orphaned_lot_count: number }>(r)
    ),

  deleteAllUploadData: () =>
    fetch(`${API_BASE_URL}/api/upload/data`, { method: "DELETE" }).then((r) =>
      handle<{ status: string }>(r)
    ),

  runXToY: () =>
    fetch(`${API_BASE_URL}/api/analysis/x-to-y`, { method: "POST" }).then((r) =>
      handle<AnalysisRunResult>(r)
    ),

  runXyToZ: () =>
    fetch(`${API_BASE_URL}/api/analysis/xy-to-z`, { method: "POST" }).then((r) =>
      handle<AnalysisRunResult>(r)
    ),

  runXToZBaseline: () =>
    fetch(`${API_BASE_URL}/api/analysis/x-to-z-baseline`, { method: "POST" }).then((r) =>
      handle<AnalysisRunResult>(r)
    ),

  getLatestAnalysis: (stage: string) =>
    fetch(`${API_BASE_URL}/api/analysis/latest?stage=${encodeURIComponent(stage)}`).then((r) =>
      handle<AnalysisRunResult | null>(r)
    ),

  runXyToSaeCca: () =>
    fetch(`${API_BASE_URL}/api/analysis/xy-to-sae-cca`, { method: "POST" }).then((r) =>
      handle<AnalysisRunResult>(r)
    ),

  runXyToEnCca: () =>
    fetch(`${API_BASE_URL}/api/analysis/xy-to-en-cca`, { method: "POST" }).then((r) =>
      handle<AnalysisRunResult>(r)
    ),

  getYVsCca: (opts?: { limit?: number; sort?: "lot_id" | "worst" }) => {
    const params = new URLSearchParams();
    if (opts?.limit !== undefined) params.set("limit", String(opts.limit));
    if (opts?.sort) params.set("sort", opts.sort);
    const qs = params.toString();
    return fetch(`${API_BASE_URL}/api/analysis/y-vs-cca${qs ? `?${qs}` : ""}`).then((r) =>
      handle<{ pairs: YVsCcaPair[]; total_count: number }>(r)
    );
  },

  getKpi: () => fetch(`${API_BASE_URL}/api/kpi`).then((r) => handle<KpiSummary>(r)),

  getSpecCompliance: () =>
    fetch(`${API_BASE_URL}/api/spec-compliance`).then((r) => handle<SpecComplianceSummary>(r)),

  getModelsSummary: () =>
    fetch(`${API_BASE_URL}/api/models/summary`).then((r) => handle<ModelsSummaryResponse>(r)),

  getModelLots: (
    modelName: string,
    opts?: { limit?: number; sort?: "recent" | "tested_first" }
  ) => {
    const params = new URLSearchParams();
    if (opts?.limit !== undefined) params.set("limit", String(opts.limit));
    if (opts?.sort) params.set("sort", opts.sort);
    const qs = params.toString();
    return fetch(
      `${API_BASE_URL}/api/models/${encodeURIComponent(modelName)}/lots${qs ? `?${qs}` : ""}`
    ).then((r) => handle<ModelLotsResponse>(r));
  },

  getFailingLots: (opts?: { modelName?: string; buyerCode?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.modelName) params.set("model_name", opts.modelName);
    if (opts?.buyerCode) params.set("buyer_code", opts.buyerCode);
    if (opts?.limit !== undefined) params.set("limit", String(opts.limit));
    const qs = params.toString();
    return fetch(`${API_BASE_URL}/api/models/failing-lots${qs ? `?${qs}` : ""}`).then((r) =>
      handle<FailingLotsResponse>(r)
    );
  },

  getModelTrend: (modelName: string, period: string) =>
    fetch(
      `${API_BASE_URL}/api/models/${encodeURIComponent(modelName)}/trend?period=${encodeURIComponent(period)}`
    ).then((r) => handle<ModelTrendResponse>(r)),

  predictManual: (modelName: string, x: Record<string, number>) =>
    fetch(`${API_BASE_URL}/api/predict/manual`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_name: modelName, x }),
    }).then((r) => handle<ManualPredictResponse>(r)),

  predictBatchUnmatched: () =>
    fetch(`${API_BASE_URL}/api/predict/batch-unmatched`, { method: "POST" }).then((r) =>
      handle<BatchUnmatchedResponse>(r)
    ),

  runScoring: (target: ScoringTarget) =>
    fetch(`${API_BASE_URL}/api/scoring/run?target=${encodeURIComponent(target)}`, {
      method: "POST",
    }).then((r) => handle<ScoringRunResult>(r)),

  getLatestScoring: (target: ScoringTarget) =>
    fetch(`${API_BASE_URL}/api/scoring/latest?target=${encodeURIComponent(target)}`).then((r) => {
      if (r.status === 404) return null;
      return handle<ScoringRunResult>(r);
    }),
};
