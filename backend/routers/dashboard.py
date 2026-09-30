"""③-1/③-2 회귀·KPI API.

`.docs/02_nextjs-fastapi-구현-아키텍처.md` §3 화면-API 매핑 표의 `/dashboard` 화면에 대응.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.analysis.cca_spec import (
    aggregate_cca_pass_rates,
    judge_en_cca,
    judge_sae_cca,
)
from backend.analysis.regression import (
    InsufficientSampleError,
    fit_x_to_y,
    fit_x_to_z_baseline,
    fit_xy_to_en_cca,
    fit_xy_to_sae_cca,
    fit_xy_to_z,
)
from backend.db import repository as repo

router = APIRouter(prefix="/api", tags=["dashboard"])

_STAGE_RUNNERS = {
    "x_to_y": (repo.get_x_to_y_training_rows, fit_x_to_y),
    "xy_to_z": (repo.get_xy_to_z_training_rows, fit_xy_to_z),
    "x_to_z_baseline": (repo.get_xy_to_z_training_rows, fit_x_to_z_baseline),
    # 신규(history/19 Phase C) — CCA를 Z2/Z3로 추가. 신뢰성 배치 표본이 n=2뿐이라 지금은
    # InsufficientSampleError(400)가 정상적으로 발생할 수 있다(표본이 쌓이면 자동으로 동작).
    "xy_to_sae_cca": (repo.get_xy_to_sae_cca_training_rows, fit_xy_to_sae_cca),
    "xy_to_en_cca": (repo.get_xy_to_en_cca_training_rows, fit_xy_to_en_cca),
}


def _run_stage(stage: str) -> dict:
    get_rows, fit = _STAGE_RUNNERS[stage]
    conn = repo.get_connection()
    try:
        rows = get_rows(conn)
        try:
            result = fit(rows)
        except InsufficientSampleError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        run_id = repo.save_analysis_run(conn, stage, result)
        return {"run_id": run_id, **result}
    finally:
        conn.close()


@router.post("/analysis/x-to-y")
def run_x_to_y():
    return _run_stage("x_to_y")


@router.post("/analysis/xy-to-z")
def run_xy_to_z():
    return _run_stage("xy_to_z")


@router.post("/analysis/x-to-z-baseline")
def run_x_to_z_baseline():
    return _run_stage("x_to_z_baseline")


@router.post("/analysis/xy-to-sae-cca")
def run_xy_to_sae_cca():
    return _run_stage("xy_to_sae_cca")


@router.post("/analysis/xy-to-en-cca")
def run_xy_to_en_cca():
    return _run_stage("xy_to_en_cca")


def _cca_margin(spec: dict) -> float | None:
    """EN/SAE CCA 판정 기준 대비 여유율(음수일수록 기준 미달 폭이 큼). 두 체크포인트가 모두
    있어야 판정 가능한 EN은 둘 중 더 나쁜 쪽을 대표값으로 쓴다. 측정값이 없어 판정 불가면 None."""
    if "voltage_10s_min" in spec:  # EN
        v, vmin, h, hmin = spec["voltage_10s"], spec["voltage_10s_min"], spec["hold_6v_sec"], spec["hold_6v_sec_min"]
        if v is None or h is None:
            return None
        return min((v - vmin) / vmin, (h - hmin) / hmin)
    h, hmin = spec["hold_7v2_sec"], spec["hold_7v2_sec_min"]  # SAE
    if h is None:
        return None
    return (h - hmin) / hmin


def _worst_score(pair: dict) -> float:
    margins = [m for m in (_cca_margin(pair["en_cca_spec"]), _cca_margin(pair["sae_cca_spec"])) if m is not None]
    return min(margins) if margins else float("inf")


@router.get("/analysis/y-vs-cca")
def get_y_vs_cca(limit: int | None = None, sort: str = "lot_id"):
    """포화도(Y) ↑에 따른 SAE/EN CCA 관계 확인용 — 정식 회귀가 아니라 로트별 실측 쌍을 그대로
    반환한다. 표본이 극히 적을 수 있어(history/19 Phase C) 화면에서 참고용으로 표시해야 한다.

    `sort="worst"`면 EN/SAE 규격 기준 대비 여유가 가장 적은(불합격·근접 불합격 우선) 순으로
    정렬한다 — 대시보드 요약 카드가 `limit`과 함께 써서 "가장 나쁜 N건"만 보여줄 때 쓴다.
    기본값(`lot_id`)은 하위 호환을 위한 기존 동작(전체, lot_id 순)이다."""
    conn = repo.get_connection()
    try:
        pairs = repo.get_y_vs_cca_pairs(conn)
        for pair in pairs:
            pair["en_cca_spec"] = judge_en_cca(pair["en_cca_10s_voltage"], pair["en_cca_6v_hold_sec"])
            pair["sae_cca_spec"] = judge_sae_cca(pair["sae_cca_7v2_hold_sec"])
        total_count = len(pairs)
        if sort == "worst":
            pairs = sorted(pairs, key=_worst_score)
        if limit is not None:
            pairs = pairs[:limit]
        return {"pairs": pairs, "total_count": total_count}
    finally:
        conn.close()


@router.get("/analysis/latest")
def get_latest_analysis(stage: str):
    """아직 실행 전(정상 상태)일 수 있으므로 없으면 404가 아니라 200 + null을 반환한다.

    화면 최초 진입 시 세 stage를 한꺼번에 조회하는데, 그중 일부가 "아직 실행 안 됨"인 것은
    에러가 아니라 정상적인 초기 상태다(브라우저 콘솔에 불필요한 404 에러를 남기지 않기 위함).
    """
    if stage not in _STAGE_RUNNERS:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 stage입니다: {stage}")
    conn = repo.get_connection()
    try:
        return repo.get_latest_analysis_run(conn, stage)
    finally:
        conn.close()


@router.get("/kpi")
def get_kpi():
    """대시보드 히어로(Layer 0)가 평균 Y·Z·CCA를 한 번에 보여줄 수 있도록, 형명 구분 없이 전체
    로트 기준 EN/SAE CCA 합격률을 함께 집계한다(판정 로직은 `models/summary`와 동일하게
    `analysis/cca_spec.py`의 고정 임계값 함수를 그대로 재사용, 새 판정 로직 없음)."""
    conn = repo.get_connection()
    try:
        summary = repo.get_kpi_summary(conn)
        agg = aggregate_cca_pass_rates(repo.get_model_cca_checkpoints(conn))
        summary.update(agg)
        return summary
    finally:
        conn.close()


@router.get("/spec-compliance")
def get_spec_compliance():
    """⑤ SPEC 판정 요약(실측/직접계산 Y·Z 기준) — `/dashboard` KPI 카드 + Layer 3."""
    conn = repo.get_connection()
    try:
        return repo.get_spec_compliance_summary(conn)
    finally:
        conn.close()
