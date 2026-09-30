"use client";

import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { TopBar } from "@/components/TopBar";
import { apiClient, type ModelLotsResponse } from "@/lib/api-client";
import { ccaSpecBadge } from "@/lib/cca-spec";
import { fmt } from "@/lib/format";

type SortMode = "recent" | "tested_first";

// 전체 로트 raw data를 페이지네이션 없이 한 번에 받기 위한 상한. 형명당 표본 수가
// 이보다 많아지면 최신(또는 시험 매칭 우선) N건까지만 표시된다. 너무 크게 잡으면(예: 5,000건
// 이상 형명 하나에 몰린 경우) 표 렌더링 자체가 느려지고 컬럼이 찌그러져 보일 수 있어 2,000건으로
// 제한한다 — "전체 N건 중 M건 표시" 안내를 이미 화면에 보여주고 있어 사용자에게 정직하게 전달됨.
const FULL_VIEW_LIMIT = 2000;

export default function ModelLotsFullPage() {
  const params = useParams<{ model: string }>();
  const searchParams = useSearchParams();
  const modelName = decodeURIComponent(params.model);
  const initialSort: SortMode = searchParams.get("sort") === "tested_first" ? "tested_first" : "recent";

  const [sort, setSort] = useState<SortMode>(initialSort);
  const [data, setData] = useState<ModelLotsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // 정렬 토글을 빠르게 연속 클릭하면 먼저 보낸 요청이 나중에 도착할 수 있어(네트워크 지터),
    // `active` 플래그로 "이 effect가 아직 최신인지"를 확인한 뒤에만 상태를 반영한다 — 그러지
    // 않으면 화면 표는 방금 선택한 정렬과 다른, 이전 정렬 결과로 조용히 덮어써질 수 있다.
    let active = true;
    apiClient
      .getModelLots(modelName, { sort, limit: FULL_VIEW_LIMIT })
      .then((result) => {
        if (active) setData(result);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [modelName, sort]);

  return (
    <div className="app">
      <TopBar active="상세 분석" />

      <div className="page-head">
        <div>
          <h1>{modelName} · 전체 raw data</h1>
          <p>
            형명별 상세 분석에서 이어진 화면입니다. 이 형명의 로트 전체를 페이지 제한 없이
            확인할 수 있습니다.
          </p>
        </div>
      </div>

      <div className="card" style={{ marginBottom: "var(--space-6)" }}>
        <div className="card-head">
          <h3>
            로트 목록{data ? ` — 전체 ${data.total_count}건 중 ${data.rows.length}건 표시` : ""}
          </h3>
          <div className="period-tabs">
            <button
              className={`period-tab${sort === "recent" ? " active" : ""}`}
              onClick={() => setSort("recent")}
            >
              최신순
            </button>
            <button
              className={`period-tab${sort === "tested_first" ? " active" : ""}`}
              onClick={() => setSort("tested_first")}
            >
              시험 매칭 우선
            </button>
          </div>
        </div>

        {loading && <div className="alert">불러오는 중...</div>}

        {!loading && data && (
          <div className="table-scroll">
          <table className="raw-data-table" style={{ width: "100%" }}>
            <thead>
              <tr>
                <th>lot_id</th>
                <th>생산일자</th>
                <th>Y(포화도)</th>
                <th>시험 여부</th>
                <th>Z(discharge_amount)</th>
                <th>Z(%)</th>
                <th>SAE CCA</th>
                <th>EN CCA</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row) => {
                const saeBadge = ccaSpecBadge(row.sae_cca_spec);
                const enBadge = ccaSpecBadge(row.en_cca_spec);
                return (
                  <tr key={row.lot_id}>
                    <td className="cell-lot">{row.lot_id}</td>
                    <td>{row.prod_date}</td>
                    <td>{fmt(row.retention_rate)}%</td>
                    <td>
                      {row.has_test ? (
                        <span className="status-pill matched">
                          <span className="dot" />
                          시험 완료
                        </span>
                      ) : (
                        <span className="status-pill unmatched">
                          <span className="dot" />
                          미시험
                        </span>
                      )}
                    </td>
                    <td>{fmt(row.discharge_amount)}</td>
                    <td>{fmt(row.capacity_rate)}%</td>
                    <td>
                      {row.sae_cca !== null ? (
                        <>
                          {row.sae_cca.toFixed(3)}{" "}
                          <span className={`status-pill ${saeBadge.tone}`}>{saeBadge.label}</span>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>
                      {row.en_cca !== null ? (
                        <>
                          {row.en_cca.toFixed(3)}{" "}
                          <span className={`status-pill ${enBadge.tone}`}>{enBadge.label}</span>
                        </>
                      ) : (
                        "—"
                      )}
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
