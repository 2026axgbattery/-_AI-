"""③-3/③-4 형명별 상세·추이 API.

`.docs/02_nextjs-fastapi-구현-아키텍처.md` §3 화면-API 매핑 표의 `/detail-analysis` 화면에 대응.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.analysis.cca_spec import (
    aggregate_cca_pass_rates,
    judge_en_cca,
    judge_sae_cca,
)
from backend.analysis.derive import extract_buyer_code_from_model_name
from backend.analysis.diagnosis import compute_factor_means, judge_spec, rank_causes
from backend.analysis.regression import X_COLUMNS
from backend.analysis.trend import aggregate_by_period
from backend.config.spec_thresholds import MIN_SAMPLE_SIZE_FOR_MODEL_DETAIL
from backend.db import repository as repo

router = APIRouter(prefix="/api", tags=["detail-analysis"])


@router.get("/models/summary")
def models_summary():
    conn = repo.get_connection()
    try:
        rows = repo.get_model_summary(conn)
        cca_by_model = aggregate_cca_pass_rates(repo.get_model_cca_checkpoints(conn), group_by="model_name")

        for row in rows:
            row["sample_sufficient"] = row["lot_count"] >= MIN_SAMPLE_SIZE_FOR_MODEL_DETAIL
            row.update(
                cca_by_model.get(
                    row["model_name"],
                    {"en_cca_evaluated": 0, "en_cca_pass": 0, "sae_cca_evaluated": 0, "sae_cca_pass": 0},
                )
            )
        return {"min_sample_size": MIN_SAMPLE_SIZE_FOR_MODEL_DETAIL, "models": rows}
    finally:
        conn.close()


@router.get("/models/failing-lots")
def failing_lots(model_name: str | None = None, buyer_code: str | None = None, limit: int = 30):
    """실측 Y·Z가 SPEC 하한 미달인 로트 목록 + 로트별 원인진단(상위 기여 X인자 3개, `.docs/27`).

    `/prediction`의 원인진단(`judge_spec`/`rank_causes`)은 예측값·미매칭 로트 전용이었는데,
    사용자 요청으로 이미 시험 완료된(실측값이 있는) 로트 중 SPEC 미달인 것도 "왜 미달인지"를
    바로 확인할 수 있도록 새로 추가했다. 새 회귀 학습은 하지 않고 기존 최신 `AnalysisRun`
    (x_to_y/xy_to_z)의 계수를 그대로 재사용하며, 예측/판정 결과를 DB에 저장하지도 않는다
    (그때그때 조회 전용 — `Prediction`/`CauseDiagnosis` 테이블은 예측 흐름 전용이라 그대로 둠).

    표본이 많으면(형명당 수천 건) 한 번에 다 보여주는 게 의미 없어, SPEC 이탈폭이 큰(더 심각한)
    순으로 정렬해 `limit`건만 반환하고 형명별 미달 건수(`by_model`)를 같이 줘서 전체 규모를
    파악할 수 있게 한다. `model_name`/`buyer_code`는 `/detail-analysis` 상단의 전체/형명별/바이어별
    스코프 선택과 이 섹션을 맞추기 위한 필터(2026-09-26, 둘 다 주면 model_name이 우선 적용).
    `buyer_code`는 `ChargeProgramSpec`처럼 DB 컬럼이 아니라 `model_name` 접미문자에서 그때그때
    추출하는 값이라 SQL이 아니라 조회 후 Python에서 거른다(`extract_buyer_code_from_model_name`).
    """
    conn = repo.get_connection()
    try:
        lots = repo.get_failing_lots(conn, model_name)
        if buyer_code and not model_name:
            lots = [
                lot for lot in lots
                if extract_buyer_code_from_model_name(lot["model_name"]) == buyer_code
            ]

        y_run = repo.get_latest_analysis_run(conn, "x_to_y")
        y_means = compute_factor_means(repo.get_x_to_y_training_rows(conn), X_COLUMNS) if y_run else {}
        z_run = repo.get_latest_analysis_run(conn, "xy_to_z")
        z_means = (
            compute_factor_means(repo.get_xy_to_z_training_rows(conn), z_run["x_columns"]) if z_run else {}
        )

        results = []
        by_model: dict[str, int] = {}
        for lot in lots:
            by_model[lot["model_name"]] = by_model.get(lot["model_name"], 0) + 1
            x = {c: lot[c] for c in X_COLUMNS if lot[c] is not None}

            y_spec = judge_spec(lot["retention_rate"], lot["spec_lower_y"])
            y_causes = (
                rank_causes(X_COLUMNS, y_run["coefficients"], x, y_means)
                if y_run and y_spec["spec_result"] == "fail"
                else []
            )

            z_spec = judge_spec(lot["capacity_rate"], lot["spec_lower_z"])
            z_causes = []
            if z_run and z_spec["spec_result"] == "fail":
                x_with_y = {**x, "retention_rate": lot["retention_rate"]}
                z_causes = rank_causes(z_run["x_columns"], z_run["coefficients"], x_with_y, z_means)

            # 심각도(severity) = Y/Z 중 미달인 쪽의 이탈폭(음수, 클수록 더 미달) — 정렬용.
            deviations = [
                spec["deviation"] for spec in (y_spec, z_spec)
                if spec["spec_result"] == "fail" and spec["deviation"] is not None
            ]
            severity = min(deviations) if deviations else 0.0

            results.append({
                "lot_id": lot["lot_id"],
                "model_name": lot["model_name"],
                "severity": severity,
                "y": {"value": lot["retention_rate"], "spec": y_spec, "causes": y_causes},
                "z": {"value": lot["capacity_rate"], "spec": z_spec, "causes": z_causes},
            })

        results.sort(key=lambda r: r["severity"])
        shown = results[:limit]
        for r in shown:
            del r["severity"]

        return {
            "total_count": len(results),
            "shown_count": len(shown),
            "by_model": by_model,
            "y_run_available": y_run is not None,
            "z_run_available": z_run is not None,
            "lots": shown,
        }
    finally:
        conn.close()


@router.get("/models/{model_name}/lots")
def model_lots(model_name: str, limit: int = 200, sort: str = "recent"):
    """형명별 상세 테이블의 "로트 수"/"시험 매칭" 드릴다운용 기본 raw data 목록.

    `sort=tested_first`이면 시험 매칭된 로트를 먼저 반환한다(그 안에서는 최신순).
    `limit`을 크게 주면(예: 전체 로트 수) 페이지네이션 없이 전체 raw data를 한 번에 받을 수 있다.
    """
    if sort not in ("recent", "tested_first"):
        raise HTTPException(status_code=400, detail=f"지원하지 않는 sort 값입니다: {sort!r}")
    conn = repo.get_connection()
    try:
        result = repo.get_model_lot_rows(conn, model_name, limit, sort)
        for row in result["rows"]:
            row["en_cca_spec"] = judge_en_cca(row["en_cca_10s_voltage"], row["en_cca_6v_hold_sec"])
            row["sae_cca_spec"] = judge_sae_cca(row["sae_cca_7v2_hold_sec"])
        return {"model_name": model_name, "limit": limit, **result}
    finally:
        conn.close()


@router.get("/models/{model_name}/trend")
def model_trend(model_name: str, period: str = "month"):
    conn = repo.get_connection()
    try:
        rows = repo.get_model_trend_rows(conn, None if model_name == "all" else model_name)
        try:
            points = aggregate_by_period(rows, period)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        years = sorted({p["period"][:4] for p in aggregate_by_period(rows, "year")})
        return {
            "model_name": model_name,
            "period": period,
            "points": points,
            "available_years": years,
        }
    finally:
        conn.close()
