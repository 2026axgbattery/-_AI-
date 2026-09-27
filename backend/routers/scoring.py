"""검증·성공/실패 기준 채점 API(.docs/24, 2026-09-24).

튜터 조언(.docs/23)과 사용자 확정 기준(.docs/22 §0)을 반영 — 시험 매칭 로트를 대상으로
"예측 SPEC 판정 == 실측 SPEC 판정" 일치율을 채점한다. 채점 로직은 `analysis/scoring.py`(순수
함수), 이 라우터는 데이터 조회+실행+저장만 담당한다.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.analysis.scoring import TARGETS, score_target
from backend.db import repository as repo

router = APIRouter(prefix="/api", tags=["scoring"])


def _validate_target(target: str) -> None:
    if target not in TARGETS:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 채점 대상입니다: {target!r}(허용값: {TARGETS})",
        )


@router.post("/scoring/run")
def run_scoring(target: str):
    """target(y|z|en_cca_spec|sae_cca_spec)에 대해 그때그때 재학습+채점하고 결과를 저장한다."""
    _validate_target(target)
    conn = repo.get_connection()
    try:
        rows = repo.get_scoring_rows(conn)
        result = score_target(target, rows)
        run_id = repo.save_scoring_run(conn, result)
        return {"run_id": run_id, **result}
    finally:
        conn.close()


@router.get("/scoring/latest")
def latest_scoring(target: str):
    """target별 가장 최근 채점 결과(+불일치 로트 목록)를 조회한다. 아직 채점한 적 없으면 404."""
    _validate_target(target)
    conn = repo.get_connection()
    try:
        run = repo.get_latest_scoring_run(conn, target)
        if run is None:
            raise HTTPException(
                status_code=404, detail=f"target={target!r}로 채점을 실행한 이력이 없습니다."
            )
        return run
    finally:
        conn.close()
