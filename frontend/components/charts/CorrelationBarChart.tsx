"use client";

import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CHART_COLORS, CHART_TOOLTIP_CURSOR_FILL } from "@/lib/chart-colors";
import { IMPACT_DURATION_MS, IMPACT_EASING, usePrefersReducedMotion } from "@/lib/useMotion";
import { ChartTooltipBox } from "./ChartTooltip";

export interface CorrelationBarDatum {
  key: string;
  label: string;
  /** 실제 상관계수(부호 있음) — 막대 길이는 |r|, 막대 색은 부호로 나타낸다. */
  r: number;
  strengthLabel: string;
  significant: boolean;
}

interface ChartRow extends CorrelationBarDatum {
  absR: number;
  displayValue: string;
}

function CorrelationTooltip({ active, payload }: { active?: boolean; payload?: { payload: ChartRow }[] }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <ChartTooltipBox>
      <div style={{ fontWeight: 700, marginBottom: 4 }}>{d.label}</div>
      <div>
        r = <b>{d.r.toFixed(3)}</b>
        {!d.significant && " †"} · {d.strengthLabel}
      </div>
    </ChartTooltipBox>
  );
}

/** 상관계수 막대(|r| 기준, 색=부호) — 기존 `.heat-row` div 막대를 Recharts로 교체(2026-09-27,
 * `.docs/33`). 양(+)은 그린(주목할 만한 관계), 음(-)은 그레이로 표시하는 기존 색 관례를 그대로
 * 따른다 — 상관 부호 자체는 "좋고 나쁨"이 아니라서 오렌지/그린 동시강조 금지 규칙과는 무관. */
export function CorrelationBarChart({ data }: { data: CorrelationBarDatum[] }) {
  const reduceMotion = usePrefersReducedMotion();
  const rows: ChartRow[] = data.map((d) => ({
    ...d,
    absR: Math.abs(d.r),
    displayValue: `${d.r.toFixed(2)}${d.significant ? "" : "†"}`,
  }));
  const rowHeight = 40;
  const height = rows.length * rowHeight + 16;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 48, bottom: 4, left: 4 }} barCategoryGap={10}>
        <XAxis type="number" domain={[0, 1]} hide />
        <YAxis
          type="category"
          dataKey="label"
          width={132}
          tickLine={false}
          axisLine={false}
          tick={{ fontSize: 12, fill: CHART_COLORS.textPrimary }}
        />
        <Tooltip content={<CorrelationTooltip />} cursor={{ fill: CHART_TOOLTIP_CURSOR_FILL }} />
        <Bar
          dataKey="absR"
          radius={[4, 4, 4, 4]}
          maxBarSize={16}
          isAnimationActive={!reduceMotion}
          animationDuration={IMPACT_DURATION_MS}
          animationEasing={IMPACT_EASING}
        >
          {rows.map((d) => (
            <Cell key={d.key} fill={d.r < 0 ? CHART_COLORS.gray400 : CHART_COLORS.green700} />
          ))}
          <LabelList
            dataKey="displayValue"
            position="right"
            style={{ fontSize: 12, fontWeight: 600, fill: CHART_COLORS.textSecondary }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
