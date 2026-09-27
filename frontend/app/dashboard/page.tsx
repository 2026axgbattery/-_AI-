"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { TopBar } from "@/components/TopBar";
import { StepFlow } from "@/components/StepFlow";
import {
  apiClient,
  ApiError,
  type AnalysisRunResult,
  type KpiSummary,
  type ScoringRunResult,
  type ScoringTarget,
  type SpecComplianceSummary,
  type YVsCcaPair,
} from "@/lib/api-client";
import { ccaSpecBadge } from "@/lib/cca-spec";
import { RadialGauge } from "@/components/RadialGauge";
import { CorrelationBarChart } from "@/components/charts/CorrelationBarChart";
import { DivergingBarChart } from "@/components/charts/DivergingBarChart";
import Link from "next/link";

type Stage = "x_to_y" | "xy_to_z" | "x_to_z_baseline";
type CcaStage = "xy_to_sae_cca" | "xy_to_en_cca";

// 포화도(Y)↔CCA 관계표 — 로트 수가 많아지면(형명당 수천 건 규모 더미 데이터) 전부 나열하지
// 않고 규격 기준 대비 여유가 가장 적은 상위 N건만 보여준다. 전체는 별도 새 창(raw data)에서.
const WORST_CCA_LIMIT = 10;

// 검증·채점(history/24) — target별 "예측 SPEC 판정 == 실측 SPEC 판정" 일치율.
const SCORING_TARGETS: { key: ScoringTarget; label: string }[] = [
  { key: "y", label: "포화도(Y)" },
  { key: "z", label: "20시간 용량(Z)" },
  { key: "en_cca_spec", label: "EN CCA 합격여부" },
  { key: "sae_cca_spec", label: "SAE CCA 합격여부" },
];

const X_COLUMN_LABELS: Record<string, string> = {
  electrolyte_temp: "전해액온도",
  tank_temp: "수조온도",
  soaking_time_sec: "함침시간",
  aging_days: "에이징일수",
  formation_dv: "화성전압차",
  cell_weight_mean: "셀중량 평균",
  cell_weight_std: "셀중량 표준편차",
  charge_ratio: "충전율(정격 대비 %)",
  charge_program_deviation_pct: "충전 프로그램 이탈도(기준 대비 %)",
  retention_rate: "포화도(Y, 실측)",
};

function labelFor(col: string): string {
  return X_COLUMN_LABELS[col] ?? col;
}

function fmt(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v.toFixed(digits);
}

function fmtSigned(v: number): string {
  return `${v >= 0 ? "+" : ""}${v.toFixed(3)}`;
}

/** |r|이 얼마나 커야 "관계가 높다"고 볼 수 있는지에 대한 일반적인 통계 해석 기준(참고용).
 * 도메인 전용 기준이 아니라 사회과학·통계에서 흔히 쓰는 rule-of-thumb이다. */
function strengthLabel(absR: number): string {
  if (absR < 0.1) return "거의 없음";
  if (absR < 0.3) return "약한 관계";
  if (absR < 0.5) return "보통 관계";
  return "강한 관계";
}

interface RankedFactor {
  col: string;
  r: number;
  significant: boolean;
  direction: "높아지는" | "낮아지는";
  strength: string;
}

/** 회귀 결과(X→Y 또는 X+Y→Z)에서 |상관계수| 기준 영향력 순위를 뽑는다 — 대시보드 메인
 * "가장 큰 영향 인자" 카드(Y·Z 공용)에서 쓴다. `excludeCols`로 Z 랭킹에서 포화도(Y) 자신을
 * 뺀다(Y는 캐스케이드의 매개변수라 "어떤 공정인자가 문제인지"와는 다른 질문이라 제외). */
function rankFactorsByCorrelation(
  run: AnalysisRunResult | undefined,
  excludeCols: string[] = []
): RankedFactor[] {
  if (!run) return [];
  const candidates = run.x_columns.filter((c) => !excludeCols.includes(c));
  const significantCols = candidates.filter((c) => run.significance[c]?.significant);
  const pool = significantCols.length > 0 ? significantCols : candidates;
  const sorted = [...pool].sort(
    (a, b) => Math.abs(run.significance[b]?.r ?? 0) - Math.abs(run.significance[a]?.r ?? 0)
  );
  return sorted.slice(0, 3).map((col) => {
    const s = run.significance[col];
    const r = s?.r ?? 0;
    return {
      col,
      r,
      significant: !!s?.significant,
      direction: r >= 0 ? "높아지는" : "낮아지는",
      strength: strengthLabel(Math.abs(r)),
    };
  });
}

/** "가장 큰 영향 인자" 카드용 — 결과 우선 재설계 이전에 메인 화면에 바로 보이던 상관계수
 * 막대그래프를 다시 가져오되, 근거 섹션의 3열 그리드(`.heat-row`)는 좁은 카드에서 긴 한글
 * 라벨("충전 프로그램 이탈도(기준 대비 %)" 등)이 밀려 보여 그대로 쓰지 않는다 — 라벨을 한 줄에
 * 통째로 두고 막대는 그 아래 별도 줄에 두는 세로 배치(`.factor-mini-item`)라 라벨 길이와
 * 무관하게 항상 안 밀린다. `.heat-bar-track`/`.heat-bar-fill`(막대 자체)만 그대로 재사용. */
function FactorMiniList({ factors, emptyText }: { factors: RankedFactor[]; emptyText: string }) {
  if (factors.length === 0) {
    return <div className="insight-desc factor-mini-empty">{emptyText}</div>;
  }
  return (
    <>
      {factors.slice(0, 2).map((f) => (
        <div className="factor-mini-item" key={f.col}>
          <div className="factor-mini-item-head">
            <span className="factor-mini-name">
              {labelFor(f.col)} <span className="factor-mini-strength">· {f.strength}</span>
            </span>
            <span className={`factor-mini-r${f.significant ? " strong" : ""}`}>
              {fmt(f.r)}
              {f.significant ? "" : "†"}
            </span>
          </div>
          <div className="heat-bar-track">
            <div
              className="heat-bar-fill"
              style={{
                width: `${Math.min(Math.abs(f.r) * 100, 100)}%`,
                background: f.r < 0 ? "var(--sebang-gray-400)" : undefined,
              }}
            />
          </div>
        </div>
      ))}
    </>
  );
}

/** 캐스케이드(X+Y→Z) R²와 베이스라인(X→Z) R² 차이가 무엇을 뜻하는지 평이한 문장으로 설명.
 * "포화도(Y)를 추가로 넣었을 때 20시간 용량(Z)을 더 잘 설명하게 됐는지"가 핵심 질문이다. */
function interpretR2Gap(
  cascade: AnalysisRunResult | undefined,
  baseline: AnalysisRunResult | undefined
): string | null {
  if (!cascade || !baseline) return null;
  const gap = cascade.r_squared - baseline.r_squared;
  if (Math.abs(gap) < 0.01) {
    return `두 R²가 거의 같습니다(차이 ${fmtSigned(gap)}) — 이번 데이터에서는 포화도(Y)를 추가로 알아도 20시간 용량(Z) 설명력이 눈에 띄게 나아지지 않았다는 뜻입니다. 즉 공정인자(X)만으로도 베이스라인 수준의 설명력을 이미 확보했다는 의미입니다.`;
  }
  if (gap > 0) {
    return `캐스케이드 R²가 베이스라인보다 ${fmt(gap, 3)} 더 높습니다 — 포화도(Y)를 추가로 넣었을 때 20시간 용량(Z)을 더 잘 설명하게 됐다는 뜻입니다(포화도가 공정인자만으로는 알 수 없는 추가 정보를 준다는 신호).`;
  }
  return `캐스케이드 R²가 베이스라인보다 오히려 ${fmt(Math.abs(gap), 3)} 낮습니다 — 이 표본에서는 포화도(Y)를 추가해도 설명력이 개선되지 않았다는 뜻입니다.`;
}

type Tone = "ok" | "warn" | "unknown";

interface HeroMetric {
  icon: string;
  label: string;
  value: string;
  tone: Tone;
  sub: string;
  /** 0~100 비율 — 히어로 카드의 원형 게이지(RadialGauge) 채움값. null이면 빈 링만 표시. */
  gaugeValue: number | null;
}

/** 히어로 지표 3개(Y/Z/CCA) 공용 톤 판정 — 실측 기준 미달이 있으면 warn, 판정 기준 자체가
 * 없으면 unknown, 그 외(기준 있음+미달 없음)는 ok. */
function metricTone(hasBasis: boolean, hasFail: boolean): Tone {
  if (!hasBasis) return "unknown";
  return hasFail ? "warn" : "ok";
}

/** "스펙이 얼마인지" 자체를 보여달라는 요청(2026-09-27) — 형명마다 SPEC 하한이 다를 수 있어
 * 하나의 숫자로 단정하지 않고, 실제로 설정된 값이 전부 같으면 그 값을, 다르면 범위를 보여준다. */
function specRangeLabel(min: number | null | undefined, max: number | null | undefined): string | null {
  if (min == null || max == null) return null;
  if (Math.abs(min - max) < 0.001) return `${fmt(min, 1)}%`;
  return `${fmt(min, 1)}~${fmt(max, 1)}%`;
}

/** 초대형 결론 배너(Layer 0)용 — "특정 로트를 확인하라"는 경고보다 먼저, X→Y→Z 전체 평균이
 * 어떤 상태인지부터 한눈에 보여준다(사용자 피드백: 메인은 평균 결과, 미달 로트 안내는 아래
 * insight-row의 Y/Z 카드로). */
function buildHeroVerdict(
  kpi: KpiSummary | null,
  spec: SpecComplianceSummary | null
): {
  tone: Tone;
  icon: string;
  chip: string;
  title: string;
  desc: ReactNode;
  metrics: HeroMetric[];
  followUp: ReactNode | null;
} {
  const hasSpec = !!spec && spec.models_with_spec > 0;
  const yFail = spec?.y_fail ?? 0;
  const zFail = spec?.z_fail ?? 0;
  const enCcaEvaluated = kpi?.en_cca_evaluated ?? 0;
  const saeCcaEvaluated = kpi?.sae_cca_evaluated ?? 0;
  const ccaHasBasis = enCcaEvaluated > 0 || saeCcaEvaluated > 0;
  const ccaHasFail =
    (kpi?.en_cca_pass ?? 0) < enCcaEvaluated || (kpi?.sae_cca_pass ?? 0) < saeCcaEvaluated;
  const ySpecLabel = specRangeLabel(spec?.spec_lower_y_min, spec?.spec_lower_y_max);
  const zSpecLabel = specRangeLabel(spec?.spec_lower_z_min, spec?.spec_lower_z_max);
  const saeRate = saeCcaEvaluated ? ((kpi?.sae_cca_pass ?? 0) / saeCcaEvaluated) * 100 : null;
  const enRate = enCcaEvaluated ? ((kpi?.en_cca_pass ?? 0) / enCcaEvaluated) * 100 : null;
  const ccaGaugeValue =
    saeRate !== null && enRate !== null
      ? (saeRate + enRate) / 2
      : saeRate ?? enRate;

  const metrics: HeroMetric[] = [
    {
      icon: "💧",
      label: "포화도(Y) 평균",
      value: kpi?.avg_retention_rate != null ? `${fmt(kpi.avg_retention_rate, 1)}%` : "—",
      tone: metricTone(hasSpec, yFail > 0),
      sub: ySpecLabel ? `SPEC 하한 ${ySpecLabel} · 미달 ${yFail}건` : "데이터 없음",
      gaugeValue: kpi?.avg_retention_rate ?? null,
    },
    {
      icon: "🔋",
      label: "20시간 용량(Z) 평균",
      value: kpi?.avg_capacity_rate != null ? `${fmt(kpi.avg_capacity_rate, 1)}%` : "—",
      tone: metricTone(hasSpec, zFail > 0),
      sub: zSpecLabel ? `SPEC 하한 ${zSpecLabel} · 미달 ${zFail}건` : "데이터 없음",
      gaugeValue: kpi?.avg_capacity_rate ?? null,
    },
    {
      icon: "🧊",
      label: "CCA 합격률",
      value: ccaHasBasis
        ? `SAE ${saeRate !== null ? fmt(saeRate, 0) : "—"}% · EN ${enRate !== null ? fmt(enRate, 0) : "—"}%`
        : "—",
      tone: metricTone(ccaHasBasis, ccaHasFail),
      sub: ccaHasBasis ? "기준 EN ≥7.5V·90초 / SAE ≥7.2V·30초(고정)" : "시험 데이터 없음",
      gaugeValue: ccaGaugeValue,
    },
  ];

  const totalFail = yFail + zFail;
  const anyWarn = metrics.some((m) => m.tone === "warn");
  const anyBasis = hasSpec || ccaHasBasis;

  const followUp =
    totalFail > 0 ? (
      <span className="hero-desc-line hero-desc-sub">
        포화도(Y) {yFail}건, 20시간 용량(Z) {zFail}건은 아래 카드에서 어떤 형명인지 확인하세요. ↓
      </span>
    ) : null;

  if (!anyBasis) {
    return {
      tone: "unknown",
      icon: "❔",
      chip: "판정 불가",
      title: "아직 판정할 데이터가 없어요",
      desc: "업로드된 로트가 없어 판정할 수 없습니다 — 데이터가 들어오면 SPEC(포화도 90%·20시간 용량 95%, CCA는 EN 50342/SAE J537 고정 기준) 대비 합격/불합격이 바로 나옵니다.",
      metrics,
      followUp,
    };
  }
  if (!anyWarn) {
    return {
      tone: "ok",
      icon: "✅",
      chip: "정상",
      title: "현재 데이터, 평균적으로 정상이에요",
      desc: (
        <span className="hero-desc-line">
          지금까지 확인된 로트 기준으로 포화도(Y)·20시간 용량(Z)·CCA 모두 평균이 기준을 충족했습니다.
        </span>
      ),
      metrics,
      followUp: null,
    };
  }
  return {
    tone: "warn",
    icon: "⚠️",
    chip: "확인 필요",
    title: "평균은 정상 범위지만 확인이 필요한 로트가 있어요",
    desc: (
      <span className="hero-desc-line">
        아래 3개 지표 중 기준 미달이 있는 항목을 확인하세요 — 평균 자체는 정상 범위라도 일부 로트가
        전체 평균을 끌어올리거나 내릴 수 있습니다.
      </span>
    ),
    metrics,
    followUp,
  };
}

/** "한눈에 보기" Y/Z 카드용 — SPEC 미달 건수를 전문용어 없이 상태로 요약. */
function buildSpecCard(
  metricLabel: string,
  fail: number | undefined,
  evaluated: number | undefined,
  modelsWithSpec: number | undefined
): { tone: Tone; chip: string; value: string; desc: string } {
  if (!modelsWithSpec) {
    return {
      tone: "unknown",
      chip: "데이터 없음",
      value: "판정 불가",
      desc: `아직 업로드된 로트가 없어 ${metricLabel} 판정을 할 수 없습니다.`,
    };
  }
  if (!fail) {
    return {
      tone: "ok",
      chip: "정상",
      value: "기준 충족",
      desc: `SPEC이 설정된 형명 전량(${evaluated ?? 0}건)이 ${metricLabel} 기준을 충족했습니다.`,
    };
  }
  return {
    tone: "warn",
    chip: "확인 필요",
    value: `${fail}건 미달`,
    desc: `평가 대상 ${evaluated ?? 0}건 중 ${fail}건이 ${metricLabel} 기준에 못 미칩니다.`,
  };
}

/** 검증·채점 카드용 — 4개 target 중 가장 낮은 일치율을 대표값으로 보여준다(약한 고리 기준). */
function buildScoringCard(scoring: Partial<Record<ScoringTarget, ScoringRunResult>>): {
  tone: Tone;
  chip: string;
  value: string;
  desc: string;
} {
  const entries = SCORING_TARGETS.map(({ key }) => scoring[key]).filter(
    (r): r is ScoringRunResult => !!r
  );
  if (entries.length === 0) {
    return { tone: "unknown", chip: "미채점", value: "—", desc: "아직 채점을 실행한 적이 없습니다." };
  }
  const rates = entries
    .map((r) => r.success_rate_pct)
    .filter((v): v is number => v !== null && v !== undefined);
  const minRate = rates.length > 0 ? Math.min(...rates) : null;
  const anyReliable = entries.some((r) => r.reliable === true);
  const anyUnreliable = entries.some((r) => r.reliable === false);
  if (anyReliable && !anyUnreliable) {
    return {
      tone: "ok",
      chip: "신뢰 가능",
      value: minRate !== null ? `${minRate.toFixed(1)}%` : "—",
      desc: "예측이 실측과 맞는 비율이 신뢰 기준(90%)을 충족했습니다.",
    };
  }
  if (anyUnreliable) {
    return {
      tone: "warn",
      chip: "확인 필요",
      value: minRate !== null ? `${minRate.toFixed(1)}%` : "—",
      desc: "예측이 실측과 맞는 비율이 신뢰 기준(90%)에는 아직 못 미칩니다. 표본이 더 쌓이면 다시 확인해요.",
    };
  }
  return { tone: "unknown", chip: "판정 불가", value: "—", desc: "판정할 수 있는 항목이 아직 없습니다." };
}

export default function DashboardPage() {
  const [kpi, setKpi] = useState<KpiSummary | null>(null);
  const [specCompliance, setSpecCompliance] = useState<SpecComplianceSummary | null>(null);
  const [results, setResults] = useState<Partial<Record<Stage, AnalysisRunResult>>>({});
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  // CCA(Z2/Z3, history/19 Phase C)는 표본이 극히 적어 실패가 정상 상태다 — 메인 에러 배너와
  // 완전히 분리된 상태로 관리해, 실패해도 위 핵심 분석 결과가 "오류"처럼 보이지 않게 한다.
  const [yVsCca, setYVsCca] = useState<YVsCcaPair[]>([]);
  const [yVsCcaTotal, setYVsCcaTotal] = useState(0);
  const [ccaResults, setCcaResults] = useState<Partial<Record<CcaStage, AnalysisRunResult>>>({});
  const [ccaNote, setCcaNote] = useState<Partial<Record<CcaStage, string>>>({});
  const [ccaRunning, setCcaRunning] = useState(false);

  // 검증·채점(history/24)
  const [scoring, setScoring] = useState<Partial<Record<ScoringTarget, ScoringRunResult>>>({});
  const [scoringRunning, setScoringRunning] = useState(false);

  const refresh = useCallback(async () => {
    const kpiData = await apiClient.getKpi().catch(() => null);
    setKpi(kpiData);
    const specData = await apiClient.getSpecCompliance().catch(() => null);
    setSpecCompliance(specData);

    const stages: Stage[] = ["x_to_y", "xy_to_z", "x_to_z_baseline"];
    const next: Partial<Record<Stage, AnalysisRunResult>> = {};
    for (const stage of stages) {
      const result = await apiClient.getLatestAnalysis(stage).catch(() => null);
      if (result) next[stage] = result;
    }
    setResults(next);

    const ccaStages: CcaStage[] = ["xy_to_sae_cca", "xy_to_en_cca"];
    const nextCca: Partial<Record<CcaStage, AnalysisRunResult>> = {};
    for (const stage of ccaStages) {
      const result = await apiClient.getLatestAnalysis(stage).catch(() => null);
      if (result) nextCca[stage] = result;
    }
    setCcaResults(nextCca);
    const ccaPairs = await apiClient.getYVsCca({ limit: WORST_CCA_LIMIT, sort: "worst" }).catch(() => null);
    setYVsCca(ccaPairs?.pairs ?? []);
    setYVsCcaTotal(ccaPairs?.total_count ?? 0);

    const nextScoring: Partial<Record<ScoringTarget, ScoringRunResult>> = {};
    for (const { key } of SCORING_TARGETS) {
      const result = await apiClient.getLatestScoring(key).catch(() => null);
      if (result) nextScoring[key] = result;
    }
    setScoring(nextScoring);

    setLoaded(true);
  }, []);

  /** target 4종을 전부 채점 — "다시 채점" 버튼과 분석 실행 직후 둘 다에서 재사용한다(분석을 막
   * 실행한 직후에는 채점 이력이 아직 없어 "검증 신뢰도" 카드가 계속 "미채점"으로 보였던 문제 수정). */
  const runScoringAll = useCallback(async () => {
    const next: Partial<Record<ScoringTarget, ScoringRunResult>> = {};
    for (const { key } of SCORING_TARGETS) {
      try {
        next[key] = await apiClient.runScoring(key);
      } catch {
        // 무시 — 표본 부족·판정불가는 결과의 note/reliable 필드로 이미 정직하게 표현됨.
        // 여기서 잡는 예외는 네트워크 오류 등 그 외의 경우뿐.
      }
    }
    setScoring((prev) => ({ ...prev, ...next }));
  }, []);

  async function handleRunScoring() {
    setScoringRunning(true);
    await runScoringAll();
    setScoringRunning(false);
  }

  async function handleRunCca() {
    setCcaRunning(true);
    const nextNote: Partial<Record<CcaStage, string>> = {};
    for (const [stage, run] of [
      ["xy_to_sae_cca", apiClient.runXyToSaeCca] as const,
      ["xy_to_en_cca", apiClient.runXyToEnCca] as const,
    ]) {
      try {
        await run();
        nextNote[stage] = "성공 — 아래 결과가 갱신됐습니다.";
      } catch (e) {
        nextNote[stage] = e instanceof ApiError ? String(e.detail) : "분석 실행 중 오류가 발생했습니다.";
      }
    }
    setCcaNote(nextNote);
    await refresh();
    setCcaRunning(false);
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refresh();
  }, [refresh]);

  async function handleRunAnalysis() {
    setRunning(true);
    setError(null);
    try {
      await apiClient.runXToY();
      await apiClient.runXyToZ();
      await apiClient.runXToZBaseline();
      await refresh();
      await runScoringAll();
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail) : "분석 실행 중 오류가 발생했습니다.");
    } finally {
      setRunning(false);
    }
  }

  const xToY = results.x_to_y;
  const xyToZ = results.xy_to_z;
  const baseline = results.x_to_z_baseline;

  const sortedCorrelation = xToY
    ? [...xToY.x_columns].sort(
        (a, b) => Math.abs(xToY.significance[b]?.r ?? 0) - Math.abs(xToY.significance[a]?.r ?? 0)
      )
    : [];
  const sortedCoef = xToY
    ? [...xToY.x_columns].sort(
        (a, b) => Math.abs(xToY.coefficients[b] ?? 0) - Math.abs(xToY.coefficients[a] ?? 0)
      )
    : [];

  const correlationChartData = sortedCorrelation.map((col) => {
    const sig = xToY?.significance[col];
    const r = sig?.r ?? 0;
    return {
      key: col,
      label: labelFor(col),
      r,
      strengthLabel: strengthLabel(Math.abs(r)),
      significant: !!sig?.significant,
    };
  });
  const coefChartData = sortedCoef.map((col) => ({
    key: col,
    label: labelFor(col),
    value: xToY?.coefficients[col] ?? 0,
  }));

  const r2GapNote = interpretR2Gap(xyToZ, baseline);

  const hero = buildHeroVerdict(kpi, specCompliance);
  const yCard = buildSpecCard("포화도(Y)", specCompliance?.y_fail, specCompliance?.y_evaluated, specCompliance?.models_with_spec);
  const zCard = buildSpecCard("20시간 용량(Z)", specCompliance?.z_fail, specCompliance?.z_evaluated, specCompliance?.models_with_spec);
  const yRankedFactors = rankFactorsByCorrelation(xToY);
  const zRankedFactors = rankFactorsByCorrelation(xyToZ, ["retention_rate"]);
  const scoringCard = buildScoringCard(scoring);

  return (
    <div className="app">
      <TopBar active="분석 대시보드" />

      <StepFlow current="dashboard" />

      <div className="page-head">
        <div>
          <h1>분석 대시보드</h1>
          <p>공정 데이터로 예측한 포화도(Y)·20시간 용량(Z)의 지금 상태를 한눈에 확인하세요.</p>
        </div>
        <button className="btn btn-primary" onClick={handleRunAnalysis} disabled={running}>
          {running ? "분석 실행 중..." : "1단·2단 분석 실행"}
        </button>
      </div>

      <div className="onboard-strip">
        <span className="onboard-icon">💡</span>
        <div>
          처음이라도 걱정 마세요 — 위 순서(① 업로드 → ② 결과 확인 → ③ 상세 조회 → ④ 예측)만
          따라가면 오늘 데이터가 <b>괜찮은지 바로</b> 알 수 있어요.
        </div>
      </div>

      {error && <div className="alert warn">{error}</div>}

      {!loaded && <div className="alert">불러오는 중...</div>}

      {loaded && !xToY && !running && (
        <div className="alert">
          아직 저장된 분석 결과가 없습니다. 위 <b>1단·2단 분석 실행</b> 버튼을 눌러 회귀를 실행하세요.
          업로드·수기입력이 끝난 로트가 최소 10건 이상 있어야 1단(X→Y) 회귀가 가능합니다.
        </div>
      )}

      {/* ===== Layer 0: 초대형 결론 배너 + 한눈에 보기 카드 4개 ===== */}
      {loaded && xToY && (
        <>
          <div className="hero-verdict">
            <div className="hero-watermark">EB</div>
            <div className="hero-icon">{hero.icon}</div>
            <div className="hero-body">
              <div className="hero-eyebrow-row">
                <span className="hero-eyebrow">종합 결론</span>
                <span className={`status-chip ${hero.tone}`}>{hero.chip}</span>
              </div>
              <div className="hero-title">{hero.title}</div>
              <div className="hero-desc">{hero.desc}</div>
              <div className="hero-metrics">
                {hero.metrics.map((m) => (
                  <div className="hero-metric" key={m.label}>
                    <div className="hero-metric-head">
                      <span>
                        {m.icon} {m.label}
                      </span>
                      <span className={`status-chip ${m.tone}`}>
                        {m.tone === "ok" ? "정상" : m.tone === "warn" ? "확인 필요" : "판정 불가"}
                      </span>
                    </div>
                    <div className="hero-metric-body">
                      <RadialGauge value={m.gaugeValue !== null ? Math.min(m.gaugeValue, 100) : null} />
                      <div>
                        <div className="hero-metric-value">{m.value}</div>
                        <div className="hero-metric-sub">{m.sub}</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              {hero.followUp && <div className="hero-desc hero-followup">{hero.followUp}</div>}
              <div className="hero-updated">
                마지막 갱신 {xToY.run_at ?? "—"} · 분석 표본 {xToY.n}건
              </div>
            </div>
          </div>

          <div className="insight-row insight-row--2x2">
            <div className="insight-card">
              <div className="insight-head">
                <span className="insight-label">
                  <span className="insight-icon">💧</span> 포화도(Y)
                </span>
                <span className={`status-chip ${yCard.tone}`}>{yCard.chip}</span>
              </div>
              <div className="insight-value">{yCard.value}</div>
              <div className="insight-desc">{yCard.desc}</div>
              <Link href="/detail-analysis" className="insight-cta">
                형명별로 자세히 보기 →
              </Link>
            </div>

            <div className="insight-card">
              <div className="insight-head">
                <span className="insight-label">
                  <span className="insight-icon">🔋</span> 20시간 용량(Z)
                </span>
                <span className={`status-chip ${zCard.tone}`}>{zCard.chip}</span>
              </div>
              <div className="insight-value">{zCard.value}</div>
              <div className="insight-desc">{zCard.desc}</div>
              <Link href="/detail-analysis" className="insight-cta">
                미달 로트 보기 →
              </Link>
            </div>

            <div className="insight-card">
              <div className="insight-head">
                <span className="insight-label">
                  <span className="insight-icon">🎯</span> X → Y → Z 핵심 영향 인자
                </span>
                <span className="status-chip unknown">참고</span>
              </div>
              <div className="factor-mini-group">
                <div className="factor-mini-title">💧 포화도(Y)에 영향을 준 공정인자</div>
                <FactorMiniList factors={yRankedFactors} emptyText="아직 통계적으로 뚜렷한 인자가 확인되지 않았습니다." />
              </div>
              <div className="factor-mini-group">
                <div className="factor-mini-title">🔋 20시간 용량(Z)에 영향을 준 인자</div>
                <FactorMiniList
                  factors={zRankedFactors}
                  emptyText={xyToZ ? "아직 통계적으로 뚜렷한 인자가 확인되지 않았습니다." : "아직 2단(X+Y→Z) 회귀가 실행되지 않았습니다."}
                />
              </div>
              <Link href="/prediction" className="insight-cta">
                로트별 원인 진단 보기 →
              </Link>
            </div>

            <div className="insight-card">
              <div className="insight-head">
                <span className="insight-label">
                  <span className="insight-icon">🧪</span> 검증 신뢰도
                </span>
                <span className={`status-chip ${scoringCard.tone}`}>{scoringCard.chip}</span>
              </div>
              <div className="insight-value">{scoringCard.value}</div>
              <div className="insight-desc">{scoringCard.desc}</div>
              <a href="#scoring-detail" className="insight-cta">
                검증 자세히 보기 →
              </a>
            </div>
          </div>
        </>
      )}

      {/* ===== 통계 근거 자세히 보기(구 "전문가 모드") — 기본 접힘 ===== */}
      <details className="evidence-toggle" id="evidence">
        <summary>
          통계 근거 자세히 보기
          <span className="summary-sub">상관계수 · 회귀계수 · VIF · 검증 채점표 (담당자·통계 확인용)</span>
        </summary>
        <div className="evidence-toggle-body">
      {/* ===== Layer 2: 근거 — 기본 접힘, 클릭 시 펼침 ===== */}
      {xToY && (
        <details className="evidence" open>
          <summary>
            <span className="summary-tag">1단</span> X → Y(포화도) 상관·회귀 근거 보기
            <span className="summary-hint">상관계수 · 회귀계수 · VIF</span>
          </summary>
          <div className="evidence-body">
            <div className="flow-strip">
              <div className="flow-node">
                <span className="tag">INPUT</span>
                <div className="name">X · 공정인자</div>
                <div className="desc">
                  전해액온도·수조온도·함침시간·에이징일수·화성전압차·셀중량평균/표준편차·충전율(정격
                  대비 %)·충전 프로그램 이탈도. process_data.csv 컬럼 + 충전 STEP 기준표 대비 파생값.
                </div>
              </div>
              <div className="flow-arrow">→</div>
              <div className="flow-node">
                <span className="tag">1단</span>
                <div className="name">Y · 포화도 (잔존율 proxy)</div>
                <div className="desc">(fill_weight − water_loss) / fill_weight × 100.</div>
              </div>
              <div className="flow-arrow">→</div>
              <div className="flow-node">
                <span className="tag">2단</span>
                <div className="name">Z · 20시간 용량</div>
                <div className="desc">
                  discharge_amount(Ah). 학습은 실측 Y로, 추론 시에만 Ŷ 투입. X→Z 베이스라인과 병행
                  비교.
                </div>
              </div>
            </div>

            <div className="kpi-row">
              <div className="kpi-card">
                <div className="kpi-label">전체 로트</div>
                <div className="kpi-value">{kpi?.total_lots ?? "—"}건</div>
              </div>
              <div className="kpi-card">
                <div className="kpi-label">시험 매칭 로트</div>
                <div className="kpi-value">{kpi?.matched_lots ?? "—"}건</div>
                <div className="kpi-sub">매칭률 {fmt(kpi?.match_rate, 1)}%</div>
              </div>
              <div className="kpi-card">
                <div className="kpi-label">평균 포화도(Y)</div>
                <div className="kpi-value">{fmt(kpi?.avg_retention_rate, 1)}%</div>
              </div>
              <div className="kpi-card">
                <div className="kpi-label">SPEC 판정 (실측/직접계산 기준)</div>
                {specCompliance && specCompliance.models_with_spec > 0 ? (
                  <>
                    <div className="kpi-value">
                      Y {specCompliance.y_fail}건 · Z {specCompliance.z_fail}건
                    </div>
                    <div className={`kpi-sub${specCompliance.y_fail + specCompliance.z_fail > 0 ? " danger" : " ok"}`}>
                      평가 대상 Y {specCompliance.y_evaluated}건 · Z {specCompliance.z_evaluated}건 중 SPEC
                      미달
                    </div>
                  </>
                ) : (
                  <>
                    <div
                      className="kpi-value"
                      style={{ fontSize: "1rem", color: "var(--color-text-secondary)" }}
                    >
                      데이터 없음
                    </div>
                    <div className="kpi-sub">
                      아직 업로드된 로트가 없어 SPEC 판정을 할 수 없습니다. 데이터가 들어오면 포화도(Y)
                      90%·20시간 용량(Z) 95% 기준(전 형명 공통, 형명별로 다르게 하려면
                      templates/spec_thresholds_template.csv로 override 가능)으로 자동 판정됩니다.
                    </div>
                  </>
                )}
              </div>
            </div>

            <div className="section-title">
              <span className="stage-tag">1단</span>
              <h2>X → Y(포화도) 상관·회귀</h2>
              <span className="hint">
                표본 {xToY.n}건 · R² {fmt(xToY.r_squared, 3)}
                {xToY.run_at ? ` · 갱신 ${xToY.run_at}` : ""}
              </span>
            </div>

            <div className="vif-note align-start" style={{ marginBottom: "var(--space-5)" }}>
              📐 <div>
                <b>R²(결정계수, &ldquo;설명력&rdquo;)란?</b> 회귀 모델이 실제 값의 오르내림을 얼마나 잘
                따라가는지를 0~1 사이 숫자로 나타낸 것입니다. 1에 가까울수록 &ldquo;이 공정인자들만 알아도
                포화도(Y)를 거의 정확히 맞힌다&rdquo;는 뜻이고, 0에 가까우면 &ldquo;이 인자들로는 포화도를 거의
                설명하지 못한다&rdquo;는 뜻입니다. 지금 R² {fmt(xToY.r_squared, 3)}는 이번 표본(
                {xToY.n}건) 기준값이며, 표본이 적을수록 실제보다 부풀려질 수 있어 표본이 쌓일수록
                다시 확인하는 것이 안전합니다.
              </div>
            </div>

            <div className="grid-2">
              <div className="card">
                <div className="card-head">
                  <h3>상관계수 — 공정인자 × 포화도(Y)</h3>
                  <span className="hint">|r| 기준</span>
                </div>
                <CorrelationBarChart data={correlationChartData} />
                <div className="vif-note align-start">
                  📏 <div><b>|r| 해석 기준(일반적인 통계 관례)</b> — 0~0.1 거의 없음 · 0.1~0.3
                  약한 관계 · 0.3~0.5 보통 관계 · 0.5 이상 강한 관계. 숫자가 클수록 두 값이 뚜렷하게
                  같이 움직인다는 뜻입니다.</div>
                </div>
                <div className="vif-note align-start">
                  📊 † p ≥ 0.05(유의수준 미달)인 인자는 참고용으로만 보고, 확정된 인과관계로
                  해석하지 않습니다(docs/correlation-reliability-review.md 기준).
                </div>
              </div>

              <div className="card">
                <div className="card-head">
                  <h3>다중선형회귀 계수 (X → Y)</h3>
                  <span className="hint">원 단위 계수</span>
                </div>
                <DivergingBarChart data={coefChartData} />
                <div className="vif-note align-start">
                  📈 다른 인자의 영향을 걷어낸 뒤 이 인자 하나만 바뀌었을 때 Y가 얼마나 움직이는지
                  보여주는 계수입니다. VIF가 5를 크게 넘으면 다중공선성을 의심하세요.
                </div>
                <div className="vif-note">
                  VIF —{" "}
                  {xToY.x_columns.map((c) => `${labelFor(c)} ${fmt(xToY.vif[c], 2)}`).join(" · ")}
                </div>
              </div>
            </div>
          </div>
        </details>
      )}

      {(xyToZ || baseline) && (
        <details className="evidence">
          <summary>
            <span className="summary-tag">2단</span> X + Y → Z(20시간 용량) 회귀 + 베이스라인 근거
            보기
            <span className="summary-hint">
              {xyToZ ? `캐스케이드 표본 ${xyToZ.n}건 · R² ${fmt(xyToZ.r_squared, 3)}` : ""}
              {baseline ? ` · 베이스라인 R² ${fmt(baseline.r_squared, 3)}` : ""}
            </span>
          </summary>
          <div className="evidence-body">
            <div className="vif-note align-start" style={{ marginBottom: "var(--space-5)" }}>
              🧭 <div>
                <b>캐스케이드 vs 베이스라인이란?</b> 20시간 용량(Z)을 추정하는 두 가지 방식을
                나란히 비교합니다. <b>캐스케이드(X+Y→Z)</b>는 공정인자(X)에 더해 1단에서 나온
                포화도(Y)까지 함께 넣어 Z를 설명하고, <b>베이스라인(X→Z)</b>는 포화도 없이 공정인자만
                으로 Z를 설명합니다. 아래 표는 같은 공정인자라도 포화도(Y)를 같이 넣었을 때 계수가
                얼마나 달라지는지를, 표 아래 R² 비교는 두 방식 중 어느 쪽이 Z를 더 잘 설명하는지를
                보여줍니다.
              </div>
            </div>
            <div className="card" style={{ marginBottom: "var(--space-5)" }}>
              <div className="card-head">
                <h3>회귀계수 비교 — 캐스케이드(X+Y→Z) vs 베이스라인(X→Z)</h3>
                <span className="hint">retention_rate(Y)는 베이스라인에 포함되지 않음</span>
              </div>
              <table>
                <thead>
                  <tr>
                    <th>인자</th>
                    <th>캐스케이드 계수</th>
                    <th>베이스라인 계수</th>
                  </tr>
                </thead>
                <tbody>
                  {(xyToZ ?? baseline)!.x_columns
                    .filter((c) => c !== "retention_rate")
                    .map((col) => (
                      <tr key={col}>
                        <td>{labelFor(col)}</td>
                        <td>{xyToZ ? fmtSigned(xyToZ.coefficients[col] ?? 0) : "—"}</td>
                        <td>{baseline ? fmtSigned(baseline.coefficients[col] ?? 0) : "—"}</td>
                      </tr>
                    ))}
                  {xyToZ && (
                    <tr>
                      <td>{labelFor("retention_rate")}</td>
                      <td>{fmtSigned(xyToZ.coefficients.retention_rate ?? 0)}</td>
                      <td>—</td>
                    </tr>
                  )}
                </tbody>
              </table>
              <div className="baseline-compare">
                <div className="baseline-box">
                  <div className="label">캐스케이드 R²</div>
                  <div className="status">{xyToZ ? fmt(xyToZ.r_squared, 3) : "—"}</div>
                </div>
                <div className="baseline-box">
                  <div className="label">베이스라인 R²</div>
                  <div className="status">{baseline ? fmt(baseline.r_squared, 3) : "—"}</div>
                </div>
              </div>
              <div className="vif-note align-start">
                📐 <div>
                  <b>R²(설명력)가 무엇을 뜻하나요?</b> 0~1 사이 값으로, 그 모델이 실제 20시간
                  용량(Z)의 값을 얼마나 정확히 맞히는지를 나타냅니다(1에 가까울수록 실제 값과 잘
                  맞음, 1단의 R² 설명 참고). 여기서는 <b>두 R²의 차이</b>가 핵심입니다 — 캐스케이드
                  R²가 베이스라인보다 뚜렷하게 높다면 &ldquo;포화도(Y)를 알면 용량을 더 잘 예측할 수 있다&rdquo;는
                  뜻이고, 둘이 비슷하다면 &ldquo;포화도 없이 공정인자만으로도 충분하다&rdquo;는 뜻입니다.
                </div>
              </div>
              {r2GapNote && <div className="vif-note align-start">🔍 <div>{r2GapNote}</div></div>}
              <div className="vif-note align-start">
                🔬 정량적 우열 비교(통계적으로 유의미한 차이인지 검정하는 것, 예: F-검정)는 v2
                범위입니다 — 지금은 두 R²의 단순 비교와 구조·계수를 나란히 두는 데 집중합니다. 또한
                표본 수(n={xyToZ?.n ?? baseline?.n ?? "—"})에 비해 공정인자 수가 많으면 R²가
                과대적합으로 실제보다 높게 나올 수 있어, 표본이 더 쌓인 뒤 재확인하는 것이 안전합니다.
              </div>
            </div>
          </div>
        </details>
      )}

      {loaded && (
        <details className="evidence">
          <summary>
            <span className="summary-tag">참고</span> 포화도(Y) ↔ CCA(저온시동전류) 관계 확인
            <span className="summary-hint">규격 기준 대비 여유가 적은 순 상위 {WORST_CCA_LIMIT}건</span>
          </summary>
          <div className="evidence-body">
            <div className="card">
              <p style={{ margin: "0 0 var(--space-4)", fontSize: "0.875rem", lineHeight: 1.6 }}>
                <b>CCA(Cold Cranking Amps, 저온시동전류)</b>는 배터리가 추운 날씨에도 시동을 걸 수
                있는 힘을 나타내는 값이에요. 20시간 용량(Z)과는 별개의 두 번째 성능 지표이고, SAE·EN
                두 국제 규격으로 각각 측정합니다. 포화도(Y)가 높아질수록 CCA가 어떻게 달라지는지
                확인하기 위해 추가했습니다.
              </p>

              {yVsCca.length === 0 ? (
                <div className="alert">
                  아직 SAE/EN CCA 실측값이 있는 로트가 없습니다. 신뢰성 시험 데이터가 업로드되면
                  여기에 자동으로 표시됩니다.
                </div>
              ) : (
                <>
                  <div className="vif-note align-start" style={{ marginBottom: "var(--space-3)" }}>
                    📌 전체 {yVsCcaTotal}건 중 SAE·EN 규격 기준 대비 여유가 가장 적은 {yVsCca.length}건만
                    표시합니다 — 나머지는 아래 원본 데이터 화면에서 전부 확인할 수 있습니다.
                  </div>
                  <div className="table-scroll">
                  <table style={{ marginBottom: "var(--space-4)" }}>
                    <thead>
                      <tr>
                        <th>로트</th>
                        <th>형명</th>
                        <th>포화도(Y)</th>
                        <th>SAE CCA</th>
                        <th>SAE 규격</th>
                        <th>EN CCA</th>
                        <th>EN 규격</th>
                      </tr>
                    </thead>
                    <tbody>
                      {yVsCca.map((p) => {
                        const saeBadge = ccaSpecBadge(p.sae_cca_spec);
                        const enBadge = ccaSpecBadge(p.en_cca_spec);
                        return (
                          <tr key={p.lot_id}>
                            <td>{p.lot_id}</td>
                            <td>{p.model_name}</td>
                            <td>{p.retention_rate.toFixed(1)}%</td>
                            <td>{p.sae_cca !== null ? p.sae_cca.toFixed(3) : "—"}</td>
                            <td>
                              <span className={`status-pill ${saeBadge.tone}`}>{saeBadge.label}</span>
                            </td>
                            <td>{p.en_cca !== null ? p.en_cca.toFixed(3) : "—"}</td>
                            <td>
                              <span className={`status-pill ${enBadge.tone}`}>{enBadge.label}</span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                  </div>
                  <a
                    href="/dashboard/y-vs-cca"
                    target="_blank"
                    className="insight-cta"
                    style={{ display: "inline-block", marginBottom: "var(--space-4)" }}
                  >
                    전체 {yVsCcaTotal}건 원본 데이터 보기(새 창) →
                  </a>
                  <div className="vif-note align-start">
                    📐 EN/SAE 규격: EN CCA는 10초 전압 ≥7.5V·6.0V까지 지속시간 ≥90초, SAE CCA는
                    7.2V까지 지속시간 ≥30초를 만족해야 합격입니다(형명 무관 고정 기준).
                  </div>
                </>
              )}

              <button
                className="btn btn-secondary"
                onClick={handleRunCca}
                disabled={ccaRunning}
                style={{ marginTop: "var(--space-4)" }}
              >
                {ccaRunning ? "시도 중..." : "SAE·EN CCA 회귀 시도"}
              </button>
              {ccaResults.xy_to_sae_cca ? (
                <div className="vif-note align-start" style={{ marginTop: "var(--space-3)" }}>
                  ✅ SAE CCA 회귀 성공(표본 {ccaResults.xy_to_sae_cca.n}건, R² {ccaResults.xy_to_sae_cca.r_squared.toFixed(3)})
                </div>
              ) : ccaNote.xy_to_sae_cca && (
                <div className="vif-note align-start" style={{ marginTop: "var(--space-3)" }}>
                  SAE CCA: {ccaNote.xy_to_sae_cca}
                </div>
              )}
              {ccaResults.xy_to_en_cca ? (
                <div className="vif-note align-start">
                  ✅ EN CCA 회귀 성공(표본 {ccaResults.xy_to_en_cca.n}건, R² {ccaResults.xy_to_en_cca.r_squared.toFixed(3)})
                </div>
              ) : ccaNote.xy_to_en_cca && (
                <div className="vif-note align-start">EN CCA: {ccaNote.xy_to_en_cca}</div>
              )}
            </div>
          </div>
        </details>
      )}

      {xToY && (
        <details className="evidence">
          <summary>
            <span className="summary-tag">원인</span> SPEC 판정 & 원인진단 · 미매칭 로트 일괄 예측
            <span className="summary-hint">Day 3 — Y/Z SPEC 판정과 조건 시뮬레이션은 예측 화면에서</span>
          </summary>
          <div className="evidence-body">
            <div className="card">
              {specCompliance && specCompliance.models_with_spec > 0 ? (
                <p style={{ margin: "0 0 var(--space-4)", fontSize: "0.875rem", lineHeight: 1.6 }}>
                  현재 SPEC이 설정된 형명 <b>{specCompliance.models_with_spec}개</b> 기준으로, 지금까지
                  실제로 확보된 값(실측/직접계산) 중 포화도(Y)는 <b>{specCompliance.y_evaluated}건</b>{" "}
                  평가해 <b>{specCompliance.y_fail}건</b>이 SPEC 미달, 20시간 용량(Z)은{" "}
                  <b>{specCompliance.z_evaluated}건</b> 평가해 <b>{specCompliance.z_fail}건</b>이 SPEC
                  미달로 확인됐습니다.
                </p>
              ) : (
                <p style={{ margin: "0 0 var(--space-4)", fontSize: "0.875rem", lineHeight: 1.6 }}>
                  아직 업로드된 로트가 없어 양품/부적합을 판정할 수 없습니다. 데이터가 들어오면
                  포화도(Y) 90%·20시간 용량(Z) 95% 기준(전 형명 공통)으로 바로 판정됩니다 — 형명별로
                  다른 기준이 필요하면 <code>templates/spec_thresholds_template.csv</code>로 개별
                  override할 수 있습니다.
                </p>
              )}
              <p style={{ margin: "0 0 var(--space-4)", fontSize: "0.875rem", lineHeight: 1.6 }}>
                특정 로트·조건에 대한 상세 원인진단(어떤 공정인자가 SPEC 미달의 원인인지)과, 시험 미실시
                로트 전체에 대한 Y·Z 일괄 예측은 <b>예측 화면</b>에서 확인할 수 있습니다 — 1단·2단
                회귀모델이 먼저 학습되어 있어야 합니다(위에서 이미 실행됨).
              </p>
              <Link href="/prediction" className="btn btn-primary">
                예측 화면으로 이동 →
              </Link>
            </div>
          </div>
        </details>
      )}

      {loaded && (
        <details className="evidence">
          <summary>
            <span className="summary-tag">검증</span> 채점 — 예측이 실측과 얼마나 맞는지
            <span className="summary-hint">
              튜터 조언(.docs/23) 반영 — 성공 기준: SPEC 판정 일치, 90% 이상이면 &ldquo;신뢰
              가능&rdquo;
            </span>
          </summary>
          <div className="evidence-body" id="scoring-detail">
            <div className="card">
              <p style={{ margin: "0 0 var(--space-4)", fontSize: "0.875rem", lineHeight: 1.6 }}>
                시험 매칭 로트(실측값이 있는 로트) 전체로 회귀를 다시 학습해, 그 로트들에 대해 예측한
                SPEC 판정이 실측 SPEC 판정과 같은지 비교합니다. 데이터를 새로 업로드한 뒤{" "}
                <b>&ldquo;다시 채점&rdquo;</b>을 누르면 지금 들어있는 데이터 기준으로 재계산됩니다.
                (학습에 쓴 로트를 그대로 다시 채점하는 방식이라 참고용 자가진단이며, 정식 검증은 v2
                예정입니다.)
              </p>

              <table style={{ marginBottom: "var(--space-4)" }}>
                <thead>
                  <tr>
                    <th>대상</th>
                    <th>대상 건수</th>
                    <th>일치율</th>
                    <th>신뢰 가능?</th>
                    <th>불일치(실패) 건수</th>
                  </tr>
                </thead>
                <tbody>
                  {SCORING_TARGETS.map(({ key, label }) => {
                    const r = scoring[key];
                    const tone: "pass" | "fail" | "unknown" =
                      r?.reliable === true ? "pass" : r?.reliable === false ? "fail" : "unknown";
                    const badgeLabel =
                      r?.reliable === true ? "신뢰 가능" : r?.reliable === false ? "미달" : "판정 불가";
                    return (
                      <tr key={key}>
                        <td>{label}</td>
                        <td>{r ? `${r.n_scorable} / ${r.n_total}` : "—"}</td>
                        <td>{r?.success_rate_pct !== null && r?.success_rate_pct !== undefined ? `${r.success_rate_pct.toFixed(1)}%` : "—"}</td>
                        <td>
                          <span className={`status-pill ${tone}`}>{badgeLabel}</span>
                        </td>
                        <td>{r ? r.n_mismatched : "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              {SCORING_TARGETS.some(({ key }) => scoring[key]?.note) && (
                <div className="vif-note align-start" style={{ marginBottom: "var(--space-4)" }}>
                  📌{" "}
                  {SCORING_TARGETS.filter(({ key }) => scoring[key]?.note)
                    .map(({ key, label }) => `${label}: ${scoring[key]?.note}`)
                    .join(" · ")}
                </div>
              )}

              <button
                className="btn btn-secondary"
                onClick={handleRunScoring}
                disabled={scoringRunning}
              >
                {scoringRunning ? "채점 중..." : "다시 채점"}
              </button>
            </div>
          </div>
        </details>
      )}
        </div>
      </details>

      <div className="foot-note">
        전 구간 로컬 처리, 외부 전송 없음. 수치는 실제 업로드된 데이터로 즉시 재계산됩니다.
      </div>
    </div>
  );
}
