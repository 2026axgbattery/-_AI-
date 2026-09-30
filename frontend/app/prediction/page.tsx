"use client";

import { useEffect, useMemo, useState } from "react";
import { TopBar } from "@/components/TopBar";
import { StepFlow } from "@/components/StepFlow";
import { CausesList } from "@/components/CausesList";
import { StatusStackedBarChart } from "@/components/charts/StatusStackedBarChart";
import { extractBuyerCode } from "@/lib/buyer";
import { X_COLUMN_EXAMPLES, X_COLUMN_LABELS, X_COLUMN_ORDER, chipTone, specBadge } from "@/lib/diagnosis";
import { fmt } from "@/lib/format";
import { useCountUp } from "@/lib/useMotion";
import {
  apiClient,
  ApiError,
  type BatchUnmatchedResponse,
  type BatchUnmatchedResultRow,
  type ManualPredictResponse,
} from "@/lib/api-client";

type Tab = "manual" | "batch";
type BatchScope = "all" | "date" | "model" | "buyer";

/** Next.js App Router는 다른 화면으로 이동만 해도 이 페이지 컴포넌트를 언마운트한다 — 그래서
 * 예측 결과(순수 useState)가 페이지 이동 한 번에 사라진다. `/dashboard`의 회귀 결과와 달리 예측은
 * 서버에 "최신 결과"로 조회할 API가 없으므로(수동 시뮬레이션은 입력값 의존, 일괄 예측은 매번
 * 전체 로트를 다시 계산), 탭이 열려 있는 동안(sessionStorage, 브라우저 탭을 닫으면 사라짐)만
 * 마지막 결과를 기억해뒀다가 복귀 시 그대로 되살린다. 새로고침도 동일하게 복원되고, 데이터가
 * 바뀌었을 수 있으니 언제든 "예측 실행"을 다시 눌러 최신 상태로 갱신할 수 있다(`.docs/30`). */
const PREDICTION_SESSION_KEY = "ax_prediction_session_v1";

interface PersistedPredictionState {
  tab: Tab;
  modelName: string;
  xValues: Record<string, string>;
  manualResult: ManualPredictResponse | null;
  batchResult: BatchUnmatchedResponse | null;
  batchScope: BatchScope;
  batchScopeDate: string;
  batchScopeModel: string;
  batchScopeBuyer: string;
  batchMetric: BatchMetric;
}

/** 표에 한 번에 그리는 로트 수 상한 — 1,000건 넘는 일괄 예측도 표 렌더링이 느려지거나
 * 컬럼이 찌그러지지 않도록 이상치·부적합 우선으로 상위 건만 보여준다. */
const BATCH_TABLE_LIMIT = 200;

function batchSeverity(row: BatchUnmatchedResultRow): number {
  if (row.is_outlier) return 0;
  const specs = [
    row.y.spec.spec_result,
    row.z.available ? row.z.spec.spec_result : null,
    row.sae_cca.available ? row.sae_cca.spec.spec_result : null,
    row.en_cca.available ? row.en_cca.spec.spec_result : null,
  ];
  return specs.includes("fail") ? 1 : 2;
}


/** 직전 실행 대비 변화량 — "이 조건을 바꾸면 Y·Z가 어떻게 달라지는지"를 재실행할 때마다
 * 바로 보여주기 위한 것(2026-09-27 요청). 같은 세션 안의 바로 이전 예측과만 비교한다. */
function deltaLabel(curr: number | null | undefined, prev: number | null | undefined, digits = 1): string | null {
  if (curr == null || prev == null || Number.isNaN(curr) || Number.isNaN(prev)) return null;
  const diff = curr - prev;
  if (Math.abs(diff) < 5 * 10 ** -(digits + 1)) return "변화 없음";
  return `${diff >= 0 ? "+" : ""}${diff.toFixed(digits)}`;
}

function badgeToneLabel(tone: "pass" | "fail" | "unknown"): string {
  return tone === "pass" ? "양품" : tone === "fail" ? "부적합" : "판정불가";
}

type BatchMetric = "y" | "z" | "sae_cca" | "en_cca";

const BATCH_METRIC_LABELS: Record<BatchMetric, string> = {
  y: "Y · 포화도",
  z: "Z · 20시간 용량",
  sae_cca: "Z2 · SAE CCA",
  en_cca: "Z3 · EN CCA",
};

function metricSpecResult(row: BatchUnmatchedResultRow, metric: BatchMetric): "pass" | "fail" | null {
  if (metric === "y") return row.y.spec.spec_result;
  if (metric === "z") return row.z.available ? row.z.spec.spec_result : null;
  if (metric === "sae_cca") return row.sae_cca.available ? row.sae_cca.spec.spec_result : null;
  return row.en_cca.available ? row.en_cca.spec.spec_result : null;
}

interface GroupBar {
  key: string;
  count: number;
  pass: number;
  fail: number;
  unknown: number;
}

/** 로트 배열을 형명/바이어/날짜 등 그룹키로 묶어 선택된 지표(Y/Z/Z2/Z3)의 양품·부적합·판정불가
 * 건수를 집계 — 그래프 막대 하나가 그룹 하나에 대응한다. 기본 정렬은 부적합이 많은 그룹이
 * 먼저 보이도록 해 문제 있는 형명/바이어를 한눈에 찾게 하지만, 날짜처럼 최신순이 더 자연스러운
 * 그룹은 `sort`로 재정렬한다. */
function buildGroupBars(
  rows: BatchUnmatchedResultRow[],
  keyFn: (row: BatchUnmatchedResultRow) => string | null,
  metric: BatchMetric,
  sort: (a: GroupBar, b: GroupBar) => number = (a, b) => b.fail - a.fail || b.count - a.count
): GroupBar[] {
  const map = new Map<string, GroupBar>();
  for (const row of rows) {
    const key = keyFn(row);
    if (!key) continue;
    let g = map.get(key);
    if (!g) {
      g = { key, count: 0, pass: 0, fail: 0, unknown: 0 };
      map.set(key, g);
    }
    g.count++;
    const result = metricSpecResult(row, metric);
    if (result === "pass") g.pass++;
    else if (result === "fail") g.fail++;
    else g.unknown++;
  }
  return [...map.values()].sort(sort);
}

/** 형명별/바이어별/날짜별 판정 분포를 막대(양품=그린/부적합=오렌지/판정불가=그레이) 하나당
 * 그룹 하나로 시각화한다. 막대를 클릭하면 그 그룹으로 아래 표를 드릴다운한다. 실제 막대 렌더링은
 * Recharts 기반 `StatusStackedBarChart`가 담당(2026-09-27, `.docs/33`) — 이 함수는 범례·빈
 * 상태 안내를 둘러싼 래퍼만 유지한다. */
function GroupBarChart({
  bars,
  selectedKey,
  onSelect,
  emptyHint,
  todayKey,
}: {
  bars: GroupBar[];
  selectedKey: string;
  onSelect: (key: string) => void;
  emptyHint: string;
  todayKey?: string;
}) {
  if (bars.length === 0) {
    return <div style={{ fontSize: "0.8125rem", color: "var(--color-text-secondary)" }}>{emptyHint}</div>;
  }
  return (
    <div className="batch-chart">
      <div className="batch-chart-legend">
        <span>
          <span className="batch-chart-dot" style={{ background: "var(--sebang-green-700)" }} />양품
        </span>
        <span>
          <span className="batch-chart-dot" style={{ background: "var(--sebang-orange)" }} />부적합
        </span>
        <span>
          <span className="batch-chart-dot" style={{ background: "var(--sebang-gray-400)" }} />판정불가
        </span>
      </div>
      <StatusStackedBarChart bars={bars} selectedKey={selectedKey} onSelect={onSelect} todayKey={todayKey} />
    </div>
  );
}

interface BatchSummary {
  count: number;
  yPass: number;
  yFail: number;
  zPass: number;
  zFail: number;
  saePass: number;
  saeFail: number;
  enPass: number;
  enFail: number;
}

/** 선택 범위(로트별/날짜별/형명별/바이어별)로 필터링된 로트들의 판정 건수 집계 — 새 예측 호출
 * 없이 이미 받아온 `batchResult.results`만으로 계산한다(history/28, `.docs/07` 2026-09-25/26). */
function summarizeBatch(rows: BatchUnmatchedResultRow[]): BatchSummary {
  const s: BatchSummary = { count: rows.length, yPass: 0, yFail: 0, zPass: 0, zFail: 0, saePass: 0, saeFail: 0, enPass: 0, enFail: 0 };
  for (const r of rows) {
    if (r.y.spec.spec_result === "pass") s.yPass++;
    else if (r.y.spec.spec_result === "fail") s.yFail++;
    if (r.z.available) {
      if (r.z.spec.spec_result === "pass") s.zPass++;
      else if (r.z.spec.spec_result === "fail") s.zFail++;
    }
    if (r.sae_cca.available) {
      if (r.sae_cca.spec.spec_result === "pass") s.saePass++;
      else if (r.sae_cca.spec.spec_result === "fail") s.saeFail++;
    }
    if (r.en_cca.available) {
      if (r.en_cca.spec.spec_result === "pass") s.enPass++;
      else if (r.en_cca.spec.spec_result === "fail") s.enFail++;
    }
  }
  return s;
}

function buildVerdict(result: ManualPredictResponse): {
  headline: string;
  desc: string;
  tone: "pass" | "fail" | "unknown";
} {
  const ySpec = result.y.spec;
  const zSpec = result.z.available ? result.z.spec : null;
  const saeSpec = result.sae_cca.available ? result.sae_cca.spec : null;
  const enSpec = result.en_cca.available ? result.en_cca.spec : null;
  // Y·Z뿐 아니라 SAE/EN CCA도 이 화면에 verdict-card로 나란히 표시되므로, 종합 결론(히어로 배너)도
  // 넷 다 반영해야 한다 — Y·Z는 양품인데 CCA만 부적합인 조건에서 배너가 "양품"이라고 잘못 말하면
  // 바로 아래 카드와 모순되는 화면이 된다.
  const results = [ySpec.spec_result, zSpec?.spec_result, saeSpec?.spec_result, enSpec?.spec_result].filter(
    (v) => v !== undefined
  );
  const anyFail = results.includes("fail");
  const anyConfigured = results.some((v) => v !== null && v !== undefined);
  const ccaFailed = saeSpec?.spec_result === "fail" || enSpec?.spec_result === "fail";
  const yzFailed = ySpec.spec_result === "fail" || zSpec?.spec_result === "fail";

  if (anyFail) {
    return {
      headline: `이 조건(${result.model_name})의 예측 판정: 부적합 — SPEC 미달 예상`,
      desc: `예측 포화도(Y) ${fmt(result.y.predicted_value)}%${
        result.z.available ? `, 20시간 용량(Z) ${fmt(result.z.predicted_capacity_rate)}%` : ""
      }${yzFailed ? "" : " (SPEC 충족)"}${
        ccaFailed ? ", SAE/EN CCA(저온시동전류) 판정" : ""
      } 중 하나 이상이 SPEC 하한을 밑돌 것으로 예측됩니다. 아래에서 근거와 원인 인자를 확인하세요.`,
      tone: "fail",
    };
  }
  if (!anyConfigured) {
    return {
      headline: "이 조건으로는 판정할 수 없습니다",
      desc: "예측값 자체를 계산할 수 없어(예: 모델명에서 정격용량을 읽을 수 없음) 양품/부적합을 가릴 수 없습니다. 모델명·입력값을 확인하고 다시 시도하세요.",
      tone: "unknown",
    };
  }
  return {
    headline: `이 조건(${result.model_name})의 예측 판정: 양품 — SPEC 충족 예상`,
    desc: `예측 포화도(Y) ${fmt(result.y.predicted_value)}%${
      result.z.available ? `, 20시간 용량(Z) ${fmt(result.z.predicted_capacity_rate)}%` : ""
    }${saeSpec || enSpec ? ", SAE/EN CCA(저온시동전류)" : ""} 모두 SPEC 하한을 충족할 것으로 예측됩니다.`,
    tone: "pass",
  };
}

export default function PredictionPage() {
  const [tab, setTab] = useState<Tab>("manual");

  const [modelName, setModelName] = useState("AGM90_S1");
  const [xValues, setXValues] = useState<Record<string, string>>({});
  const [manualResult, setManualResult] = useState<ManualPredictResponse | null>(null);
  // 바로 이전 실행 결과 — "조건을 바꾸면 Y·Z가 어떻게 달라지는지"를 재실행할 때마다 델타로
  // 보여주기 위함(세션 복원 대상 아님, 새로고침하면 초기화돼도 무방한 보조 정보).
  const [previousManualResult, setPreviousManualResult] = useState<ManualPredictResponse | null>(null);
  const [manualError, setManualError] = useState<string | null>(null);
  const [manualLoading, setManualLoading] = useState(false);

  const [batchResult, setBatchResult] = useState<BatchUnmatchedResponse | null>(null);
  const [batchError, setBatchError] = useState<string | null>(null);
  const [batchLoading, setBatchLoading] = useState(false);
  const [batchScope, setBatchScope] = useState<BatchScope>("all");
  const [batchScopeDate, setBatchScopeDate] = useState<string>("");
  const [batchScopeModel, setBatchScopeModel] = useState<string>("");
  const [batchScopeBuyer, setBatchScopeBuyer] = useState<string>("");
  const [batchMetric, setBatchMetric] = useState<BatchMetric>("y");
  const [sessionHydrated, setSessionHydrated] = useState(false);
  // 지금 보이는 결과가 이번에 새로 계산한 게 아니라 세션에서 복원된 이전 결과인지 — 데이터가 그
  // 사이 바뀌었을 수 있으니 화면에 "복원됨" 안내를 보여줘 다시 실행을 유도한다.
  const [manualRestored, setManualRestored] = useState(false);
  const [batchRestored, setBatchRestored] = useState(false);

  // 마운트 시 1회, 이전에 저장해둔 결과가 있으면 복원한다. 서버 렌더링에는 `sessionStorage`가
  // 없으므로 반드시 effect 안에서만 접근한다(초기 state 값에서 바로 읽으면 정적 프리렌더 자체가
  // 깨진다). 프라이빗 브라우징 등에서 접근 자체가 막혀 있어도 조용히 무시하고 기본값으로 진행한다.
  // `queueMicrotask`로 한 단계 미루는 이유: effect 본문에서 setState를 바로 여러 번 부르면
  // `react-hooks/set-state-in-effect` 린트가 "연쇄 렌더링" 경고를 낸다 — 마이크로태스크 콜백
  // 안으로 옮기면(다른 곳의 `.then()` 콜백과 동일한 패턴) 즉시 실행되면서도 이 경고를 피한다.
  useEffect(() => {
    queueMicrotask(() => {
      try {
        const raw = sessionStorage.getItem(PREDICTION_SESSION_KEY);
        if (raw) {
          const saved: Partial<PersistedPredictionState> = JSON.parse(raw);
          if (saved.tab) setTab(saved.tab);
          if (saved.modelName) setModelName(saved.modelName);
          if (saved.xValues) setXValues(saved.xValues);
          if (saved.manualResult) {
            setManualResult(saved.manualResult);
            setManualRestored(true);
          }
          if (saved.batchResult) {
            setBatchResult(saved.batchResult);
            setBatchRestored(true);
          }
          if (saved.batchScope) setBatchScope(saved.batchScope);
          if (saved.batchScopeDate) setBatchScopeDate(saved.batchScopeDate);
          if (saved.batchScopeModel) setBatchScopeModel(saved.batchScopeModel);
          if (saved.batchScopeBuyer) setBatchScopeBuyer(saved.batchScopeBuyer);
          if (saved.batchMetric) setBatchMetric(saved.batchMetric);
        }
      } catch {
        // 저장된 값을 읽을 수 없어도(손상된 JSON, 접근 차단 등) 기본값으로 계속 진행.
      } finally {
        setSessionHydrated(true);
      }
    });
  }, []);

  // 복원이 끝난 뒤부터만 저장한다 — 복원 직전(기본값 상태)에 먼저 저장이 실행되면 방금 있던
  // 이전 결과를 기본값으로 덮어써버릴 수 있다.
  useEffect(() => {
    if (!sessionHydrated) return;
    try {
      const toSave: PersistedPredictionState = {
        tab, modelName, xValues, manualResult, batchResult,
        batchScope, batchScopeDate, batchScopeModel, batchScopeBuyer, batchMetric,
      };
      sessionStorage.setItem(PREDICTION_SESSION_KEY, JSON.stringify(toSave));
    } catch {
      // 용량 초과(특히 일괄 예측 결과가 아주 클 때) 등으로 저장에 실패해도 무시 — 세션 유지는
      // 편의 기능일 뿐이라, 이 경우엔 "예측 실행"을 다시 눌러 새로 계산하면 된다.
    }
  }, [
    sessionHydrated, tab, modelName, xValues, manualResult, batchResult,
    batchScope, batchScopeDate, batchScopeModel, batchScopeBuyer, batchMetric,
  ]);

  const todayStr = useMemo(() => new Date().toISOString().slice(0, 10), []);

  const batchBuyers = useMemo(() => {
    if (!batchResult) return [];
    const set = new Set<string>();
    for (const r of batchResult.results) {
      const b = extractBuyerCode(r.model_name);
      if (b) set.add(b);
    }
    return [...set].sort();
  }, [batchResult]);

  // 날짜 그룹은 부적합 우선이 아니라 최신순(오늘이 맨 위)으로 정렬 —
  // "그날 넣은 데이터"를 확인하는 용도라 시간순이 더 자연스럽다.
  const dateGroupBars = useMemo(
    () =>
      batchResult
        ? buildGroupBars(batchResult.results, (r) => r.uploaded_date, batchMetric, (a, b) => b.key.localeCompare(a.key))
        : [],
    [batchResult, batchMetric]
  );
  const modelGroupBars = useMemo(
    () => (batchResult ? buildGroupBars(batchResult.results, (r) => r.model_name, batchMetric) : []),
    [batchResult, batchMetric]
  );
  const buyerGroupBars = useMemo(
    () => (batchResult ? buildGroupBars(batchResult.results, (r) => extractBuyerCode(r.model_name), batchMetric) : []),
    [batchResult, batchMetric]
  );

  const activeGroup = {
    date: { label: "날짜", bars: dateGroupBars, selected: batchScopeDate, setSelected: setBatchScopeDate },
    model: { label: "형명", bars: modelGroupBars, selected: batchScopeModel, setSelected: setBatchScopeModel },
    buyer: { label: "바이어", bars: buyerGroupBars, selected: batchScopeBuyer, setSelected: setBatchScopeBuyer },
  }[batchScope === "all" ? "model" : batchScope];

  // 날짜별/형명별/바이어별 뷰는 그래프에서 그룹을 클릭하기 전까지 로트 표를 드릴다운하지 않는다
  // (선택 전에는 그래프만으로 전체 분포를 먼저 파악하게 한다).
  const showBatchDrilldown = batchScope === "all" || activeGroup.selected !== "";

  const scopedBatchRows = useMemo(() => {
    if (!batchResult) return [];
    if (batchScope === "date") {
      return batchScopeDate ? batchResult.results.filter((r) => r.uploaded_date === batchScopeDate) : [];
    }
    if (batchScope === "model") {
      return batchScopeModel ? batchResult.results.filter((r) => r.model_name === batchScopeModel) : [];
    }
    if (batchScope === "buyer") {
      return batchScopeBuyer
        ? batchResult.results.filter((r) => extractBuyerCode(r.model_name) === batchScopeBuyer)
        : [];
    }
    return batchResult.results;
  }, [batchResult, batchScope, batchScopeDate, batchScopeModel, batchScopeBuyer]);

  const batchSummary = useMemo(() => summarizeBatch(scopedBatchRows), [scopedBatchRows]);

  // `batchResult.sae_cca_run`/`en_cca_run`은 방전량(Ah) 회귀 실행 여부만 알려준다 — 실제 판정은
  // 요청마다 자동 재학습되는 체크포인트 회귀(전압10초/6.0V·7.2V 지속시간) 기준이라, Ah 회귀가
  // 한 번도 안 돌았어도(대시보드 "CCA 회귀 시도" 버튼 클릭 전) 체크포인트 표본만 충분하면 로트별
  // 판정이 이미 나와 있을 수 있다. 그 경우까지 "이번 예측에 포함되지 않았다"고 안내하면 바로 아래
  // 표(실제 판정이 나와 있는)와 모순되므로, 실제로 행에 값이 하나도 없을 때만 안내 배너를 띄운다.
  const anyCcaAvailable = useMemo(
    () => (batchResult ? batchResult.results.some((r) => r.sae_cca.available || r.en_cca.available) : false),
    [batchResult]
  );

  const visibleBatchRows = useMemo(
    () => [...scopedBatchRows].sort((a, b) => batchSeverity(a) - batchSeverity(b)).slice(0, BATCH_TABLE_LIMIT),
    [scopedBatchRows]
  );

  /** 처음 여는 사람은 9개 입력 칸이 전부 비어 있으면 뭘 넣어야 할지 감이 안 잡힌다 — 대표
   * 예시값을 한 번에 채워 일단 결과부터 보고, 그다음 값을 하나씩 바꿔가며 Y·Z가 어떻게
   * 달라지는지 확인하는 흐름을 유도한다(2026-09-27 요청). */
  function handleFillExample() {
    const next: Record<string, string> = {};
    for (const col of X_COLUMN_ORDER) {
      next[col] = String(X_COLUMN_EXAMPLES[col]);
    }
    setXValues(next);
  }

  async function handleManualSubmit() {
    const prevResult = manualResult;
    setManualLoading(true);
    setManualError(null);
    setManualResult(null);
    try {
      const x: Record<string, number> = {};
      for (const col of X_COLUMN_ORDER) {
        const raw = xValues[col];
        if (!raw) {
          setManualError(`${X_COLUMN_LABELS[col]} 값을 입력하세요.`);
          setManualLoading(false);
          return;
        }
        const parsed = parseFloat(raw);
        if (Number.isNaN(parsed)) {
          setManualError(`${X_COLUMN_LABELS[col]} 값이 숫자가 아닙니다: "${raw}"`);
          setManualLoading(false);
          return;
        }
        x[col] = parsed;
      }
      const result = await apiClient.predictManual(modelName, x);
      setPreviousManualResult(prevResult);
      setManualResult(result);
      setManualRestored(false);
    } catch (err) {
      setManualError(
        err instanceof ApiError
          ? typeof err.detail === "string"
            ? err.detail
            : JSON.stringify(err.detail)
          : "예측 실행 중 오류가 발생했습니다."
      );
    } finally {
      setManualLoading(false);
    }
  }

  async function handleBatchRun() {
    setBatchLoading(true);
    setBatchError(null);
    try {
      const result = await apiClient.predictBatchUnmatched();
      setBatchResult(result);
      setBatchRestored(false);
    } catch (err) {
      setBatchError(
        err instanceof ApiError
          ? typeof err.detail === "string"
            ? err.detail
            : JSON.stringify(err.detail)
          : "일괄 예측 실행 중 오류가 발생했습니다."
      );
    } finally {
      setBatchLoading(false);
    }
  }

  const verdict = manualResult ? buildVerdict(manualResult) : null;
  // 아래 verdict-card 4개가 각자 specBadge(...)를 2~3번씩 다시 호출하던 것을 방지 — 한 번만
  // 계산해 재사용한다(배치 예측 표의 yBadge/zBadge 계산 패턴과 동일).
  const yBadge = manualResult ? specBadge(manualResult.y.spec) : null;
  const zBadge = manualResult?.z.available ? specBadge(manualResult.z.spec) : null;
  const saeBadge = manualResult?.sae_cca.available ? specBadge(manualResult.sae_cca.spec) : null;
  const enBadge = manualResult?.en_cca.available ? specBadge(manualResult.en_cca.spec) : null;
  // 예측 실행마다 결과 숫자가 0에서 실제 값까지 올라가는 카운트업 임팩트(.docs/35) — 4개
  // verdict-card 모두 같은 컴포넌트 안에서 바로 렌더링되므로(별도 .map 콜백이 아님) 훅을
  // 컴포넌트 최상단에서 조건 없이 호출해도 안전하다.
  const yCountUp = useCountUp(manualResult?.y.predicted_value ?? null);
  const zCountUp = useCountUp(manualResult?.z.available ? manualResult.z.predicted_capacity_rate : null);
  const saeCountUp = useCountUp(manualResult?.sae_cca.available ? manualResult.sae_cca.predicted_value : null);
  const enCountUp = useCountUp(manualResult?.en_cca.available ? manualResult.en_cca.predicted_value : null);
  const yDelta =
    manualResult && previousManualResult
      ? deltaLabel(manualResult.y.predicted_value, previousManualResult.y.predicted_value)
      : null;
  const currZ = manualResult?.z;
  const prevZ = previousManualResult?.z;
  const zDelta =
    currZ?.available && prevZ?.available
      ? deltaLabel(currZ.predicted_capacity_rate, prevZ.predicted_capacity_rate)
      : null;
  const currSae = manualResult?.sae_cca;
  const prevSae = previousManualResult?.sae_cca;
  const saeDelta =
    currSae?.available && prevSae?.available
      ? deltaLabel(currSae.predicted_value, prevSae.predicted_value, 3)
      : null;
  const currEn = manualResult?.en_cca;
  const prevEn = previousManualResult?.en_cca;
  const enDelta =
    currEn?.available && prevEn?.available
      ? deltaLabel(currEn.predicted_value, prevEn.predicted_value, 3)
      : null;

  return (
    <div className="app">
      <TopBar active="예측" />

      <StepFlow current="prediction" />

      <div className="page-head">
        <div>
          <h1>포화도(Y) · 20시간 용량(Z) · CCA 예측</h1>
          <p>
            공정인자(X)만 입력하면 1단(X→Y)에서 포화도를, 2단(X+Y→Z, X+Y→CCA)에서 20시간 용량과
            저온시동전류(SAE/EN CCA)까지 연달아 예측합니다. 시험 미실시 로트도 동일하게 일괄
            산출할 수 있습니다.
          </p>
        </div>
      </div>

      <div className="tabs">
        <button className={`tab${tab === "manual" ? " active" : ""}`} onClick={() => setTab("manual")}>
          조건을 바꾸면 결과가 어떻게 될까?
        </button>
        <button className={`tab${tab === "batch" ? " active" : ""}`} onClick={() => setTab("batch")}>
          시험 전 로트는 지금 어떨까?
        </button>
      </div>

      {tab === "manual" && (
        <>
          <div className="alert">
            <span>ℹ️</span>
            <div>
              공정 조건(X) 하나를 바꿔보고 그 결과 포화도(Y)·20시간 용량(Z)·CCA가 어떻게 달라지는지
              바로 확인하는 <b>선택적 시뮬레이션 도구</b>입니다(실제 로트를 위한 필수 입력 화면이
              아닙니다). 처음이라 값 감이 안 잡히면 아래 <b>&ldquo;예시값으로 채우기&rdquo;</b>를 눌러
              결과부터 먼저 보고, 값을 하나씩 바꿔가며 재실행해 보세요 — 바뀐 조건과 이전 예측의
              차이를 결과 카드에 바로 같이 보여줍니다. 실제 미매칭 로트에 대한 예측은{" "}
              <b>옆 탭</b>에서 업로드된 데이터로 자동 계산됩니다.
            </div>
          </div>

          {verdict && (
            <>
              {manualRestored && (
                <div className="vif-note align-start" style={{ marginBottom: "var(--space-4)" }}>
                  ⏱ 이전에 실행했던 예측 결과가 복원됐습니다(다른 화면으로 이동했다가 돌아온 경우
                  포함). 그 사이 데이터가 바뀌었을 수 있으니, 최신 상태가 필요하면 아래에서 조건을
                  확인하고 &ldquo;1단→2단 순차 예측 실행&rdquo;을 다시 눌러주세요.
                </div>
              )}
              <div className="hero-verdict">
                <div className="hero-watermark">EB</div>
                <div className="hero-icon">
                  {verdict.tone === "fail" ? "⚠️" : verdict.tone === "pass" ? "✅" : "❔"}
                </div>
                <div className="hero-body">
                  <div className="hero-eyebrow-row">
                    <span className="hero-eyebrow">종합 결론</span>
                    <span className={`status-chip ${chipTone(verdict.tone)}`}>
                      {verdict.tone === "fail" ? "확인 필요" : verdict.tone === "pass" ? "정상" : "판정 불가"}
                    </span>
                  </div>
                  <div className="hero-title">{verdict.headline}</div>
                  <div className="hero-desc">{verdict.desc}</div>
                </div>
              </div>

              <div className="verdict-row">
                <div className={`verdict-card status-${yBadge!.tone}`}>
                  <span className="stage-tag">1단 · X → Y</span>
                  <div className="vc-title">예측 포화도 (잔존율 proxy)</div>
                  <div className="vc-main">
                    <span className="vc-value">{fmt(yCountUp)}%</span>
                    <span className={`status-chip ${chipTone(yBadge!.tone)}`}>
                      {yBadge!.label}
                    </span>
                  </div>
                  {manualResult!.y.spec.spec_lower !== null && (
                    <div className="vc-sub">
                      SPEC 하한 <b>{fmt(manualResult!.y.spec.spec_lower)}%</b> 대비{" "}
                      <b>{manualResult!.y.spec.deviation! >= 0 ? "+" : ""}{fmt(manualResult!.y.spec.deviation)}%p</b>
                    </div>
                  )}
                  {yDelta && (
                    <div className="vc-sub vc-delta">
                      이전 예측 대비 {yDelta}
                      {yDelta !== "변화 없음" ? "%p" : ""}
                    </div>
                  )}
                </div>
                <div className={`verdict-card status-${zBadge?.tone ?? "unknown"}`}>
                  <span className="stage-tag">2단 · X + Ŷ → Z</span>
                  <div className="vc-title">예측 20시간 용량 (capacity_rate)</div>
                  <div className="vc-main">
                    {manualResult!.z.available ? (
                      <>
                        <span className="vc-value">{fmt(zCountUp)}%</span>
                        <span className={`status-chip ${chipTone(zBadge!.tone)}`}>
                          {zBadge!.label}
                        </span>
                      </>
                    ) : (
                      <span className="vc-value" style={{ fontSize: "1rem" }}>
                        2단 모델 미학습 — 대시보드에서 실행 필요
                      </span>
                    )}
                  </div>
                  {manualResult!.z.available && (
                    <div className="vc-sub">
                      방전량 {fmt(manualResult!.z.predicted_discharge_amount, 2)}Ah · ⚠ 실측 Y가 아닌
                      1단 예측값(Ŷ)으로 산출됨(input_y_source: predicted)
                    </div>
                  )}
                  {zDelta && (
                    <div className="vc-sub vc-delta">
                      이전 예측 대비 {zDelta}
                      {zDelta !== "변화 없음" ? "%p" : ""}
                    </div>
                  )}
                </div>
              </div>

              <div className="verdict-row">
                <div className={`verdict-card status-${saeBadge?.tone ?? "unknown"}`}>
                  <span className="stage-tag">2단 · X + Ŷ → SAE CCA</span>
                  <div className="vc-title">예측 SAE CCA (저온시동전류, Ah)</div>
                  <div className="vc-main">
                    {manualResult!.sae_cca.available ? (
                      <>
                        <span className="vc-value">
                          {manualResult!.sae_cca.predicted_value !== null ? `${fmt(saeCountUp, 3)}Ah` : "—"}
                        </span>
                        <span className={`status-chip ${chipTone(saeBadge!.tone)}`}>
                          {saeBadge!.label}
                        </span>
                      </>
                    ) : (
                      <span className="vc-value" style={{ fontSize: "1rem" }}>
                        모델 미학습 — 신뢰성 시험 표본 부족(표본 2건, 최소 11건 필요)
                      </span>
                    )}
                  </div>
                  {manualResult!.sae_cca.available && manualResult!.sae_cca.predicted_hold_7v2_sec !== undefined && (
                    <div className="vc-sub">
                      판정 기준(SAE J537): 7.2V까지 지속시간 예측 {fmt(manualResult!.sae_cca.predicted_hold_7v2_sec, 1)}초
                      (합격 기준 ≥30초) — 방전량(Ah)이 아니라 이 체크포인트로 합격 여부를 가립니다.
                    </div>
                  )}
                  {saeDelta && (
                    <div className="vc-sub vc-delta">이전 예측 대비 {saeDelta}{saeDelta !== "변화 없음" ? "Ah" : ""}</div>
                  )}
                </div>
                <div className={`verdict-card status-${enBadge?.tone ?? "unknown"}`}>
                  <span className="stage-tag">2단 · X + Ŷ → EN CCA</span>
                  <div className="vc-title">예측 EN CCA (저온시동전류, Ah)</div>
                  <div className="vc-main">
                    {manualResult!.en_cca.available ? (
                      <>
                        <span className="vc-value">
                          {manualResult!.en_cca.predicted_value !== null ? `${fmt(enCountUp, 3)}Ah` : "—"}
                        </span>
                        <span className={`status-chip ${chipTone(enBadge!.tone)}`}>
                          {enBadge!.label}
                        </span>
                      </>
                    ) : (
                      <span className="vc-value" style={{ fontSize: "1rem" }}>
                        모델 미학습 — 신뢰성 시험 표본 부족(표본 2건, 최소 11건 필요)
                      </span>
                    )}
                  </div>
                  {manualResult!.en_cca.available && manualResult!.en_cca.predicted_voltage_10s !== undefined && (
                    <div className="vc-sub">
                      판정 기준(EN 50342): 10초 전압 예측 {fmt(manualResult!.en_cca.predicted_voltage_10s, 2)}V(≥7.5V)
                      · 6.0V까지 지속시간 예측 {fmt(manualResult!.en_cca.predicted_hold_6v_sec, 1)}초(≥90초) — 방전량(Ah)이
                      아니라 이 체크포인트 2개로 합격 여부를 가립니다.
                    </div>
                  )}
                  {enDelta && (
                    <div className="vc-sub vc-delta">이전 예측 대비 {enDelta}{enDelta !== "변화 없음" ? "Ah" : ""}</div>
                  )}
                </div>
              </div>
            </>
          )}

          <details className="evidence" open>
            <summary>
              <span className="summary-tag">근거</span> 입력 조건 · 예측 세부 결과 · 원인 인자
              <span className="summary-hint">조건을 바꿔 재예측해 보세요</span>
            </summary>
            <div className="evidence-body">
              <div className="grid-2">
                <div className="card">
                  <div className="card-head">
                    <h3>조건 입력 (X)</h3>
                    <button type="button" className="raw-data-toggle" onClick={handleFillExample}>
                      예시값으로 채우기
                    </button>
                  </div>
                  <div className="form-grid">
                    <div className="field field-full" style={{ gridColumn: "1 / -1" }}>
                      <label>모델명 (model_name)</label>
                      <input
                        type="text"
                        value={modelName}
                        onChange={(e) => setModelName(e.target.value)}
                        placeholder="예: AGM90_S1"
                      />
                    </div>
                    {X_COLUMN_ORDER.map((col) => (
                      <div className="field" key={col}>
                        <label>{X_COLUMN_LABELS[col]}</label>
                        <input
                          type="text"
                          value={xValues[col] ?? ""}
                          onChange={(e) => setXValues((prev) => ({ ...prev, [col]: e.target.value }))}
                          placeholder={`예: ${X_COLUMN_EXAMPLES[col]}`}
                        />
                      </div>
                    ))}
                  </div>
                  {manualError && <div className="alert warn">{manualError}</div>}
                  <button
                    className="btn btn-primary"
                    style={{ width: "100%", justifyContent: "center" }}
                    onClick={handleManualSubmit}
                    disabled={manualLoading}
                  >
                    {manualLoading ? "예측 실행 중..." : "1단→2단 순차 예측 실행"}
                  </button>
                </div>

                <div className="card">
                  <div className="card-head">
                    <h3>원인 인자 (SPEC 미달 시)</h3>
                    <span className="hint">계수 × 훈련 평균 대비 편차, 상위 3개</span>
                  </div>
                  {!manualResult && (
                    <div style={{ fontSize: "0.8125rem", color: "var(--color-text-secondary)" }}>
                      왼쪽에서 조건을 입력하고 예측을 실행하세요.
                    </div>
                  )}
                  {manualResult && manualResult.y.causes.length === 0 && manualResult.y.spec.spec_result !== "fail" && (
                    <div style={{ fontSize: "0.8125rem", color: "var(--color-text-secondary)" }}>
                      Y가 부적합으로 판정된 경우에만 원인 인자를 계산합니다.
                    </div>
                  )}
                  {manualResult && manualResult.y.causes.length > 0 && (
                    <>
                      <div className="card-head" style={{ marginBottom: "var(--space-2)" }}>
                        <span className="hint">Y(포화도) 원인 인자</span>
                      </div>
                      <CausesList causes={manualResult.y.causes} />
                    </>
                  )}
                  {manualResult?.z.available && manualResult.z.causes.length > 0 && (
                    <>
                      <div className="card-head" style={{ marginTop: "var(--space-4)", marginBottom: "var(--space-2)" }}>
                        <span className="hint">Z(20시간 용량) 원인 인자</span>
                      </div>
                      <CausesList causes={manualResult.z.causes} />
                    </>
                  )}
                  {manualResult?.sae_cca.available && manualResult.sae_cca.causes.length > 0 && (
                    <>
                      <div className="card-head" style={{ marginTop: "var(--space-4)", marginBottom: "var(--space-2)" }}>
                        <span className="hint">SAE CCA 원인 인자</span>
                      </div>
                      <CausesList causes={manualResult.sae_cca.causes} />
                    </>
                  )}
                  {manualResult?.en_cca.available && manualResult.en_cca.causes.length > 0 && (
                    <>
                      <div className="card-head" style={{ marginTop: "var(--space-4)", marginBottom: "var(--space-2)" }}>
                        <span className="hint">EN CCA 원인 인자</span>
                      </div>
                      <CausesList causes={manualResult.en_cca.causes} />
                    </>
                  )}
                </div>
              </div>
            </div>
          </details>
        </>
      )}

      {tab === "batch" && (
        <>
          <div className="alert">
            <span>ℹ️</span>
            <div>
              시험과 매칭되지 않은 로트(공정 데이터만 있고 시험 미실시) 전체에 대해 1단(Y)→2단(Z,
              SAE/EN CCA)을 순차 실행합니다. CCA는 신뢰성 시험 표본이 쌓여 회귀가 학습된 경우에만
              같이 예측됩니다(미학습 시 아래에 안내). 수기입력(전해액온도·충전량·수조온도)이 모두
              채워진 로트만 대상입니다. 예측 후에는 <b>로트별·날짜별·형명별·바이어별</b>로 나눠 그래프로
              확인할 수 있습니다 — 날짜별은 공정 데이터가 시스템에 들어온 날짜(업로드일) 기준이라,
              오늘 새로 넣은 데이터만 골라 예측 결과를 바로 확인할 수 있습니다.
            </div>
          </div>

          <button className="btn btn-primary" onClick={handleBatchRun} disabled={batchLoading}>
            {batchLoading ? "예측 실행 중..." : "미매칭 로트 Y·Z·CCA 예측 실행"}
          </button>

          {batchError && <div className="alert warn" style={{ marginTop: "var(--space-4)" }}>{batchError}</div>}

          {batchRestored && batchResult && (
            <div className="vif-note align-start" style={{ marginTop: "var(--space-4)" }}>
              ⏱ 이전에 실행했던 예측 결과가 복원됐습니다(다른 화면으로 이동했다가 돌아온 경우
              포함). 그 사이 데이터가 바뀌었을 수 있으니, 최신 상태가 필요하면 위 &ldquo;미매칭 로트
              Y·Z·CCA 예측 실행&rdquo;을 다시 눌러주세요.
            </div>
          )}

          {batchResult && (
            <div className="card" style={{ marginTop: "var(--space-5)" }}>
              <div className="card-head">
                <h3>미매칭 로트 Y·Z·CCA 예측 결과</h3>
                <span className="pill-count">{batchResult.total}건</span>
              </div>
              {batchResult.total > 0 && (
                <div className="period-tabs">
                  <button
                    className={`period-tab${batchScope === "all" ? " active" : ""}`}
                    onClick={() => setBatchScope("all")}
                  >
                    로트별
                  </button>
                  <button
                    className={`period-tab${batchScope === "date" ? " active" : ""}`}
                    onClick={() => setBatchScope("date")}
                  >
                    날짜별
                  </button>
                  <button
                    className={`period-tab${batchScope === "model" ? " active" : ""}`}
                    onClick={() => setBatchScope("model")}
                  >
                    형명별
                  </button>
                  <button
                    className={`period-tab${batchScope === "buyer" ? " active" : ""}`}
                    onClick={() => setBatchScope("buyer")}
                    disabled={batchBuyers.length === 0}
                  >
                    바이어별
                  </button>
                </div>
              )}

              {batchResult.total > 0 && batchScope !== "all" && (
                <>
                  <div className="batch-metric-tabs">
                    {(Object.keys(BATCH_METRIC_LABELS) as BatchMetric[]).map((m) => (
                      <button
                        key={m}
                        type="button"
                        className={`batch-metric-tab${batchMetric === m ? " active" : ""}`}
                        onClick={() => setBatchMetric(m)}
                      >
                        {BATCH_METRIC_LABELS[m]}
                      </button>
                    ))}
                  </div>
                  <div className="card" style={{ background: "var(--color-bg-base)", marginBottom: "var(--space-4)" }}>
                    <GroupBarChart
                      bars={activeGroup.bars}
                      selectedKey={activeGroup.selected}
                      onSelect={activeGroup.setSelected}
                      emptyHint="그래프로 표시할 그룹이 없습니다."
                      todayKey={batchScope === "date" ? todayStr : undefined}
                    />
                  </div>
                  {!showBatchDrilldown && (
                    <div className="vif-note align-start" style={{ marginBottom: "var(--space-4)" }}>
                      👆 위 그래프에서 {activeGroup.label} 막대를 클릭하면 해당 로트 목록과 판정 상세를
                      아래에서 확인할 수 있습니다.
                    </div>
                  )}
                </>
              )}

              {showBatchDrilldown && batchScope !== "all" && (
                <div className="card-head" style={{ marginBottom: "var(--space-3)" }}>
                  <h3 style={{ fontSize: "0.9375rem" }}>
                    선택: {activeGroup.selected}
                    {batchScope === "buyer" ? " 바이어" : ""}
                    {batchScope === "date" && activeGroup.selected === todayStr ? " (오늘)" : ""}{" "}
                    <span className="pill-count">{scopedBatchRows.length}건</span>
                  </h3>
                  <button className="raw-data-toggle" onClick={() => activeGroup.setSelected("")}>
                    ← 전체 {activeGroup.label} 그래프로
                  </button>
                </div>
              )}

              {showBatchDrilldown && batchResult.total > 0 && (
                <div className="insight-row" style={{ marginBottom: "var(--space-5)" }}>
                  <div className="insight-card">
                    <div className="insight-label">Y(포화도) 판정</div>
                    <div className="insight-value">
                      양품 {batchSummary.yPass}건<br />부적합 {batchSummary.yFail}건
                    </div>
                  </div>
                  <div className="insight-card">
                    <div className="insight-label">Z(20시간 용량) 판정</div>
                    <div className="insight-value">
                      양품 {batchSummary.zPass}건<br />부적합 {batchSummary.zFail}건
                    </div>
                  </div>
                  <div className="insight-card">
                    <div className="insight-label">Z2(SAE CCA) 판정</div>
                    <div className="insight-value">
                      양품 {batchSummary.saePass}건<br />부적합 {batchSummary.saeFail}건
                    </div>
                  </div>
                  <div className="insight-card">
                    <div className="insight-label">Z3(EN CCA) 판정</div>
                    <div className="insight-value">
                      양품 {batchSummary.enPass}건<br />부적합 {batchSummary.enFail}건
                    </div>
                  </div>
                </div>
              )}
              {!anyCcaAvailable && batchResult.total > 0 && (
                <div className="vif-note align-start" style={{ marginBottom: "var(--space-4)" }}>
                  📌 SAE·EN CCA(저온시동전류)는 아직 회귀 모델이 학습되지 않아(신뢰성 시험 표본
                  부족) 이번 예측에는 포함되지 않았습니다 — 표본이 쌓이면 대시보드의 &ldquo;CCA
                  회귀 시도&rdquo;로 학습한 뒤 여기서도 함께 예측됩니다.
                </div>
              )}
              {batchResult.total === 0 ? (
                <div style={{ fontSize: "0.8125rem", color: "var(--color-text-secondary)" }}>
                  대상 로트가 없습니다 — 모든 로트가 이미 시험 매칭됐거나, 수기입력(전해액온도·충전량·
                  수조온도)이 아직 채워지지 않았을 수 있습니다.
                </div>
              ) : !showBatchDrilldown ? null : (
                <>
                  {scopedBatchRows.length > BATCH_TABLE_LIMIT && (
                    <div className="vif-note align-start" style={{ marginBottom: "var(--space-3)" }}>
                      📋 이 범위에 {scopedBatchRows.length}건이 있어, 표에는 이상치·부적합을 우선한
                      상위 {BATCH_TABLE_LIMIT}건만 표시합니다. 나머지는 위 요약 카드의 집계에는
                      포함돼 있습니다.
                    </div>
                  )}
                  <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>lot_id</th>
                      <th>모델</th>
                      <th>Y (포화도)</th>
                      <th>Y 판정</th>
                      <th>Z (capacity_rate)</th>
                      <th>Z 판정</th>
                      <th>Z2 (SAE CCA)</th>
                      <th>Z2 판정</th>
                      <th>Z3 (EN CCA)</th>
                      <th>Z3 판정</th>
                      <th>이상치</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleBatchRows.map((row) => {
                      const yBadge = specBadge(row.y.spec);
                      const zBadge = row.z.available ? specBadge(row.z.spec) : null;
                      const saeCcaBadge = row.sae_cca.available ? specBadge(row.sae_cca.spec) : null;
                      const enCcaBadge = row.en_cca.available ? specBadge(row.en_cca.spec) : null;
                      return (
                        <tr key={row.lot_id}>
                          <td className="cell-lot">{row.lot_id}</td>
                          <td>{row.model_name}</td>
                          <td>{fmt(row.y.predicted_value)}%</td>
                          <td>
                            <span className={`status-pill ${yBadge.tone}`}>
                              <span className="dot" />
                              {badgeToneLabel(yBadge.tone)}
                            </span>
                          </td>
                          <td>
                            {row.z.available ? (
                              <>
                                {fmt(row.z.predicted_capacity_rate)}%<span className="yhat-flag">Ŷ 기반</span>
                              </>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td>
                            {zBadge ? (
                              <span className={`status-pill ${zBadge.tone}`}>
                                <span className="dot" />
                                {badgeToneLabel(zBadge.tone)}
                              </span>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td>
                            {row.sae_cca.available && row.sae_cca.predicted_value !== null ? (
                              <>
                                {fmt(row.sae_cca.predicted_value, 3)}Ah<span className="yhat-flag">Ŷ 기반</span>
                              </>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td>
                            {saeCcaBadge ? (
                              <span className={`status-pill ${saeCcaBadge.tone}`}>
                                <span className="dot" />
                                {badgeToneLabel(saeCcaBadge.tone)}
                              </span>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td>
                            {row.en_cca.available && row.en_cca.predicted_value !== null ? (
                              <>
                                {fmt(row.en_cca.predicted_value, 3)}Ah<span className="yhat-flag">Ŷ 기반</span>
                              </>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td>
                            {enCcaBadge ? (
                              <span className={`status-pill ${enCcaBadge.tone}`}>
                                <span className="dot" />
                                {badgeToneLabel(enCcaBadge.tone)}
                              </span>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td>
                            {row.is_outlier && <span className="outlier-flag">⚠ 물리적으로 불가능한 값</span>}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                  </div>
                </>
              )}
            </div>
          )}
        </>
      )}

      <div className="foot-note">
        전 구간 로컬 처리, 외부 전송 없음. &quot;Ŷ 기반&quot; 배지는 2단 Z 예측에 실측 Y 대신 1단
        예측값이 입력되었음을 뜻합니다(input_y_source: predicted). 학습은 항상 실측 Y로만 수행됩니다.
      </div>
    </div>
  );
}
