"""③-1/③-2 회귀·KPI API.

`.docs/02_nextjs-fastapi-구현-아키텍처.md` §3 화면-API 매핑 표의 `/dashboard` 화면에 대응.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.analysis.cca_spec import judge_en_cca, judge_sae_cca
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


@router.get("/analysis/y-vs-cca")
def get_y_vs_cca():
    """포화도(Y) ↑에 따른 SAE/EN CCA 관계 확인용(팀장 피드백) — 정식 회귀가 아니라 로트별
    실측 쌍을 그대로 반환한다. 표본이 극히 적을 수 있어(history/19 Phase C) 화면에서 참고용으로
    표시해야 한다."""
    conn = repo.get_connection()
    try:
        pairs = repo.get_y_vs_cca_pairs(conn)
        for pair in pairs:
            pair["en_cca_spec"] = judge_en_cca(pair["en_cca_10s_voltage"], pair["en_cca_6v_hold_sec"])
            pair["sae_cca_spec"] = judge_sae_cca(pair["sae_cca_7v2_hold_sec"])
        return {"pairs": pairs}
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
    conn = repo.get_connection()
    try:
        return repo.get_kpi_summary(conn)
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
