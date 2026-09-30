"use client";

import { useEffect, useRef, useState } from "react";

/** `docs/design.md` 모션 토큰 — 마이크로 인터랙션(150~200ms)보다 조금 긴, 결과가 눈에 들어오는
 * "임팩트" 등장 애니메이션에 쓰는 지속시간·이징(.docs/35, 2026-09-30). */
export const IMPACT_DURATION_MS = 900;
export const IMPACT_EASING = "ease-out"; // Recharts는 cubic-bezier 문자열도 받지만 표준 키워드로 통일

function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

/** SSR에서는 `window`가 없어 항상 false(애니메이션 있음 가정)로 초기화되고, 클라이언트
 * 마운트 시 lazy initializer(렌더 중 실행, effect 아님)로 실제 값을 즉시 반영한다 — effect
 * 본문에서 곧장 setState를 부르면 `react-hooks/set-state-in-effect` 린트 규칙을 위반한다
 * (2026-09-26 세션 복원 작업 때도 같은 규칙을 이미 한 번 맞춘 적 있음, CLAUDE.md 참조). */
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() =>
    typeof window === "undefined" ? false : window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
  useEffect(() => {
    const mql = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setReduced(mql.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);
  return reduced;
}

/** 값이 로드/변경될 때마다 이전 값(최초는 0)에서 목표값까지 부드럽게 올라가는 카운트업.
 * `components/BatteryGauge.tsx`의 배터리 채움 애니메이션과 같은 로직(ease-out cubic,
 * prefers-reduced-motion 존중)을 순수 숫자 표시에도 재사용할 수 있도록 훅으로 분리했다
 * (.docs/35) — 대시보드 히어로·예측 결과 카드처럼 "결과가 나올 때 눈에 띄어야 하는" 핵심
 * 숫자에만 선별 적용한다(모든 KPI에 걸면 클러터가 된다는 게 .docs/33에서 이미 내린 결론).
 */
export function useCountUp(target: number | null, durationMs = IMPACT_DURATION_MS): number | null {
  const [display, setDisplay] = useState<number | null>(target);
  const prevTarget = useRef<number | null>(null);
  const reduceMotion = usePrefersReducedMotion();

  useEffect(() => {
    // 아래 세 분기는 effect 본문에서 setState를 곧장 부르면 안 되는 케이스(값 없음/모션
    // 비활성/변화 없음)라 한 틱 미룬다(queueMicrotask) — 실제 rAF 루프 안의 setDisplay는
    // 비동기 콜백이라 이 규칙 대상이 아니다(BatteryGauge.tsx의 기존 패턴과 동일).
    if (target === null) {
      queueMicrotask(() => setDisplay(null));
      prevTarget.current = null;
      return;
    }
    if (reduceMotion) {
      queueMicrotask(() => setDisplay(target));
      prevTarget.current = target;
      return;
    }
    const from = prevTarget.current ?? 0;
    prevTarget.current = target;
    if (from === target) {
      queueMicrotask(() => setDisplay(target));
      return;
    }
    let raf = 0;
    let start: number | null = null;
    const step = (ts: number) => {
      if (start === null) start = ts;
      const p = Math.min((ts - start) / durationMs, 1);
      const eased = easeOutCubic(p);
      setDisplay(from + (target - from) * eased);
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, durationMs, reduceMotion]);

  return display;
}
