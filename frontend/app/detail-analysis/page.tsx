"use client";

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { TopBar } from "@/components/TopBar";
import { StepFlow } from "@/components/StepFlow";
import { BatteryGauge } from "@/components/BatteryGauge";
import { TrendLineChart } from "@/components/charts/TrendLineChart";
import { CausesList } from "@/components/CausesList";
import {
  apiClient,
  type FailingLotsResponse,
  type ModelLotsResponse,
  type ModelSummaryRow,
  type ModelsSummaryResponse,
  type ModelTrendResponse,
} from "@/lib/api-client";
import { extractBuyerCode } from "@/lib/buyer";
import { ccaSpecBadge } from "@/lib/cca-spec";
import { specBadge } from "@/lib/diagnosis";

type Period = "day" | "month" | "year";
type Scope = "all" | "model" | "buyer";

interface ScopeStats {
  label: string;
  sub: string;
  lot_count: number;
  matched_count: number;
  avg_retention_rate: number | null;
  avg_capacity_rate: number | null;
  sample_sufficient: boolean;
  en_cca_pass: number;
  en_cca_evaluated: number;
  sae_cca_pass: number;
  sae_cca_evaluated: number;
}

/** 선택 범위(전체/형명별/바이어별)에 해당하는 형명 행들을 로트 수 가중평균으로 재집계 —
 * 새 회귀·백엔드 호출 없이 이미 받아온 `GET /api/models/summary` 응답만으로 계산한다(history/28). */
function aggregateModels(rows: ModelSummaryRow[], minSample: number, label: string, sub: string): ScopeStats {
  let lot_count = 0;
  let matched_count = 0;
  let ySum = 0;
  let yWeight = 0;
  let zSum = 0;
  let zWeight = 0;
  let en_cca_pass = 0;
  let en_cca_evaluated = 0;
  let sae_cca_pass = 0;
  let sae_cca_evaluated = 0;
  for (const m of rows) {
    lot_count += m.lot_count;
    matched_count += m.matched_count;
    if (m.avg_retention_rate !== null) {
      ySum += m.avg_retention_rate * m.lot_count;
      yWeight += m.lot_count;
    }
    if (m.avg_capacity_rate !== null) {
      zSum += m.avg_capacity_rate * m.matched_count;
      zWeight += m.matched_count;
    }
    en_cca_pass += m.en_cca_pass;
    en_cca_evaluated += m.en_cca_evaluated;
    sae_cca_pass += m.sae_cca_pass;
    sae_cca_evaluated += m.sae_cca_evaluated;
  }
  return {
    label,
    sub,
    lot_count,
    matched_count,
    avg_retention_rate: yWeight > 0 ? ySum / yWeight : null,
    avg_capacity_rate: zWeight > 0 ? zSum / zWeight : null,
    sample_sufficient: lot_count >= minSample,
    en_cca_pass,
    en_cca_evaluated,
    sae_cca_pass,
    sae_cca_evaluated,
  };
}

function fmt(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v.toFixed(digits);
}

/** CCA 합격률을 Y/Z와 동일한 배터리 게이지로 표현하기 위한 값 변환 — evaluated=0이면 시험 데이터 자체가 없는 것. */
function ccaGaugeStats(pass: number, evaluated: number): { value: number | null; statusText: string; variant: "ok" | "warn" } {
  if (evaluated === 0) return { value: null, statusText: "아직 시험 데이터 없음", variant: "ok" };
  const rate = (pass / evaluated) * 100;
  return {
    value: rate,
    statusText: `시험 매칭 ${evaluated}건 중 ${pass}건 합격`,
    variant: rate >= 90 ? "ok" : "warn",
  };
}

/** 형명별 상세 테이블(Z 컬럼과 동일한 형식)의 CCA 합격률 셀 표기. */
function ccaCellText(pass: number, evaluated: number): string {
  if (evaluated === 0) return "—";
  const rate = (pass / evaluated) * 100;
  return `${pass}/${evaluated}건 (${rate.toFixed(1)}%)`;
}

function TrendChart({ points }: { points: ModelTrendResponse["points"] }) {
  if (points.length === 0) {
    return <div className="trend-empty">해당 조건의 추이 데이터가 없습니다.</div>;
  }
  if (points.length === 1) {
    return (
      <div className="trend-empty">
        데이터가 1개 구간뿐이라 추이를 그릴 수 없습니다 — {points[0].period} 평균{" "}
        {fmt(points[0].avg_retention_rate)}% (n={points[0].n})
      </div>
    );
  }
  return <TrendLineChart points={points} />;
}

export default function DetailAnalysisPage() {
  const [summary, setSummary] = useState<ModelsSummaryResponse | null>(null);
  const [selectedModel, setSelectedModel] = useState<string>("all");
  const [period, setPeriod] = useState<Period>("month");
  const [trend, setTrend] = useState<ModelTrendResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedModel, setExpandedModel] = useState<string | null>(null);
  const [activeSort, setActiveSort] = useState<"recent" | "tested_first">("recent");
  const [lotData, setLotData] = useState<Record<string, ModelLotsResponse>>({});
  const [lotLoading, setLotLoading] = useState<string | null>(null);
  const [failingLots, setFailingLots] = useState<FailingLotsResponse | null>(null);
  const [expandedFailingLot, setExpandedFailingLot] = useState<string | null>(null);
  const [scope, setScope] = useState<Scope>("all");
  const [scopeModel, setScopeModel] = useState<string>("");
  const [scopeBuyer, setScopeBuyer] = useState<string>("");

  const toggleModelLots = useCallback(
    (modelName: string, sortMode: "recent" | "tested_first") => {
      if (expandedModel === modelName && activeSort === sortMode) {
        setExpandedModel(null);
        return;
      }
      setExpandedModel(modelName);
      setActiveSort(sortMode);
      const key = `${modelName}:${sortMode}`;
      if (!lotData[key]) {
        setLotLoading(key);
        apiClient
          .getModelLots(modelName, { sort: sortMode })
          .then((data) => setLotData((prev) => ({ ...prev, [key]: data })))
          .finally(() => setLotLoading((cur) => (cur === key ? null : cur)));
      }
    },
    [expandedModel, activeSort, lotData]
  );

  useEffect(() => {
    apiClient
      .getModelsSummary()
      .then((data) => {
        setSummary(data);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    // 형명 <select>를 빠르게 연속 전환하면 먼저 보낸 요청이 나중에 도착할 수 있어(네트워크 지터),
    // `active` 플래그로 "이 effect가 아직 최신 선택인지" 확인한 뒤에만 반영한다 — 그러지 않으면
    // 차트가 현재 선택된 형명과 다른 이전 형명의 추이로 조용히 덮어써질 수 있다. 실패 시에도
    // 이전 차트를 그대로 둔 채 조용히 무시하지 않도록 `.catch`로 빈 배열을 채워 넣는다.
    let active = true;
    apiClient
      .getModelTrend(selectedModel, period)
      .catch(() => null)
      .then((data) => {
        if (active) setTrend(data);
      });
    return () => {
      active = false;
    };
  }, [selectedModel, period]);

  const capacityGroups = useMemo(() => {
    if (!summary) return [];
    const byCapacity = new Map<
      number,
      { modelCount: number; lotCount: number; ySum: number; yWeight: number; insufficient: number }
    >();
    for (const m of summary.models) {
      const bucket = byCapacity.get(m.rated_capacity) ?? {
        modelCount: 0,
        lotCount: 0,
        ySum: 0,
        yWeight: 0,
        insufficient: 0,
      };
      bucket.modelCount += 1;
      bucket.lotCount += m.lot_count;
      if (m.avg_retention_rate !== null) {
        bucket.ySum += m.avg_retention_rate * m.lot_count;
        bucket.yWeight += m.lot_count;
      }
      if (!m.sample_sufficient) bucket.insufficient += 1;
      byCapacity.set(m.rated_capacity, bucket);
    }
    return [...byCapacity.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([capacity, b]) => ({
        capacity,
        modelCount: b.modelCount,
        lotCount: b.lotCount,
        avgY: b.yWeight > 0 ? b.ySum / b.yWeight : null,
        insufficient: b.insufficient,
      }));
  }, [summary]);

  const buyerCodes = useMemo(() => {
    if (!summary) return [];
    const set = new Set<string>();
    for (const m of summary.models) {
      const b = extractBuyerCode(m.model_name);
      if (b) set.add(b);
    }
    return [...set].sort();
  }, [summary]);

  const effectiveScopeModel = scopeModel || summary?.models[0]?.model_name || "";
  const effectiveScopeBuyer = scopeBuyer && buyerCodes.includes(scopeBuyer) ? scopeBuyer : buyerCodes[0] || "";

  useEffect(() => {
    // SPEC 미달 로트 원인진단 섹션도 위쪽 전체/형명별/바이어별 스코프 선택을 따라간다 —
    // "형명별"로 보는 중이면 그 형명만, "바이어별"이면 그 바이어의 형명들만 걸러 다시 조회한다
    // (summary가 아직 없어 effectiveScopeModel/Buyer가 빈 문자열인 초기 렌더는 건너뜀).
    // <select>를 빠르게 전환할 때의 응답 순서 뒤바뀜은 `active` 플래그로 방지(다른 effect와 동일 패턴).
    if (!summary) return;
    let active = true;
    const opts =
      scope === "model"
        ? { modelName: effectiveScopeModel }
        : scope === "buyer"
          ? { buyerCode: effectiveScopeBuyer }
          : undefined;
    apiClient
      .getFailingLots(opts)
      .catch(() => null)
      .then((data) => {
        if (active) setFailingLots(data);
      });
    return () => {
      active = false;
    };
  }, [summary, scope, effectiveScopeModel, effectiveScopeBuyer]);

  const scopeFilterLabel =
    scope === "model" ? effectiveScopeModel : scope === "buyer" ? `${effectiveScopeBuyer} 바이어` : "";

  const focusOnModel = useCallback((modelName: string) => {
    setScope("model");
    setScopeModel(modelName);
    setSelectedModel(modelName);
  }, []);

  const scopeStats = useMemo<ScopeStats | null>(() => {
    if (!summary || summary.models.length === 0) return null;
    if (scope === "model") {
      const m = summary.models.find((x) => x.model_name === effectiveScopeModel) ?? summary.models[0];
      return aggregateModels([m], summary.min_sample_size, m.model_name, `${m.rated_capacity}Ah`);
    }
    if (scope === "buyer") {
      const rows = summary.models.filter((m) => extractBuyerCode(m.model_name) === effectiveScopeBuyer);
      return aggregateModels(
        rows,
        summary.min_sample_size,
        `${effectiveScopeBuyer || "?"} 바이어`,
        `형명 ${rows.length}개`
      );
    }
    return aggregateModels(summary.models, summary.min_sample_size, "전체", `형명 ${summary.models.length}개 전체`);
  }, [summary, scope, effectiveScopeModel, effectiveScopeBuyer]);

  return (
    <div className="app">
      <TopBar active="상세 분석" />

      <StepFlow current="detail" />

      <div className="page-head">
        <div>
          <h1>형명별 상세 분석</h1>
          <p>정격용량 6개 용량군, 35개 형명 단위로 X 인자·Y(포화도)·Z(20시간 용량)를 비교합니다.</p>
        </div>
      </div>

      {loading && <div className="alert">불러오는 중...</div>}

      {summary && scopeStats && (
        <>
          <div className="model-select-row">
            <div className="period-tabs" style={{ marginBottom: 0 }}>
              <button
                className={`period-tab${scope === "all" ? " active" : ""}`}
                onClick={() => setScope("all")}
              >
                전체
              </button>
              <button
                className={`period-tab${scope === "model" ? " active" : ""}`}
                onClick={() => setScope("model")}
              >
                형명별
              </button>
              <button
                className={`period-tab${scope === "buyer" ? " active" : ""}`}
                onClick={() => setScope("buyer")}
                disabled={buyerCodes.length === 0}
              >
                바이어별
              </button>
            </div>
            {scope === "model" && (
              <select value={effectiveScopeModel} onChange={(e) => setScopeModel(e.target.value)}>
                {summary.models.map((m) => (
                  <option key={m.model_name} value={m.model_name}>
                    {m.model_name} ({m.rated_capacity}Ah)
                  </option>
                ))}
              </select>
            )}
            {scope === "buyer" && (
              <select value={effectiveScopeBuyer} onChange={(e) => setScopeBuyer(e.target.value)}>
                {buyerCodes.map((b) => (
                  <option key={b} value={b}>
                    {b} 바이어
                  </option>
                ))}
              </select>
            )}
          </div>

          <div className="spotlight-banner">
            <div className="icon">{scopeStats.matched_count > 0 ? "✅" : "ℹ️"}</div>
            <div>
              <div className="label">{scopeStats.label} 요약 · {scopeStats.sub}</div>
              <div className="line">
                평균 포화도 <b className="pulse">{fmt(scopeStats.avg_retention_rate)}%</b> · 평균 20시간 용량{" "}
                <b className="pulse">
                  {scopeStats.avg_capacity_rate !== null ? `${fmt(scopeStats.avg_capacity_rate)}%` : "시험 데이터 없음"}
                </b>{" "}
                — 전체 로트 {scopeStats.lot_count}건 중 시험 매칭 {scopeStats.matched_count}건
                {!scopeStats.sample_sufficient ? ` (표본 ${summary.min_sample_size}건 미만 — 참고용)` : ""}
              </div>
            </div>
          </div>

          <div className="gauge-row">
            <BatteryGauge
              label={<>포화도 <span style={{ color: "var(--color-text-secondary)", fontWeight: 400 }}>(Y)</span></>}
              sub="전해액이 배터리 내부를 채운 정도"
              value={scopeStats.avg_retention_rate}
              statusText={`로트 ${scopeStats.lot_count}건 평균`}
              explain={
                <>
                  <b>포화도</b>는 배터리 내부의 빈 공간(공극)을 전해액이 얼마나 채우고 있는지 보여주는 값이에요.
                  숫자가 높을수록 전해액이 내부를 가득 채우고 있다는 뜻이고, 너무 낮으면 전해액이 부족해 방전
                  성능이 떨어질 수 있어요.
                </>
              }
            />
            <BatteryGauge
              label={<>20시간 용량 <span style={{ color: "var(--color-text-secondary)", fontWeight: 400 }}>(Z)</span></>}
              sub="정격 용량 대비 실제로 방전된 비율"
              value={scopeStats.avg_capacity_rate}
              statusText={
                scopeStats.matched_count > 0
                  ? `시험 매칭 ${scopeStats.matched_count}건 평균`
                  : "아직 시험 데이터 없음"
              }
              explain={
                <>
                  <b>20시간 용량</b>은 배터리를 20시간에 걸쳐 천천히 방전시켰을 때, 원래 설계된 정격 용량 대비
                  실제로 얼마나 방전됐는지의 비율이에요. 100%를 넘으면 정격보다 더 많은 전기를 뽑아냈다는 뜻으로,
                  설계 기준보다 튼튼하게 만들어졌다는 좋은 신호예요.
                </>
              }
            />
            <BatteryGauge
              label={<>EN CCA 합격률 <span style={{ color: "var(--color-text-secondary)", fontWeight: 400 }}>(Z3)</span></>}
              sub="EN 50342 규격 합격 로트 비율"
              value={ccaGaugeStats(scopeStats.en_cca_pass, scopeStats.en_cca_evaluated).value}
              statusText={ccaGaugeStats(scopeStats.en_cca_pass, scopeStats.en_cca_evaluated).statusText}
              variant={ccaGaugeStats(scopeStats.en_cca_pass, scopeStats.en_cca_evaluated).variant}
              explain={
                <>
                  <b>EN CCA</b>는 저온에서도 시동을 걸 수 있는 능력(저온시동전류)을 유럽 규격(EN 50342)으로
                  판정한 값이에요. 10초 전압 ≥7.5V AND 6.0V까지 지속시간 ≥90초를 만족해야 합격이며(형명 무관
                  고정 기준), 20시간 용량(Z)과 같은 방식으로 시험 매칭된 로트 중 합격 비율을 보여줘요.
                </>
              }
            />
            <BatteryGauge
              label={<>SAE CCA 합격률 <span style={{ color: "var(--color-text-secondary)", fontWeight: 400 }}>(Z2)</span></>}
              sub="SAE J537 규격 합격 로트 비율"
              value={ccaGaugeStats(scopeStats.sae_cca_pass, scopeStats.sae_cca_evaluated).value}
              statusText={ccaGaugeStats(scopeStats.sae_cca_pass, scopeStats.sae_cca_evaluated).statusText}
              variant={ccaGaugeStats(scopeStats.sae_cca_pass, scopeStats.sae_cca_evaluated).variant}
              explain={
                <>
                  <b>SAE CCA</b>는 같은 저온시동전류를 미국 규격(SAE J537)으로 판정한 값이에요. 7.2V까지
                  지속시간 ≥30초를 만족해야 합격이며(형명 무관 고정 기준), 20시간 용량(Z)과 같은 방식으로
                  시험 매칭된 로트 중 합격 비율을 보여줘요.
                </>
              }
            />
          </div>

          <div className="capacity-group-row">
            {capacityGroups.map((g) => (
              <div className="capacity-group-card" key={g.capacity}>
                <div className="cg-label">{g.capacity}Ah · 형명 {g.modelCount}개</div>
                <div className="cg-value">{fmt(g.avgY)}%</div>
                <div className="cg-label">
                  로트 {g.lotCount}건{g.insufficient > 0 ? ` · 표본부족 ${g.insufficient}개` : ""}
                </div>
              </div>
            ))}
          </div>

          <details className="evidence-toggle" style={{ marginBottom: "var(--space-6)" }} open={(failingLots?.total_count ?? 0) > 0}>
            <summary>
              SPEC 미달 로트 원인진단{scopeFilterLabel && ` — ${scopeFilterLabel}`}
              <span className="summary-sub">
                {failingLots
                  ? failingLots.total_count === 0
                    ? "실측 기준 SPEC 미달 로트 없음"
                    : `실측 기준 총 ${failingLots.total_count}건 중 이탈폭이 큰 ${failingLots.shown_count}건 표시`
                  : "불러오는 중..."}
              </span>
            </summary>
            <div className="evidence-toggle-body">
              <div className="card">
                <div className="card-head">
                  <h3>부적합(SPEC 미달) 로트 — 원인 인자 상위 3개</h3>
                  {/* scope==="all"일 때만 형명별 분포를 보여준다 — model/buyer 스코프에서는
                      위 <summary>에 이미 같은 형명/바이어가 표시되므로 중복 노출을 피한다. */}
                  {scope === "all" && failingLots && Object.keys(failingLots.by_model).length > 0 && (
                    <span className="hint">
                      {Object.entries(failingLots.by_model)
                        .map(([m, n]) => `${m} ${n}건`)
                        .join(" · ")}
                    </span>
                  )}
                </div>
                <div className="vif-note align-start">
                  🔍 <div>
                    이미 시험 완료된(실측값이 있는) 로트 중 SPEC 하한 미달인 것만 골라, 이탈폭이 큰
                    순으로 보여줍니다. 각 로트를 펼치면 1·2단 회귀계수 기준 기여도가 큰 X인자 상위 3개와
                    권고 조치를 확인할 수 있습니다(미매칭 로트 예측·원인진단은 <Link href="/prediction">예측 화면</Link>에서).
                  </div>
                </div>
                {!failingLots || failingLots.lots.length === 0 ? (
                  <div className="alert" style={{ marginTop: "var(--space-4)" }}>
                    {failingLots && !failingLots.y_run_available && !failingLots.z_run_available
                      ? "1·2단 회귀가 아직 학습되지 않아 SPEC 미달 여부를 판정할 수 없습니다 — 대시보드에서 분석을 먼저 실행하세요."
                      : "SPEC 미달 로트가 없습니다."}
                  </div>
                ) : (
                  <div className="table-scroll">
                  <table style={{ marginTop: "var(--space-4)" }}>
                    <thead>
                      <tr>
                        <th>lot_id</th>
                        {scope !== "model" && <th>형명</th>}
                        <th>Y(포화도)</th>
                        <th>Z(%)</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {failingLots.lots.map((l) => {
                        const isOpen = expandedFailingLot === l.lot_id;
                        const yBadge = specBadge(l.y.spec);
                        const zBadge = specBadge(l.z.spec);
                        const colCount = scope === "model" ? 4 : 5;
                        return (
                          <Fragment key={l.lot_id}>
                            <tr>
                              <td className="cell-lot">{l.lot_id}</td>
                              {scope !== "model" && <td>{l.model_name}</td>}
                              <td>
                                <span className={`status-pill ${yBadge.tone}`}>
                                  <span className="dot" />
                                  {fmt(l.y.value)}%
                                </span>
                              </td>
                              <td>
                                <span className={`status-pill ${zBadge.tone}`}>
                                  <span className="dot" />
                                  {fmt(l.z.value)}%
                                </span>
                              </td>
                              <td>
                                <button
                                  className="raw-data-toggle"
                                  onClick={() => setExpandedFailingLot(isOpen ? null : l.lot_id)}
                                >
                                  원인 보기 {isOpen ? "▲" : "▾"}
                                </button>
                              </td>
                            </tr>
                            {isOpen && (
                              <tr className="raw-data-row">
                                <td colSpan={colCount}>
                                  <div className="raw-data-panel">
                                    {l.y.spec.spec_result === "fail" && (
                                      <div style={{ marginBottom: "var(--space-4)" }}>
                                        <b>Y(포화도) 미달 원인 — SPEC 하한 {fmt(l.y.spec.spec_lower)}% 대비{" "}
                                          {fmt(l.y.spec.deviation)}%p</b>
                                        <CausesList causes={l.y.causes} />
                                      </div>
                                    )}
                                    {l.z.spec.spec_result === "fail" && (
                                      <div>
                                        <b>Z(20시간 용량) 미달 원인 — SPEC 하한 {fmt(l.z.spec.spec_lower)}% 대비{" "}
                                          {fmt(l.z.spec.deviation)}%p</b>
                                        <CausesList causes={l.z.causes} />
                                      </div>
                                    )}
                                  </div>
                                </td>
                              </tr>
                            )}
                          </Fragment>
                        );
                      })}
                    </tbody>
                  </table>
                  </div>
                )}
              </div>
            </div>
          </details>

          <details className="evidence-toggle" style={{ marginBottom: "var(--space-6)" }}>
            <summary>
              형명 {summary.models.length}개 전체 표로 보기
              <span className="summary-sub">
                표본 수(n) {"<"} {summary.min_sample_size}건이면 표본 부족으로 표시
              </span>
            </summary>
            <div className="evidence-toggle-body">
            <div className="card">
              <div className="card-head">
                <h3>형명별 상세 테이블</h3>
              </div>
            <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>형명</th>
                  <th>정격용량</th>
                  <th>로트 수(n)</th>
                  <th>평균 Y(포화도)</th>
                  <th>시험 매칭</th>
                  <th>평균 Z(discharge_amount)</th>
                  <th>평균 Z(%)</th>
                  <th>평균 Z2(SAE CCA 합격률)</th>
                  <th>평균 Z3(EN CCA 합격률)</th>
                </tr>
              </thead>
              <tbody>
                {summary.models.map((m) => {
                  const isExpanded = expandedModel === m.model_name;
                  const key = `${m.model_name}:${activeSort}`;
                  const lots = isExpanded ? lotData[key] : undefined;
                  return (
                    <Fragment key={m.model_name}>
                      <tr>
                        <td>
                          <button
                            className="btn-sm btn-secondary btn"
                            style={{ padding: "3px 10px" }}
                            onClick={() => focusOnModel(m.model_name)}
                          >
                            {m.model_name}
                          </button>
                        </td>
                        <td>{m.rated_capacity}Ah</td>
                        <td>
                          <button
                            className="raw-data-toggle"
                            onClick={() => toggleModelLots(m.model_name, "recent")}
                            title="이 형명의 로트별 기본 raw data를 최신순으로 보기"
                          >
                            {m.lot_count}건 {isExpanded && activeSort === "recent" ? "▲" : "▾"}
                          </button>
                          {!m.sample_sufficient && (
                            <span className="sample-badge insufficient" style={{ marginLeft: 6 }}>
                              표본 부족
                            </span>
                          )}
                        </td>
                        <td>{fmt(m.avg_retention_rate)}%</td>
                        <td>
                          {m.matched_count === 0 ? (
                            <button
                              className="raw-data-toggle"
                              onClick={() => toggleModelLots(m.model_name, "tested_first")}
                              title="이 형명의 로트별 기본 raw data를 시험 매칭된 로트 우선으로 보기"
                            >
                              <span className="badge badge-note">미시험</span>{" "}
                              {isExpanded && activeSort === "tested_first" ? "▲" : "▾"}
                            </button>
                          ) : (
                            <button
                              className="raw-data-toggle"
                              onClick={() => toggleModelLots(m.model_name, "tested_first")}
                              title="이 형명의 로트별 기본 raw data를 시험 매칭된 로트 우선으로 보기"
                            >
                              {m.matched_count}건 {isExpanded && activeSort === "tested_first" ? "▲" : "▾"}
                            </button>
                          )}
                        </td>
                        <td>{fmt(m.avg_discharge_amount)}</td>
                        <td>{fmt(m.avg_capacity_rate)}%</td>
                        <td>{ccaCellText(m.sae_cca_pass, m.sae_cca_evaluated)}</td>
                        <td>{ccaCellText(m.en_cca_pass, m.en_cca_evaluated)}</td>
                      </tr>
                      {isExpanded && (
                        <tr className="raw-data-row">
                          <td colSpan={9}>
                            {lotLoading === key && <div className="alert">불러오는 중...</div>}
                            {lots && (
                              <div className="raw-data-panel">
                                <div className="raw-data-panel-head">
                                  <span>
                                    {m.model_name} · 로트별 기본 raw data(
                                    {activeSort === "tested_first" ? "시험 매칭 우선" : "최신순"})
                                    {lots.total_count > lots.rows.length
                                      ? ` — 전체 ${lots.total_count}건 중 ${lots.rows.length}건 표시`
                                      : ` — 전체 ${lots.total_count}건`}
                                  </span>
                                  <a
                                    className="raw-data-fullview-link"
                                    href={`/detail-analysis/lots/${encodeURIComponent(m.model_name)}?sort=${activeSort}`}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                  >
                                    새 창에서 전체 {lots.total_count}건 보기 ↗
                                  </a>
                                </div>
                                <table className="raw-data-table">
                                  <thead>
                                    <tr>
                                      <th>lot_id</th>
                                      <th>생산일자</th>
                                      <th>Y(포화도)</th>
                                      <th>시험 여부</th>
                                      <th>Z(discharge_amount)</th>
                                      <th>Z(%)</th>
                                      <th>SAE CCA</th>
                                      <th>EN CCA</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {lots.rows.map((row) => {
                                      const saeBadge = ccaSpecBadge(row.sae_cca_spec);
                                      const enBadge = ccaSpecBadge(row.en_cca_spec);
                                      return (
                                        <tr key={row.lot_id}>
                                          <td className="cell-lot">{row.lot_id}</td>
                                          <td>{row.prod_date}</td>
                                          <td>{fmt(row.retention_rate)}%</td>
                                          <td>
                                            {row.has_test ? (
                                              <span className="status-pill matched">
                                                <span className="dot" />
                                                시험 완료
                                              </span>
                                            ) : (
                                              <span className="status-pill unmatched">
                                                <span className="dot" />
                                                미시험
                                              </span>
                                            )}
                                          </td>
                                          <td>{fmt(row.discharge_amount)}</td>
                                          <td>{fmt(row.capacity_rate)}%</td>
                                          <td>
                                            {row.sae_cca !== null ? (
                                              <>
                                                {row.sae_cca.toFixed(3)}{" "}
                                                <span className={`status-pill ${saeBadge.tone}`}>
                                                  {saeBadge.label}
                                                </span>
                                              </>
                                            ) : (
                                              "—"
                                            )}
                                          </td>
                                          <td>
                                            {row.en_cca !== null ? (
                                              <>
                                                {row.en_cca.toFixed(3)}{" "}
                                                <span className={`status-pill ${enBadge.tone}`}>
                                                  {enBadge.label}
                                                </span>
                                              </>
                                            ) : (
                                              "—"
                                            )}
                                          </td>
                                        </tr>
                                      );
                                    })}
                                  </tbody>
                                </table>
                              </div>
                            )}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
            </div>
            </div>
            </div>
          </details>

          <div className="section-title">
            <h2>형명별 Y(포화도) 추이</h2>
            <span className="hint">prod_date 기준 집계, 별도 학습 없는 단순 시계열 조회</span>
          </div>

          <div className="model-select-row">
            <select value={selectedModel} onChange={(e) => setSelectedModel(e.target.value)}>
              <option value="all">전체 평균</option>
              {summary.models.map((m) => (
                <option key={m.model_name} value={m.model_name}>
                  {m.model_name}
                </option>
              ))}
            </select>
            <div className="period-tabs">
              {(["day", "month", "year"] as Period[]).map((p) => (
                <button
                  key={p}
                  className={`period-tab${period === p ? " active" : ""}`}
                  onClick={() => setPeriod(p)}
                >
                  {p === "day" ? "일간" : p === "month" ? "월간" : "연간"}
                </button>
              ))}
            </div>
          </div>

          {period === "year" && trend && trend.available_years.length < 2 ? (
            <div className="trend-svg-wrap">
              <div className="trend-empty">
                아직 누적된 연도가 {trend.available_years.length}개뿐이라 연간 추이를 비교할 수
                없습니다 — 최소 2개 연도 데이터가 쌓이면 표시됩니다.
              </div>
            </div>
          ) : (
            <div className="trend-svg-wrap">
              <TrendChart points={trend?.points ?? []} />
            </div>
          )}
        </>
      )}

      <div className="foot-note">전 구간 로컬 처리, 외부 전송 없음.</div>
    </div>
  );
}
