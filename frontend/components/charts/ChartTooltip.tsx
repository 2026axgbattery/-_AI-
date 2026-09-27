import { CHART_COLORS } from "@/lib/chart-colors";

/** Recharts 차트 전체가 공유하는 호버 툴팁 — dataviz 스킬의 "값이 먼저, 라벨은 다음"
 * 원칙대로 값을 굵게, 계열/카테고리명을 보조로 둔다. */
export function ChartTooltipBox({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        background: "#fff",
        border: `1px solid ${CHART_COLORS.border}`,
        borderRadius: 8,
        padding: "8px 12px",
        fontSize: 13,
        color: CHART_COLORS.textPrimary,
        boxShadow: "0 2px 8px rgba(51,63,72,0.12)",
        lineHeight: 1.5,
      }}
    >
      {children}
    </div>
  );
}
