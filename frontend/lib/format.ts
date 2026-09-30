/** 숫자 포맷터 — dashboard/prediction/detail-analysis(+lots 상세)/y-vs-cca 5개 화면에 거의
 * 동일하게 복붙돼 있던 것(기본 자릿수만 2/1/1/1/3으로 제각각)을 하나로 합침. 화면마다 기본
 * 자릿수가 다르면 호출부에서 digits를 명시적으로 넘긴다. */
export function fmt(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v.toFixed(digits);
}

/** 부호 있는 값(회귀계수·편차 등)을 "+0.123"처럼 항상 부호를 붙여 표시한다. */
export function fmtSigned(v: number): string {
  return `${v >= 0 ? "+" : ""}${v.toFixed(3)}`;
}
