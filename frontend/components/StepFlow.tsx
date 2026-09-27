import { Fragment } from "react";
import Link from "next/link";

/** 4개 화면 공용 흐름 인디케이터(① 업로드 → ② 결과 확인 → ③ 상세 조회 → ④ 예측).
 *
 * 이전에는 각 화면(`/dashboard`·`/detail-analysis`·`/prediction`)이 이 마크업을 그대로
 * 복사해 붙여넣고 있었는데, 그 결과 두 가지 문제가 있었다 — (1) 예측 화면으로 가는 흐름이
 * 전혀 표시되지 않았고(①②③까지만 존재), (2) `/prediction` 페이지의 복사본은 활성 단계
 * 라벨을 "③ 상세 조회"로 잘못 남겨둔 채였다(실제로는 예측 화면인데도). 이 컴포넌트로 단일화해
 * 두 문제를 한 번에 고친다(2026-09-27, `.docs/31`). */
const STEP_DEFS = [
  { key: "upload", href: "/upload", label: "① 업로드" },
  { key: "dashboard", href: "/dashboard", label: "② 결과 확인" },
  { key: "detail", href: "/detail-analysis", label: "③ 상세 조회" },
  { key: "prediction", href: "/prediction", label: "④ 예측" },
] as const;

export type StepKey = (typeof STEP_DEFS)[number]["key"];

export function StepFlow({ current }: { current: StepKey }) {
  const currentIndex = STEP_DEFS.findIndex((s) => s.key === current);
  return (
    <div className="steps">
      {STEP_DEFS.map((step, i) => (
        <Fragment key={step.key}>
          {i > 0 && <span className="step-sep" />}
          {i === currentIndex ? (
            <span className="step active">
              <span className="step-num">{i + 1}</span> {step.label} (지금 여기)
            </span>
          ) : (
            <Link href={step.href} className={`step${i < currentIndex ? " done" : ""}`}>
              <span className="step-num">{i < currentIndex ? "✓" : i + 1}</span> {step.label}
            </Link>
          )}
        </Fragment>
      ))}
    </div>
  );
}
