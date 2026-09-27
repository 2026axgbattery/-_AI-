"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CHART_COLORS } from "@/lib/chart-colors";
import { ChartTooltipBox } from "./ChartTooltip";

export interface TrendPointDatum {
  period: string;
  avg_retention_rate: number;
  n: number;
}

function TrendTooltip({ active, payload }: { active?: boolean; payload?: { payload: TrendPointDatum }[] }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <ChartTooltipBox>
      <div style={{ fontWeight: 700, marginBottom: 4 }}>{d.period}</div>
      <div>
        <b>{d.avg_retention_rate.toFixed(2)}%</b> (n={d.n})
      </div>
    </ChartTooltipBox>
  );
}

/** 형명별 Y(포화도) 추이 라인차트 — 기존 손수 그린 inline SVG polyline을 Recharts로 교체
 * (2026-09-27, `.docs/33`). 값이 1개뿐일 때의 안내 문구는 호출부(`/detail-analysis`)가 그대로
 * 담당(추이 자체가 성립하지 않는 경우라 차트 문제가 아님). */
export function TrendLineChart({ points }: { points: TrendPointDatum[] }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={points} margin={{ top: 16, right: 16, bottom: 4, left: 4 }}>
        <CartesianGrid stroke={CHART_COLORS.border} strokeDasharray="0" vertical={false} />
        <XAxis
          dataKey="period"
          tickLine={false}
          axisLine={{ stroke: CHART_COLORS.border }}
          tick={{ fontSize: 11, fill: CHART_COLORS.textSecondary }}
        />
        <YAxis
          tickLine={false}
          axisLine={false}
          width={48}
          tick={{ fontSize: 11, fill: CHART_COLORS.textSecondary }}
          tickFormatter={(v: number) => `${v.toFixed(0)}%`}
          domain={["dataMin - 1", "dataMax + 1"]}
        />
        <Tooltip
          content={<TrendTooltip />}
          cursor={{ stroke: CHART_COLORS.green700, strokeWidth: 1, strokeDasharray: "3 3" }}
        />
        <Line
          type="monotone"
          dataKey="avg_retention_rate"
          stroke={CHART_COLORS.green700}
          strokeWidth={2}
          dot={{ r: 3.5, fill: CHART_COLORS.green700, strokeWidth: 0 }}
          activeDot={{ r: 6, fill: CHART_COLORS.green700, stroke: "#fff", strokeWidth: 2 }}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
