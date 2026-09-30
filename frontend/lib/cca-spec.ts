import type { CcaSpecJudgment } from "@/lib/api-client";

/** EN/SAE CCA 규격(형명 무관 고정 기준, history/20) 판정 배지 표시용 — 대시보드·상세분석 공통. */
export function ccaSpecBadge(
  spec: CcaSpecJudgment
): { label: string; tone: "pass" | "fail" | "unknown" } {
  if (spec.result === "pass") return { label: "합격", tone: "pass" };
  if (spec.result === "fail") return { label: "불합격", tone: "fail" };
  return { label: spec.note ?? "판정 불가", tone: "unknown" };
}

/** CCA 합격률(%) 계산 — evaluated=0(아직 시험 데이터 없음)이면 계산 자체가 의미 없어 null.
 * `/detail-analysis`의 게이지 표시·표 셀 표기가 이 나눗셈과 0건 가드를 각자 다시 구현하고
 * 있었다(반올림 규칙이 바뀌면 두 곳을 같이 고쳐야 하는 문제). */
export function ccaPassRate(pass: number, evaluated: number): number | null {
  if (evaluated === 0) return null;
  return (pass / evaluated) * 100;
}
