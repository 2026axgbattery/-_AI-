"use client";

/** 소형 원형 게이지 — 대시보드 히어로의 Y/Z/CCA 평균 지표를 숫자 텍스트만이 아니라 "그림으로
 * 바로 읽히는" 형태로도 보여주기 위해 추가(2026-09-27, `.docs/33` — 배터리 게이지(BatteryGauge)의
 * 그림 기반 표현을 히어로까지 확장해달라는 요청). 배터리 이미지는 물리적 용량(Y/Z) 은유라 좁은
 * 히어로 카드·어두운 배경에는 안 맞아, 값 자체는 링(호)으로만 표현하는 더 단순한 형태로 새로
 * 만들었다 — 색은 상태 강조를 새로 추가하지 않도록 흰색 톤 하나만 쓰고(옆의 상태 배지가 이미
 * 정상/확인필요 색을 담당), 히어로의 어두운 배경 위에서 자연스럽게 보이도록 설계했다. */
export function RadialGauge({
  value,
  size = 56,
  strokeWidth = 5,
}: {
  /** 0~100 사이 비율. null이면 데이터 없음(빈 링만 표시). */
  value: number | null;
  size?: number;
  strokeWidth?: number;
}) {
  const clamped = value === null ? 0 : Math.max(0, Math.min(100, value));
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - clamped / 100);
  const center = size / 2;

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden focusable="false">
      <circle
        cx={center}
        cy={center}
        r={radius}
        fill="none"
        stroke="rgba(255,255,255,0.18)"
        strokeWidth={strokeWidth}
      />
      {value !== null && (
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke="#fff"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${center} ${center})`}
          style={{ transition: "stroke-dashoffset 600ms ease-out" }}
        />
      )}
    </svg>
  );
}
