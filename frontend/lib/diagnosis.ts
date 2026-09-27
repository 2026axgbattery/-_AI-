import type { SpecJudgmentResult } from "@/lib/api-client";

/** 1단 X셋(`backend/analysis/regression.py`의 `X_COLUMNS`) 한국어 라벨 — `/prediction`·
 * `/detail-analysis`의 원인진단(`CauseFactor`) 표시에서 공통으로 쓴다. */
export const X_COLUMN_LABELS: Record<string, string> = {
  electrolyte_temp: "전해액온도 (℃)",
  tank_temp: "수조온도 (℃)",
  soaking_time_sec: "함침시간 (초)",
  aging_days: "에이징일수",
  formation_dv: "화성전압차 (2차-1차, V)",
  cell_weight_mean: "셀중량 평균 (g)",
  cell_weight_std: "셀중량 표준편차 (g)",
  charge_ratio: "충전율 (정격 대비 %)",
  charge_program_deviation_pct: "충전 프로그램 이탈도 (기준 대비 %)",
};
export const X_COLUMN_ORDER = Object.keys(X_COLUMN_LABELS);

export function specBadge(spec: SpecJudgmentResult): { label: string; tone: "pass" | "fail" | "unknown" } {
  if (spec.spec_result === "pass") return { label: "양품 (SPEC 충족)", tone: "pass" };
  if (spec.spec_result === "fail") return { label: "부적합 (SPEC 미달)", tone: "fail" };
  return { label: spec.note ?? "판정 불가", tone: "unknown" };
}
