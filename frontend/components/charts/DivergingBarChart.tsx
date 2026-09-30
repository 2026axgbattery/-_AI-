"use client";

import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { CHART_COLORS, CHART_TOOLTIP_CURSOR_FILL } from "@/lib/chart-colors";
import { fmtSigned } from "@/lib/format";
import { IMPACT_DURATION_MS, IMPACT_EASING, usePrefersReducedMotion } from "@/lib/useMotion";
import { ChartTooltipBox } from "./ChartTooltip";

export interface DivergingBarDatum {
  key: string;
  label: string;
  value: number;
}

function DivergingTooltip({ active, payload }: { active?: boolean; payload?: { payload: DivergingBarDatum }[] }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <ChartTooltipBox>
      <div style={{ fontWeight: 700, marginBottom: 4 }}>{d.label}</div>
      <div>{fmtSigned(d.value)}</div>
    </ChartTooltipBox>
  );
}

/** 0을 기준으로 좌우로 뻗는(diverging) 값 라벨 — 막대가 양수면 오른쪽 끝, 음수면 왼쪽 끝에
 * 붙인다(Recharts 기본 LabelList의 `position="right"`는 부호와 무관하게 한쪽에만 붙어
 * 음수 막대에서 라벨이 축 쪽에 깔려버리는 문제가 있어 직접 그린다). */
// Recharts의 `LabelList` content prop 타입(`Props`)이 x/y/width/height/value를 각각
// string|number|null 등 넓은 유니언으로 열어둬 우리 쪽 좁은 타입과 구조적으로 안 맞는다 —
// 렌더링 시점에만 쓰는 내부 콜백이라 여기서만 느슨하게 받고 즉시 숫자로 정규화한다.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function DivergingValueLabel(props: any) {
  const x = Number(props?.x ?? 0);
  const y = Number(props?.y ?? 0);
  const width = Number(props?.width ?? 0);
  const height = Number(props?.height ?? 0);
  const value = Number(props?.value ?? 0);
  const isPos = value >= 0;
  const labelX = isPos ? x + width + 6 : x - 6;
  return (
    <text
      x={labelX}
      y={y + height / 2}
      dy={4}
      textAnchor={isPos ? "start" : "end"}
      fontSize={12}
      fontWeight={600}
      fill={CHART_COLORS.textSecondary}
    >
      {fmtSigned(value)}
    </text>
  );
}

/** 회귀계수 등 0을 기준으로 양/음이 갈리는 막대 — 기존 `.coef-track`(중앙 기준선+좌우 막대) div를
 * Recharts로 교체(2026-09-27, `.docs/33`). 값 도메인이 음수~양수에 걸쳐 있으면 Recharts가 0을
 * 기준선으로 알아서 막대를 그려주므로 별도의 커스텀 shape 없이 표준 BarChart로 구현된다. */
export function DivergingBarChart({ data }: { data: DivergingBarDatum[] }) {
  const reduceMotion = usePrefersReducedMotion();
  const maxAbs = Math.max(...data.map((d) => Math.abs(d.value)), 1e-9);
  const rowHeight = 40;
  const height = data.length * rowHeight + 16;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 56, bottom: 4, left: 4 }} barCategoryGap={10}>
        <XAxis type="number" domain={[-maxAbs * 1.15, maxAbs * 1.15]} hide />
        <YAxis
          type="category"
          dataKey="label"
          width={132}
          tickLine={false}
          axisLine={false}
          tick={{ fontSize: 12, fill: CHART_COLORS.textPrimary }}
        />
        <ReferenceLine x={0} stroke={CHART_COLORS.gray300} />
        <Tooltip content={<DivergingTooltip />} cursor={{ fill: CHART_TOOLTIP_CURSOR_FILL }} />
        <Bar
          dataKey="value"
          radius={[4, 4, 4, 4]}
          maxBarSize={16}
          isAnimationActive={!reduceMotion}
          animationDuration={IMPACT_DURATION_MS}
          animationEasing={IMPACT_EASING}
        >
          {data.map((d) => (
            <Cell key={d.key} fill={d.value >= 0 ? CHART_COLORS.darkGray : CHART_COLORS.gray400} />
          ))}
          <LabelList dataKey="value" content={DivergingValueLabel} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
