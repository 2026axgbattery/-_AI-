import type { CauseFactor } from "@/lib/api-client";
import { X_COLUMN_LABELS } from "@/lib/diagnosis";

function fmt(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v.toFixed(digits);
}

/** SPEC 미달 원인 인자 순위(`rank_causes`) 표시 — `/prediction`(예측)·`/detail-analysis`
 * (실측)에서 동일한 시각 언어로 공유한다. */
export function CausesList({ causes }: { causes: CauseFactor[] }) {
  if (causes.length === 0) return null;
  return (
    <ol className="finding-list">
      {causes.map((c) => (
        <li className="finding-item" key={c.factor}>
          <span className="finding-num">{c.rank}</span>
          <span className="finding-body">
            <b>{X_COLUMN_LABELS[c.factor] ?? c.factor}</b> — 실측 {fmt(c.value)} (훈련 평균 {fmt(c.mean)})
            <br />
            {c.recommendation}
          </span>
        </li>
      ))}
    </ol>
  );
}
