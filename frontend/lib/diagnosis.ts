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

/** `/prediction` 조건 시뮬레이션의 입력 예시값 — 실제 `process_data.csv`/파생값 범위를 참고한
 * 대표값(모델·로트마다 실제 값은 다르다, 어디까지나 "감이 안 잡히는 첫 사용자"를 위한 출발점).
 * 이전에는 모든 필드가 `placeholder="예: 31.2"`로 동일해 필드별 자릿수 감이 전혀 안 잡혔다
 * (예: 에이징일수·충전 프로그램 이탈도까지 "31.2"로 표시됨, 2026-09-27 실사용 확인). */
export const X_COLUMN_EXAMPLES: Record<string, number> = {
  electrolyte_temp: 34.5,
  tank_temp: 37.0,
  soaking_time_sec: 80,
  aging_days: 6,
  formation_dv: -0.05,
  cell_weight_mean: 4.7,
  cell_weight_std: 0.15,
  charge_ratio: 118,
  charge_program_deviation_pct: -80,
};

export function specBadge(spec: SpecJudgmentResult): { label: string; tone: "pass" | "fail" | "unknown" } {
  if (spec.spec_result === "pass") return { label: "양품 (SPEC 충족)", tone: "pass" };
  if (spec.spec_result === "fail") return { label: "부적합 (SPEC 미달)", tone: "fail" };
  return { label: spec.note ?? "판정 불가", tone: "unknown" };
}
