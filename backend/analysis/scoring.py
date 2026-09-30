"""검증·성공/실패 기준 채점 모듈(.docs/24, 2026-09-24 / .docs/35, 2026-09-30).

튜터 조언(.docs/23)과 사용자 확정 기준(.docs/22 §0)을 코드로 구현한다 — 시험 매칭 로트를 대상으로
"예측 SPEC 판정 == 실측 SPEC 판정" 일치율을 채점한다.

**2026-09-30 홀드아웃(train/val) 검증 도입(.docs/35, v2 착수)**: `docs/prd.md` §3은 애초
"train/val 분리"를 "Non-goals(→v2, 10월)"로 명시해뒀었다 — 이 모듈이 그동안 in-sample(학습에
쓴 행을 그대로 다시 채점)이었던 것도 그래서였다. 표본이 충분하면(§`MIN_HOLDOUT_VAL_SIZE`) 이제
고정 시드로 80/20 분할해 **학습(train)에 쓰지 않은 val 표본으로만** 채점한다 — in-sample은 "이미
외운 문제를 다시 풀어 맞히는" 격이라 실제보다 낙관적인 일치율이 나올 수 있었다. 분할 후에도 train이
회귀 최소 표본을 못 채우거나, 애초에 전체 표본이 분할할 만큼 안 되면 지금까지처럼 in-sample로
정직하게 폴백하고(지어내지 않음 원칙) 그 사실을 `validation_mode`/`note`로 그대로 알린다.
회귀 자체는 여전히 이 모듈 호출 시마다 그때그때 다시 학습하고 `AnalysisRun`에는 영속화하지 않는다
(회귀계수 CHECK 제약을 건드리지 않기 위함).

순수 함수만 둔다(DB·웹 프레임워크 비의존) — 라우터(`backend/routers/scoring.py`)만 이 모듈을
호출하고, 학습 데이터 조회는 `backend/db/repository.py`(`get_scoring_rows`)가 담당한다.
"""
from __future__ import annotations

import random

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
    HOLDOUT_SPLIT_SEED,
    HOLDOUT_VAL_RATIO,
    MIN_HOLDOUT_VAL_SIZE,
    SCORING_ERROR_TOLERANCE_PCT,
    SCORING_SUCCESS_RATE_THRESHOLD_PCT,
)

TARGETS = ("y", "z", "en_cca_spec", "sae_cca_spec")


def _split_train_val(valid: list[dict]) -> tuple[list[dict], list[dict]] | None:
    """고정 시드로 80/20(설정값) 분할한다. val 최소 표본조차 못 채울 만큼 전체가 적으면
    분할 자체가 무의미하므로 None을 반환해 호출부가 in-sample로 폴백하게 한다."""
    n = len(valid)
    val_n = max(MIN_HOLDOUT_VAL_SIZE, round(n * HOLDOUT_VAL_RATIO))
    if val_n >= n:
        return None
    rng = random.Random(HOLDOUT_SPLIT_SEED)
    shuffled = list(valid)
    rng.shuffle(shuffled)
    return shuffled[val_n:], shuffled[:val_n]


def _fallback_note(n_valid: int) -> str:
    return f"표본이 적어({n_valid}건) 홀드아웃 분할 없이 전체로 학습·채점했습니다(in-sample)."


def _refit_fallback_note(n_valid: int) -> str:
    return f"홀드아웃 분할 후 학습 표본이 부족해 in-sample로 대체했습니다(전체 {n_valid}건)."


def _fit_holdout_or_fallback(fit_fn, valid: list[dict]):
    """단일 회귀 하나만 학습하면 되는 타깃(y/z/sae_cca_spec) 공용 — en_cca_spec은 같은 분할로
    회귀 2개를 학습해야 해서 이 헬퍼를 쓰지 않고 같은 패턴을 직접 구현한다.

    반환: (run 또는 None, 채점에 쓸 행 목록, validation_mode, train_n, val_n, note)."""
    split = _split_train_val(valid)
    if split is not None:
        train, val = split
        try:
            return fit_fn(train), val, "holdout", len(train), len(val), None
        except InsufficientSampleError:
            pass  # train 분할이 너무 작음 — 아래에서 전체(valid)로 재시도
    try:
        run = fit_fn(valid)
    except InsufficientSampleError as exc:
        return None, [], "in_sample", 0, 0, str(exc)
    note = _refit_fallback_note(len(valid)) if split is not None else _fallback_note(len(valid))
    return run, valid, "in_sample", len(valid), len(valid), note


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


def _aggregate(
    target: str,
    n_total: int,
    results: list[dict],
    note: str | None = None,
    validation_mode: str = "in_sample",
    train_n: int = 0,
    val_n: int = 0,
) -> dict:
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
        # .docs/35 — "holdout"이면 val_n건은 train_n건 학습에 전혀 쓰이지 않은 표본으로만 채점한
        # 것이고, "in_sample"이면 표본 부족으로 학습에 쓴 행을 그대로 다시 채점한 것(과거 방식).
        "validation_mode": validation_mode,
        "train_n": train_n,
        "val_n": val_n,
    }


def score_y(rows: list[dict]) -> dict:
    """target='y': 예측 retention_rate vs 실측 retention_rate를 spec_lower_y로 판정 비교."""
    valid = [
        r for r in rows
        if all(r.get(c) is not None for c in X_COLUMNS) and r.get("retention_rate") is not None
    ]
    run, score_rows, validation_mode, train_n, val_n, note = _fit_holdout_or_fallback(fit_x_to_y, valid)
    if run is None:
        return _aggregate("y", len(rows), [], note=note, validation_mode=validation_mode, train_n=train_n, val_n=val_n)

    results = []
    for r in score_rows:
        x = {c: r[c] for c in X_COLUMNS}
        predicted = predict(run["coefficients"], run["intercept"], x)
        actual = r["retention_rate"]
        spec_lower = r.get("spec_lower_y")
        pred_result = judge_spec(predicted, spec_lower)["spec_result"]
        actual_result = judge_spec(actual, spec_lower)["spec_result"]
        results.append(_scalar_result(r["lot_id"], predicted, actual, pred_result, actual_result))
    return _aggregate(
        "y", len(rows), results, note=note, validation_mode=validation_mode, train_n=train_n, val_n=val_n
    )


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
    run, score_rows, validation_mode, train_n, val_n, note = _fit_holdout_or_fallback(fit_xy_to_z, valid)
    if run is None:
        return _aggregate("z", len(rows), [], note=note, validation_mode=validation_mode, train_n=train_n, val_n=val_n)

    results = []
    for r in score_rows:
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
    return _aggregate(
        "z", len(rows), results, note=note, validation_mode=validation_mode, train_n=train_n, val_n=val_n
    )


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
    # EN CCA는 회귀 2개(전압10초·6.0V지속)를 같은 train/val 분할로 학습해야 한다 — 채점 1건마다
    # 두 예측을 함께 judge_en_cca에 넣어야 하므로 `_fit_holdout_or_fallback`(단일 회귀 전용)을
    # 그대로 못 쓰고 같은 분할·폴백 패턴을 여기서 직접 구현한다.
    split = _split_train_val(valid)
    train, score_rows = split if split is not None else (valid, valid)
    validation_mode = "holdout" if split is not None else "in_sample"
    note = None if split is not None else _fallback_note(len(valid))
    try:
        run_voltage = fit_xy_to_en_cca_voltage10s(train)
        run_hold = fit_xy_to_en_cca_hold6v(train)
    except InsufficientSampleError as exc:
        if validation_mode == "in_sample":
            return _aggregate("en_cca_spec", len(rows), [], note=str(exc), validation_mode="in_sample")
        train, score_rows, validation_mode = valid, valid, "in_sample"
        note = _refit_fallback_note(len(valid))
        try:
            run_voltage = fit_xy_to_en_cca_voltage10s(train)
            run_hold = fit_xy_to_en_cca_hold6v(train)
        except InsufficientSampleError as exc2:
            return _aggregate("en_cca_spec", len(rows), [], note=str(exc2), validation_mode="in_sample")

    results = []
    for r in score_rows:
        x = {c: r[c] for c in X_COLUMNS}
        x["retention_rate"] = r["retention_rate"]
        predicted_voltage = predict(run_voltage["coefficients"], run_voltage["intercept"], x)
        predicted_hold = predict(run_hold["coefficients"], run_hold["intercept"], x)
        pred_result = judge_en_cca(predicted_voltage, predicted_hold)["result"]
        actual_result = judge_en_cca(r["en_cca_10s_voltage"], r["en_cca_6v_hold_sec"])["result"]
        results.append(_spec_only_result(r["lot_id"], pred_result, actual_result))
    return _aggregate(
        "en_cca_spec", len(rows), results, note=note,
        validation_mode=validation_mode, train_n=len(train), val_n=len(score_rows),
    )


def score_sae_cca_spec(rows: list[dict]) -> dict:
    """target='sae_cca_spec': SAE J537 합격배지(7.2V까지 지속시간≥30초)를 체크포인트 회귀로
    예측한 뒤, `judge_sae_cca`로 예측 판정 vs 실측 판정을 비교한다."""
    valid = [
        r for r in rows
        if all(r.get(c) is not None for c in X_COLUMNS)
        and r.get("retention_rate") is not None
        and r.get("sae_cca_7v2_hold_sec") is not None
    ]
    run, score_rows, validation_mode, train_n, val_n, note = _fit_holdout_or_fallback(
        fit_xy_to_sae_cca_hold7v2, valid
    )
    if run is None:
        return _aggregate(
            "sae_cca_spec", len(rows), [], note=note,
            validation_mode=validation_mode, train_n=train_n, val_n=val_n,
        )

    results = []
    for r in score_rows:
        x = {c: r[c] for c in X_COLUMNS}
        x["retention_rate"] = r["retention_rate"]
        predicted = predict(run["coefficients"], run["intercept"], x)
        actual = r["sae_cca_7v2_hold_sec"]
        pred_result = judge_sae_cca(predicted)["result"]
        actual_result = judge_sae_cca(actual)["result"]
        results.append(_scalar_result(r["lot_id"], predicted, actual, pred_result, actual_result))
    return _aggregate(
        "sae_cca_spec", len(rows), results, note=note,
        validation_mode=validation_mode, train_n=train_n, val_n=val_n,
    )


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
