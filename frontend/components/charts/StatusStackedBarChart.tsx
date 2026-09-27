"use client";

import { Bar, BarChart, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { STATUS_COLORS, CHART_COLORS } from "@/lib/chart-colors";
import { ChartTooltipBox } from "./ChartTooltip";

export interface StatusBarDatum {
  key: string;
  count: number;
  pass: number;
  fail: number;
  unknown: number;
}

interface ChartRow extends StatusBarDatum {
  passPct: number;
  failPct: number;
  unknownPct: number;
  isToday: boolean;
  countLabel: string;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any -- Recharts YAxis tick 렌더 prop 타입
function CategoryTick(props: any) {
  const { x, y, payload, todayRowKey } = props;
  const label = String(payload?.value ?? "");
  const isToday = label === todayRowKey;
  return (
    <text x={x} y={y} dy={4} textAnchor="end" fontSize={12} fill={CHART_COLORS.textPrimary}>
      {isToday && (
        <tspan fill={CHART_COLORS.green700} fontWeight={700}>
          [오늘]{" "}
        </tspan>
      )}
      <tspan>{label}</tspan>
    </text>
  );
}

function StatusTooltip({ active, payload }: { active?: boolean; payload?: { payload: ChartRow }[] }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <ChartTooltipBox>
      <div style={{ fontWeight: 700, marginBottom: 4 }}>
        {d.key}
        {d.isToday && " (오늘)"}
      </div>
      <div>
        <b>{d.count}</b>건 중 양품 {d.pass} · 부적합 {d.fail} · 판정불가 {d.unknown}
      </div>
    </ChartTooltipBox>
  );
}

/** 형명별/바이어별/날짜별 판정 분포(양품/부적합/판정불가) 100% 누적 막대 — 기존
 * `GroupBarChart`(div+flexGrow 직접 구현)를 Recharts로 교체(2026-09-27, `.docs/33`). 막대는
 * 항상 행 폭 전체를 채우고 내부 비율만 다르다(원래 컴포넌트와 동일한 "정규화된" 막대라서, 실제
 * 건수가 아니라 %를 도메인으로 쓴다 — 정확한 건수는 툴팁·라벨로 보여준다). 클릭하면 그 그룹으로
 * 드릴다운(기존 동작 유지). */
export function StatusStackedBarChart({
  bars,
  selectedKey,
  onSelect,
  todayKey,
}: {
  bars: StatusBarDatum[];
  selectedKey: string;
  onSelect: (key: string) => void;
  todayKey?: string;
}) {
  const rows: ChartRow[] = bars.map((b) => ({
    ...b,
    passPct: b.count ? (b.pass / b.count) * 100 : 0,
    failPct: b.count ? (b.fail / b.count) * 100 : 0,
    unknownPct: b.count ? (b.unknown / b.count) * 100 : 0,
    isToday: !!todayKey && b.key === todayKey,
    countLabel: `${b.count}건${b.fail > 0 ? ` · 부적합 ${b.fail}` : ""}`,
  }));
  const rowHeight = 36;
  const height = rows.length * rowHeight + 24;
  const todayRowKey = rows.find((r) => r.isToday)?.key;

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        data={rows}
        layout="vertical"
        margin={{ top: 4, right: 100, bottom: 4, left: 4 }}
        barCategoryGap={8}
        onClick={(state) => {
          const key = typeof state?.activeLabel === "string" ? state.activeLabel : undefined;
          if (key) onSelect(selectedKey === key ? "" : key);
        }}
      >
        <XAxis type="number" domain={[0, 100]} hide />
        <YAxis
          type="category"
          dataKey="key"
          width={110}
          tickLine={false}
          axisLine={false}
          tick={<CategoryTick todayRowKey={todayRowKey} />}
        />
        <Tooltip content={<StatusTooltip />} cursor={{ fill: "rgba(51,63,72,0.05)" }} />
        <Bar
          dataKey="passPct"
          stackId="s"
          fill={STATUS_COLORS.pass}
          stroke="#fff"
          strokeWidth={2}
          maxBarSize={22}
          isAnimationActive={false}
          cursor="pointer"
        />
        <Bar
          dataKey="failPct"
          stackId="s"
          fill={STATUS_COLORS.fail}
          stroke="#fff"
          strokeWidth={2}
          maxBarSize={22}
          isAnimationActive={false}
          cursor="pointer"
        />
        <Bar
          dataKey="unknownPct"
          stackId="s"
          fill={STATUS_COLORS.unknown}
          stroke="#fff"
          strokeWidth={2}
          maxBarSize={22}
          isAnimationActive={false}
          cursor="pointer"
        >
          <LabelList
            dataKey="countLabel"
            position="right"
            style={{ fontSize: 12, fontWeight: 600, fill: CHART_COLORS.textSecondary }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
