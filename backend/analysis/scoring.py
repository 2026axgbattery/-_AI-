"""검증·성공/실패 기준 채점 모듈(.docs/24, 2026-09-24).

튜터 조언(.docs/23)과 사용자 확정 기준(.docs/22 §0)을 코드로 구현한다 — 시험 매칭 로트를 대상으로
"예측 SPEC 판정 == 실측 SPEC 판정" 일치율을 채점한다. 학습은 이 모듈 호출 시마다 그때그때 다시
수행하는 in-sample 채점이다(`AnalysisRun`에 영속화하지 않음 — 회귀계수 CHECK 제약을 건드리지
않기 위함이기도 하고, 정식 train/val 분리 검증은 `docs/prd.md` §3에서 v2 Non-goal로 명시돼 있어
그 범위를 침범하지 않기 위함이기도 하다).

순수 함수만 둔다(DB·웹 프레임워크 비의존) — 라우터(`backend/routers/scoring.py`)만 이 모듈을
호출하고, 학습 데이터 조회는 `backend/db/repository.py`(`get_scoring_rows`)가 담당한다.
"""
from __future__ import annotations

from backend.analysis.cca_spec import judge_en_cca, judge_sae_cca
from backend.analysis.diagnosis import judge_spec
from backend.analysis.regression import (
    X_COLUMNS,
    InsufficientSampleError,
    fit_x_to_y,
    fit_xy_to_en_cca_hold6v,
    fit_xy_to_en_cca_voltage10s,
    fit_xy_to_sae_cca_hold7v2,
    fit_xy_to_z,
    predict,
)
from backend.config.spec_thresholds import (
    SCORING_ERROR_TOLERANCE_PCT,
    SCORING_SUCCESS_RATE_THRESHOLD_PCT,
)

TARGETS = ("y", "z", "en_cca_spec", "sae_cca_spec")


def _error_pct(predicted: float, actual: float | None) -> float | None:
    if actual is None or actual == 0:
        return None
    return abs(predicted - actual) / abs(actual) * 100


def _scalar_result(
    lot_id: str, predicted: float, actual: float | None,
    predicted_spec_result: str | None, actual_spec_result: str | None,
) -> dict:
    error_pct = _error_pct(predicted, actual)
    matched = (
        predicted_spec_result == actual_spec_result
        if predicted_spec_result is not None and actual_spec_result is not None
        else None
    )
    return {
        "lot_id": lot_id,
        "predicted_value": predicted,
        "actual_value": actual,
        "error_pct": error_pct,
        "within_error_tolerance": (
            error_pct is not None and error_pct <= SCORING_ERROR_TOLERANCE_PCT
        ),
        "predicted_spec_result": predicted_spec_result,
        "actual_spec_result": actual_spec_result,
        "matched": matched,
    }


def _spec_only_result(
    lot_id: str, predicted_spec_result: str | None, actual_spec_result: str | None
) -> dict:
    matched = (
        predicted_spec_result == actual_spec_result
        if predicted_spec_result is not None and actual_spec_result is not None
        else None
    )
    return {
        "lot_id": lot_id,
        "predicted_value": None,
        "actual_value": None,
        "error_pct": None,
        "within_error_tolerance": None,
        "predicted_spec_result": predicted_spec_result,
        "actual_spec_result": actual_spec_result,
        "matched": matched,
    }


def _aggregate(target: str, n_total: int, results: list[dict], note: str | None = None) -> dict:
    scorable = [r for r in results if r["matched"] is not None]
    n_matched = sum(1 for r in scorable if r["matched"])
    n_mismatched = len(scorable) - n_matched
    success_rate_pct = (n_matched / len(scorable) * 100) if scorable else None
    return {
        "target": target,
        "threshold_pct": SCORING_SUCCESS_RATE_THRESHOLD_PCT,
        "error_tolerance_pct": SCORING_ERROR_TOLERANCE_PCT,
        "n_total": n_total,
        "n_scorable": len(scorable),
        "n_matched": n_matched,
        "n_mismatched": n_mismatched,
        "success_rate_pct": success_rate_pct,
        "reliable": (
            success_rate_pct >= SCORING_SUCCESS_RATE_THRESHOLD_PCT
            if success_rate_pct is not None else None
        ),
        "results": results,
        "mismatched_lots": [r for r in results if r["matched"] is False],
        "note": note,
    }


def score_y(rows: list[dict]) -> dict:
    """target='y': 예측 retention_rate vs 실측 retention_rate를 spec_lower_y로 판정 비교."""
    valid = [
        r for r in rows
        if all(r.get(c) is not None for c in X_COLUMNS) and r.get("retention_rate") is not None
    ]
    try:
        run = fit_x_to_y(valid)
    except InsufficientSampleError as exc:
        return _aggregate("y", len(rows), [], note=str(exc))

    results = []
    for r in valid:
        x = {c: r[c] for c in X_COLUMNS}
        predicted = predict(run["coefficients"], run["intercept"], x)
        actual = r["retention_rate"]
        spec_lower = r.get("spec_lower_y")
        pred_result = judge_spec(predicted, spec_lower)["spec_result"]
        actual_result = judge_spec(actual, spec_lower)["spec_result"]
        results.append(_scalar_result(r["lot_id"], predicted, actual, pred_result, actual_result))
    return _aggregate("y", len(rows), results)


def score_z(rows: list[dict]) -> dict:
    """target='z': 예측 capacity_rate(=예측 discharge_amount/rated_capacity*100) vs 실측
    capacity_rate를 spec_lower_z로 판정 비교(prediction.py의 capacity_rate_pred 관례와 동일)."""
    valid = [
        r for r in rows
        if all(r.get(c) is not None for c in X_COLUMNS)
        and r.get("retention_rate") is not None
        and r.get("discharge_amount") is not None
        and r.get("capacity_rate") is not None
        and r.get("rated_capacity")
    ]
    try:
        run = fit_xy_to_z(valid)
    except InsufficientSampleError as exc:
        return _aggregate("z", len(rows), [], note=str(exc))

    results = []
    for r in valid:
        x = {c: r[c] for c in X_COLUMNS}
        x["retention_rate"] = r["retention_rate"]
        predicted_discharge = predict(run["coefficients"], run["intercept"], x)
        predicted_rate = predicted_discharge / r["rated_capacity"] * 100
        actual_rate = r["capacity_rate"]
        spec_lower = r.get("spec_lower_z")
        pred_result = judge_spec(predicted_rate, spec_lower)["spec_result"]
        actual_result = judge_spec(actual_rate, spec_lower)["spec_result"]
        results.append(
            _scalar_result(r["lot_id"], predicted_rate, actual_rate, pred_result, actual_result)
        )
    return _aggregate("z", len(rows), results)


def score_en_cca_spec(rows: list[dict]) -> dict:
    """target='en_cca_spec': EN 50342 합격배지(10초 전압≥7.5V AND 6.0V까지 지속시간≥90초)를
    두 체크포인트 회귀로 각각 예측한 뒤, `judge_en_cca`로 예측 판정 vs 실측 판정을 비교한다."""
    valid = [
        r for r in rows
        if all(r.get(c) is not None for c in X_COLUMNS)
        and r.get("retention_rate") is not None
        and r.get("en_cca_10s_voltage") is not None
        and r.get("en_cca_6v_hold_sec") is not None
    ]
    try:
        run_voltage = fit_xy_to_en_cca_voltage10s(valid)
        run_hold = fit_xy_to_en_cca_hold6v(valid)
    except InsufficientSampleError as exc:
        return _aggregate("en_cca_spec", len(rows), [], note=str(exc))

    results = []
    for r in valid:
        x = {c: r[c] for c in X_COLUMNS}
        x["retention_rate"] = r["retention_rate"]
        predicted_voltage = predict(run_voltage["coefficients"], run_voltage["intercept"], x)
        predicted_hold = predict(run_hold["coefficients"], run_hold["intercept"], x)
        pred_result = judge_en_cca(predicted_voltage, predicted_hold)["result"]
        actual_result = judge_en_cca(r["en_cca_10s_voltage"], r["en_cca_6v_hold_sec"])["result"]
        results.append(_spec_only_result(r["lot_id"], pred_result, actual_result))
    return _aggregate("en_cca_spec", len(rows), results)


def score_sae_cca_spec(rows: list[dict]) -> dict:
    """target='sae_cca_spec': SAE J537 합격배지(7.2V까지 지속시간≥30초)를 체크포인트 회귀로
    예측한 뒤, `judge_sae_cca`로 예측 판정 vs 실측 판정을 비교한다."""
    valid = [
        r for r in rows
        if all(r.get(c) is not None for c in X_COLUMNS)
        and r.get("retention_rate") is not None
        and r.get("sae_cca_7v2_hold_sec") is not None
    ]
    try:
        run = fit_xy_to_sae_cca_hold7v2(valid)
    except InsufficientSampleError as exc:
        return _aggregate("sae_cca_spec", len(rows), [], note=str(exc))

    results = []
    for r in valid:
        x = {c: r[c] for c in X_COLUMNS}
        x["retention_rate"] = r["retention_rate"]
        predicted = predict(run["coefficients"], run["intercept"], x)
        actual = r["sae_cca_7v2_hold_sec"]
        pred_result = judge_sae_cca(predicted)["result"]
        actual_result = judge_sae_cca(actual)["result"]
        results.append(_scalar_result(r["lot_id"], predicted, actual, pred_result, actual_result))
    return _aggregate("sae_cca_spec", len(rows), results)


_SCORE_FNS = {
    "y": score_y,
    "z": score_z,
    "en_cca_spec": score_en_cca_spec,
    "sae_cca_spec": score_sae_cca_spec,
}


def score_target(target: str, rows: list[dict]) -> dict:
    """target 문자열로 4종 채점 함수를 디스패치한다(라우터의 단일 진입점)."""
    fn = _SCORE_FNS.get(target)
    if fn is None:
        raise ValueError(f"지원하지 않는 채점 대상입니다: {target!r}(허용값: {TARGETS})")
    return fn(rows)
