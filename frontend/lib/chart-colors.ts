/** Recharts에 넘길 색상 리터럴 — SVG 프레젠테이션 속성(`fill`/`stroke`)은 브라우저에 따라
 * `var(--token)`을 안정적으로 해석하지 못하는 경우가 있어, `frontend/lib/theme.css`의 값을
 * 그대로 복제해 둔다(두 파일이 어긋나지 않도록 값 변경 시 함께 수정할 것).
 *
 * 카테고리 순서(dark-gray → green → orange → gray-400)는 `docs/design.md` §5 데이터
 * 시각화 규칙 그대로 — 이 앱의 막대는 "여러 이름의 항목을 구분"하는 진짜 categorical이
 * 아니라 부호(+/-)나 상태(양품/부적합/판정불가)를 나타내므로, `dataviz` 스킬의 8색
 * categorical 검증 대상이 아니라 status 팔레트로 취급한다(2026-09-27 검증 확인). */
export const CHART_COLORS = {
  darkGray: "#333F48",
  green700: "#006A76",
  orange: "#EB3300",
  gray400: "#B5BBBD",
  gray300: "#C7CCCE",
  border: "#D0D0CE",
  surface: "#FBFBFB",
  textSecondary: "#5C656D",
  textPrimary: "#333F48",
} as const;

/** 상태 3분류(양품/부적합/판정불가) 공용 색상 — GroupBarChart류에서 재사용. */
export const STATUS_COLORS = {
  pass: CHART_COLORS.green700,
  fail: CHART_COLORS.orange,
  unknown: CHART_COLORS.gray400,
} as const;

/** Recharts `<Tooltip cursor={{ fill: ... }}>` 호버 배경 — darkGray(#333F48)의 5% 알파를 손으로
 * 계산해 3개 차트 컴포넌트에 각각 하드코딩하고 있던 것. 팔레트가 바뀌면 여기 한 곳만 고치면 됨. */
export const CHART_TOOLTIP_CURSOR_FILL = "rgba(51,63,72,0.05)";
