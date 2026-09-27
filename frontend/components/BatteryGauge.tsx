"use client";

import { useEffect, useRef, type CSSProperties, type ReactNode } from "react";

const DURATION_MS = 1200;

function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

/** 게이지가 로드될 때마다(값이 바뀔 때 포함) 0%에서 실제 값까지 차오르는 애니메이션.
 * output/05_battery_impact_concept.html의 바닐라 JS 로직을 그대로 React 훅으로 옮김. */
function useFillAnimation(target: number | null) {
  const figureRef = useRef<HTMLDivElement>(null);
  const numRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const figure = figureRef.current;
    const numEl = numRef.current;
    if (!figure) return;

    figure.style.setProperty("--fill", "0%");
    if (numEl) numEl.textContent = "0.0";
    if (target === null) return;

    const gaugeTarget = Math.min(target, 100);
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (reduceMotion) {
      figure.style.setProperty("--fill", `${gaugeTarget}%`);
      if (numEl) numEl.textContent = target.toFixed(1);
      return;
    }

    let raf = 0;
    let start: number | null = null;
    const step = (ts: number) => {
      if (start === null) start = ts;
      const p = Math.min((ts - start) / DURATION_MS, 1);
      const eased = easeOutCubic(p);
      figure.style.setProperty("--fill", `${gaugeTarget * eased}%`);
      if (numEl) numEl.textContent = (target * eased).toFixed(1);
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target]);

  return { figureRef, numRef };
}

export function BatteryGauge({
  label,
  sub,
  value,
  statusText,
  variant = "ok",
  explain,
  size = 260,
}: {
  label: ReactNode;
  sub: string;
  /** null이면 "데이터 없음" 상태로 0%에 고정 표시 */
  value: number | null;
  statusText: string;
  variant?: "ok" | "warn";
  explain: ReactNode;
  size?: number;
}) {
  const { figureRef, numRef } = useFillAnimation(value);
  const overflow = value !== null && value > 100;
  const warn = variant === "warn";

  return (
    <div className="gauge-card">
      <div>
        <div className="metric-name">{label}</div>
        <div className="metric-sub">{sub}</div>
      </div>

      <div className="battery-figure" style={{ width: size }}>
        <div className={`battery-pct${warn ? " is-warn" : ""}`}>
          <span className="pulse" ref={numRef}>
            0.0
          </span>
          <span className="unit">%</span>
        </div>

        <div
          ref={figureRef}
          className={`battery-photo-figure${warn ? " is-warn" : ""}`}
          style={{ width: size, "--fill": "0%" } as CSSProperties}
        >
          {overflow && (
            <div className="battery-overflow-badge" title="기준 100%를 넘어선 값">
              +
            </div>
          )}
          <img className="battery-photo battery-photo--dim" src="/battery/battery-cutaway.svg" alt="" aria-hidden />
          <div
            className="battery-photo-clip"
            style={warn ? { filter: "sepia(1) saturate(4) hue-rotate(-30deg) brightness(0.95)" } : undefined}
          >
            <img
              className="battery-photo"
              src="/battery/battery-cutaway.svg"
              alt={`${label} ${value ?? 0}% 채움 표시`}
            />
          </div>
          <div className="battery-waterline" />
        </div>
      </div>

      <span className={`status-chip${warn ? " is-warn" : ""}`}>
        <span className="dot" />
        {statusText}
      </span>

      <div className={`explain${warn ? " is-warn" : ""}`}>{explain}</div>
    </div>
  );
}
