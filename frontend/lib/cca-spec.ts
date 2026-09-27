import type { CcaSpecJudgment } from "@/lib/api-client";

/** EN/SAE CCA 규격(형명 무관 고정 기준, history/20) 판정 배지 표시용 — 대시보드·상세분석 공통. */
export function ccaSpecBadge(
  spec: CcaSpecJudgment
): { label: string; tone: "pass" | "fail" | "unknown" } {
  if (spec.result === "pass") return { label: "합격", tone: "pass" };
  if (spec.result === "fail") return { label: "불합격", tone: "fail" };
  return { label: spec.note ?? "판정 불가", tone: "unknown" };
}
