"use client";

import { useEffect, useState } from "react";
import { TopBar } from "@/components/TopBar";
import { apiClient, type YVsCcaPair } from "@/lib/api-client";
import { ccaSpecBadge } from "@/lib/cca-spec";

// 전체 raw data를 페이지네이션 없이 한 번에 받기 위한 상한 — `detail-analysis/lots/[model]`의
// FULL_VIEW_LIMIT과 동일한 관례(2,000건 초과 시 표 렌더링이 느려지고 찌그러져 보일 수 있음).
const FULL_VIEW_LIMIT = 2000;

function fmt(v: number | null, digits = 3): string {
  return v === null ? "—" : v.toFixed(digits);
}

export default function YVsCcaFullPage() {
  const [pairs, setPairs] = useState<YVsCcaPair[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiClient
      .getYVsCca({ limit: FULL_VIEW_LIMIT, sort: "lot_id" })
      .then((result) => {
        setPairs(result.pairs);
        setTotalCount(result.total_count);
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="app">
      <TopBar active="분석 대시보드" />

      <div className="page-head">
        <div>
          <h1>포화도(Y) ↔ CCA 관계 · 전체 raw data</h1>
          <p>
            대시보드의 &ldquo;포화도(Y) ↔ CCA(저온시동전류) 관계 확인&rdquo;에서 이어진 화면입니다.
            SAE/EN CCA 실측값이 있는 로트 전체를 페이지 제한 없이 확인할 수 있습니다.
          </p>
        </div>
      </div>

      <div className="card" style={{ marginBottom: "var(--space-6)" }}>
        <div className="card-head">
          <h3>로트 목록{totalCount ? ` — 전체 ${totalCount}건 중 ${pairs.length}건 표시` : ""}</h3>
        </div>

        {loading && <div className="alert">불러오는 중...</div>}

        {!loading && pairs.length === 0 && (
          <div className="alert">SAE/EN CCA 실측값이 있는 로트가 없습니다.</div>
        )}

        {!loading && pairs.length > 0 && (
          <div className="table-scroll">
            <table className="raw-data-table" style={{ width: "100%" }}>
              <thead>
                <tr>
                  <th>로트</th>
                  <th>형명</th>
                  <th>포화도(Y)</th>
                  <th>SAE CCA</th>
                  <th>SAE 규격</th>
                  <th>EN CCA</th>
                  <th>EN 규격</th>
                </tr>
              </thead>
              <tbody>
                {pairs.map((p) => {
                  const saeBadge = ccaSpecBadge(p.sae_cca_spec);
                  const enBadge = ccaSpecBadge(p.en_cca_spec);
                  return (
                    <tr key={p.lot_id}>
                      <td className="cell-lot">{p.lot_id}</td>
                      <td>{p.model_name}</td>
                      <td>{p.retention_rate.toFixed(1)}%</td>
                      <td>{fmt(p.sae_cca)}</td>
                      <td>
                        <span className={`status-pill ${saeBadge.tone}`}>{saeBadge.label}</span>
                      </td>
                      <td>{fmt(p.en_cca)}</td>
                      <td>
                        <span className={`status-pill ${enBadge.tone}`}>{enBadge.label}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="foot-note">전 구간 로컬 처리, 외부 전송 없음.</div>
    </div>
  );
}
