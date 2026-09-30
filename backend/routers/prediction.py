"""④-1/④-2 예측 + ⑤ SPEC 판정·원인진단 API.

`.docs/02_nextjs-fastapi-구현-아키텍처.md` §3 화면-API 매핑 표의 `/prediction` 화면,
`history/17_day3-예측-spec판정-원인진단-구현계획.md`에 대응.

캐스케이드: 1단(X→Y) 예측값 Ŷ을 2단(X+Y→Z)에 투입해 Z(discharge_amount)를 얻고,
`capacity_rate_pred = predicted_z / rated_capacity * 100`을 SPEC(spec_lower_z, %) 비교 대상으로
쓴다(SPEC 하한이 %-단위라는 것은 output/04_prediction.html 목업의 표기 관례를 따름).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.analysis.cca_spec import judge_en_cca, judge_sae_cca
from backend.analysis.derive import parse_rated_capacity_from_model_name
from backend.analysis.diagnosis import compute_factor_means, judge_spec, rank_causes
from backend.analysis.regression import (
    X_COLUMNS,
    InsufficientSampleError,
    fit_xy_to_en_cca_hold6v,
    fit_xy_to_en_cca_voltage10s,
    fit_xy_to_sae_cca_hold7v2,
    predict,
)
from backend.config.spec_thresholds import DEFAULT_SPEC_LOWER_Y, DEFAULT_SPEC_LOWER_Z
from backend.db import repository as repo

router = APIRouter(prefix="/api", tags=["prediction"])

_OUTLIER_Y_RANGE = (0.0, 100.0)  # 포화도(잔존율 proxy)는 정의상 0~100%


class ManualPredictRequest(BaseModel):
    model_name: str
    x: dict[str, float]


def _require_latest_run(conn, stage: str) -> dict:
    run = repo.get_latest_analysis_run(conn, stage)
    if run is None:
        raise HTTPException(
            status_code=400,
            detail=f"{stage} 모델이 아직 학습되지 않았습니다. 대시보드에서 먼저 분석을 실행하세요.",
        )
    return run


def _judge_and_maybe_save(
    conn, lot_id: str | None, prediction_id: int, target: str, value: float | None, spec_lower: float | None
) -> dict:
    result = judge_spec(value, spec_lower)
    if result["spec_result"] is not None:
        repo.save_spec_judgment(
            conn, lot_id, prediction_id, target, result["spec_result"], {"spec_lower": spec_lower}
        )
    return result


def _diagnose_if_fail(
    conn,
    lot_id: str | None,
    prediction_id: int,
    target: str,
    spec_result: str | None,
    x_columns: list[str],
    coefficients: dict[str, float],
    x_values: dict[str, float],
    factor_means: dict[str, float],
) -> list[dict]:
    """부적합(fail)으로 판정된 경우에만 원인진단을 계산·저장한다(docs/prd.md §6-⑤: "부적합 판정된 로트에 대해")."""
    ranked = rank_causes(x_columns, coefficients, x_values, factor_means)
    if spec_result == "fail" and ranked:
        recommendation_text = " / ".join(r["recommendation"] for r in ranked)
        repo.save_cause_diagnosis(conn, lot_id, prediction_id, target, ranked, recommendation_text)
    return ranked


def _load_cca_ah_run(conn, stage: str) -> dict | None:
    """CCA(SAE/EN) 방전량(Ah) 회귀의 최신 run을 조회한다 — 판정에는 더 이상 쓰이지 않고(`.docs/29`
    참조, 판정은 체크포인트 회귀로 함) `predicted_value`(참고용 Ah 값) 계산·`Prediction` 로그용
    `run_id`로만 쓰인다."""
    return repo.get_latest_analysis_run(conn, stage)


def _valid_rows(rows: list[dict], x_columns: list[str], target: str) -> list[dict]:
    """`_fit_linear`(regression.py)와 동일한 완결성 필터 — 학습에 실제로 쓰인 행만 골라
    `compute_factor_means`에 넘기기 위함(그래야 "훈련 평균 대비"라는 설명이 정확함)."""
    return [r for r in rows if all(r.get(c) is not None for c in x_columns) and r.get(target) is not None]


def _fit_checkpoint(rows: list[dict], fit_fn) -> dict | None:
    """EN/SAE CCA 체크포인트 회귀(10초 전압·6.0V/7.2V 지속시간)를 요청마다 in-sample로 그때그때
    학습한다(`analysis/scoring.py`와 동일한 비영속 방식 — `AnalysisRun.stage` CHECK 제약을 건드리지
    않기 위해 일부러 영속화하지 않는다, `.docs/29`). 표본 부족이면 `InsufficientSampleError`가
    정상적으로 발생할 수 있어 `None`으로 정직하게 반환한다."""
    try:
        return fit_fn(rows)
    except InsufficientSampleError:
        return None


def _load_checkpoint_runs(conn) -> dict:
    """EN CCA(전압10초·6.0V지속) + SAE CCA(7.2V지속) 체크포인트 회귀 3개를 요청당 1회만 학습한다
    (일괄 예측 루프에서 로트마다 다시 학습하지 않도록)."""
    rows = repo.get_scoring_rows(conn)
    checkpoint_x_columns = [*X_COLUMNS, "retention_rate"]

    voltage_run = _fit_checkpoint(rows, fit_xy_to_en_cca_voltage10s)
    hold6v_run = _fit_checkpoint(rows, fit_xy_to_en_cca_hold6v)
    hold7v2_run = _fit_checkpoint(rows, fit_xy_to_sae_cca_hold7v2)

    return {
        "voltage": (
            voltage_run,
            compute_factor_means(_valid_rows(rows, checkpoint_x_columns, "en_cca_10s_voltage"), checkpoint_x_columns)
            if voltage_run else {},
        ),
        "hold6v": (
            hold6v_run,
            compute_factor_means(_valid_rows(rows, checkpoint_x_columns, "en_cca_6v_hold_sec"), checkpoint_x_columns)
            if hold6v_run else {},
        ),
        "hold7v2": (
            hold7v2_run,
            compute_factor_means(_valid_rows(rows, checkpoint_x_columns, "sae_cca_7v2_hold_sec"), checkpoint_x_columns)
            if hold7v2_run else {},
        ),
    }


_NO_SPEC_LOWER = {"spec_result": None, "spec_lower": None, "deviation": None}


def _predict_cca_ah_and_prediction_id(
    conn, ah_run: dict | None, x_with_y: dict, lot_id: str | None, target: str, source: str
) -> tuple[float | None, int | None]:
    """SAE/EN CCA 공통 전처리 — 방전량(Ah) 참고값 예측 + `Prediction` 로그 저장(`run_id`는 기존
    방전량 회귀 것을 그대로 씀, `.docs/29`: 판정 자체는 체크포인트 회귀가 따로 담당)."""
    predicted_ah = predict(ah_run["coefficients"], ah_run["intercept"], x_with_y) if ah_run else None
    prediction_id = (
        repo.save_prediction(conn, lot_id, ah_run["run_id"], target, predicted_ah, "predicted", source)
        if ah_run else None
    )
    return predicted_ah, prediction_id


def _cca_checkpoint_unavailable_block(ah_run: dict | None, predicted_ah: float | None) -> dict:
    """체크포인트 회귀가 표본 부족으로 아직 학습되지 않은 경우의 SAE/EN 공통 응답.
    방전량 회귀 자체도 없으면(ah_run is None) 참고값조차 보여줄 게 없어 완전히 판정불가로 반환."""
    if ah_run is None:
        return {"available": False}
    return {
        "available": True, "run_id": ah_run["run_id"], "run_at": ah_run.get("run_at"),
        "predicted_value": predicted_ah, "input_y_source": "predicted",
        "spec": {**_NO_SPEC_LOWER, "note": "신뢰성 시험 체크포인트 표본 부족으로 판정 불가"},
        "causes": [],
    }


def _save_cca_verdict(
    conn, lot_id: str | None, prediction_id: int | None, target: str,
    verdict_result: str | None, spec_detail: dict, causes: list[dict],
) -> None:
    if prediction_id is None:
        return
    if verdict_result is not None:
        repo.save_spec_judgment(conn, lot_id, prediction_id, target, verdict_result, spec_detail)
    if causes:
        recommendation_text = " / ".join(c["recommendation"] for c in causes)
        repo.save_cause_diagnosis(conn, lot_id, prediction_id, target, causes, recommendation_text)


def _predict_sae_cca_block(
    conn, ah_run: dict | None, checkpoint_runs: dict, lot_id: str | None, x_with_y: dict, source: str
) -> dict:
    """SAE CCA(Z2) 예측 — 판정은 방전량(Ah)이 아니라 7.2V 지속시간 체크포인트 회귀로 한다.

    `cca_spec.judge_sae_cca`가 원래 그 체크포인트로 판정하기 때문(방전량으로는 SPEC 자체가 없어
    구조적으로 판정 불가, `.docs/29`). 방전량 예측값(`predicted_value`)은 참고 정보로 그대로 두되,
    저장은 기존 방전량 회귀의 `run_id`/`prediction_id`에 그대로 연결한다(스키마 변경 없음).
    """
    hold_run, hold_means = checkpoint_runs["hold7v2"]
    predicted_ah, prediction_id = _predict_cca_ah_and_prediction_id(
        conn, ah_run, x_with_y, lot_id, "sae_cca", source
    )

    if hold_run is None:
        return _cca_checkpoint_unavailable_block(ah_run, predicted_ah)

    predicted_hold_7v2 = predict(hold_run["coefficients"], hold_run["intercept"], x_with_y)
    verdict = judge_sae_cca(predicted_hold_7v2)
    spec = {**_NO_SPEC_LOWER, "spec_result": verdict["result"], "note": verdict["note"]}

    causes: list[dict] = []
    if verdict["result"] == "fail":
        causes = rank_causes(hold_run["x_columns"], hold_run["coefficients"], x_with_y, hold_means)

    _save_cca_verdict(
        conn, lot_id, prediction_id, "sae_cca", verdict["result"],
        {"hold_7v2_sec_min": verdict["hold_7v2_sec_min"]}, causes,
    )

    return {
        "available": True,
        "run_id": ah_run["run_id"] if ah_run else None,
        "run_at": ah_run.get("run_at") if ah_run else None,
        "predicted_value": predicted_ah,
        "predicted_hold_7v2_sec": predicted_hold_7v2,
        "input_y_source": "predicted",
        "spec": spec,
        "causes": causes,
    }


def _predict_en_cca_block(
    conn, ah_run: dict | None, checkpoint_runs: dict, lot_id: str | None, x_with_y: dict, source: str
) -> dict:
    """EN CCA(Z3) 예측 — 판정은 방전량(Ah)이 아니라 10초 전압·6.0V 지속시간 체크포인트 회귀
    2개로 한다(`cca_spec.judge_en_cca`는 둘 다 필요, `.docs/29`). 원인진단도 두 회귀의 `rank_causes`
    결과를 합쳐 |기여도| 기준으로 다시 정렬해 상위 3개만 남긴다."""
    voltage_run, voltage_means = checkpoint_runs["voltage"]
    hold_run, hold_means = checkpoint_runs["hold6v"]
    predicted_ah, prediction_id = _predict_cca_ah_and_prediction_id(
        conn, ah_run, x_with_y, lot_id, "en_cca", source
    )

    if voltage_run is None or hold_run is None:
        return _cca_checkpoint_unavailable_block(ah_run, predicted_ah)

    predicted_voltage_10s = predict(voltage_run["coefficients"], voltage_run["intercept"], x_with_y)
    predicted_hold_6v = predict(hold_run["coefficients"], hold_run["intercept"], x_with_y)
    verdict = judge_en_cca(predicted_voltage_10s, predicted_hold_6v)
    spec = {**_NO_SPEC_LOWER, "spec_result": verdict["result"], "note": verdict["note"]}

    causes: list[dict] = []
    if verdict["result"] == "fail":
        voltage_causes = rank_causes(voltage_run["x_columns"], voltage_run["coefficients"], x_with_y, voltage_means)
        hold_causes = rank_causes(hold_run["x_columns"], hold_run["coefficients"], x_with_y, hold_means)
        # 두 회귀(전압10초·6.0V지속)가 같은 factor를 원인으로 꼽을 수 있어(둘 다 X셋을 공유),
        # 합친 뒤 factor 기준으로 중복 제거해야 한다 — 그러지 않으면 프런트(CausesList)가 같은
        # factor를 키로 쓰는 리스트를 두 번 렌더링해 React key 중복 경고·DOM 오염이 생긴다.
        by_factor: dict[str, dict] = {}
        for c in voltage_causes + hold_causes:
            existing = by_factor.get(c["factor"])
            if existing is None or abs(c["contribution"]) > abs(existing["contribution"]):
                by_factor[c["factor"]] = c
        causes = sorted(by_factor.values(), key=lambda c: -abs(c["contribution"]))[:3]
        for i, c in enumerate(causes, start=1):
            c["rank"] = i

    _save_cca_verdict(
        conn, lot_id, prediction_id, "en_cca", verdict["result"],
        {"voltage_10s_min": verdict["voltage_10s_min"], "hold_6v_sec_min": verdict["hold_6v_sec_min"]}, causes,
    )

    return {
        "available": True,
        "run_id": ah_run["run_id"] if ah_run else None,
        "run_at": ah_run.get("run_at") if ah_run else None,
        "predicted_value": predicted_ah,
        "predicted_voltage_10s": predicted_voltage_10s,
        "predicted_hold_6v_sec": predicted_hold_6v,
        "input_y_source": "predicted",
        "spec": spec,
        "causes": causes,
    }


def _is_outlier(predicted_y: float, predicted_z: float, capacity_rate_pred: float) -> bool:
    y_out = not (_OUTLIER_Y_RANGE[0] <= predicted_y <= _OUTLIER_Y_RANGE[1])
    z_out = predicted_z < 0 or capacity_rate_pred < 0
    return y_out or z_out


@router.post("/predict/manual")
def predict_manual(payload: ManualPredictRequest):
    """조건 시뮬레이션(수동 입력) — 1단→2단 순차 예측 + SPEC 판정 + 원인진단을 한 번에 수행."""
    missing = [c for c in X_COLUMNS if c not in payload.x]
    if missing:
        raise HTTPException(status_code=400, detail={"missing_x_columns": missing})

    conn = repo.get_connection()
    try:
        y_run = _require_latest_run(conn, "x_to_y")
        y_training_rows = repo.get_x_to_y_training_rows(conn)
        y_means = compute_factor_means(y_training_rows, X_COLUMNS)

        predicted_y = predict(y_run["coefficients"], y_run["intercept"], payload.x)
        y_prediction_id = repo.save_prediction(
            conn, None, y_run["run_id"], "y", predicted_y, None, "manual"
        )

        thresholds = repo.get_spec_threshold_for_model(conn, payload.model_name)
        y_spec = _judge_and_maybe_save(
            conn, None, y_prediction_id, "y", predicted_y, thresholds.get("spec_lower_y")
        )
        y_causes = _diagnose_if_fail(
            conn, None, y_prediction_id, "y", y_spec["spec_result"],
            X_COLUMNS, y_run["coefficients"], payload.x, y_means,
        )

        z_run = repo.get_latest_analysis_run(conn, "xy_to_z")
        z_block: dict = {"available": False}
        if z_run is not None:
            z_x_columns = z_run["x_columns"]
            x_with_y = {**payload.x, "retention_rate": predicted_y}
            predicted_z = predict(z_run["coefficients"], z_run["intercept"], x_with_y)

            try:
                rated_capacity = parse_rated_capacity_from_model_name(payload.model_name)
            except ValueError:
                rated_capacity = None
            capacity_rate_pred = (
                (predicted_z / rated_capacity * 100) if rated_capacity else None
            )

            z_prediction_id = repo.save_prediction(
                conn, None, z_run["run_id"], "z", predicted_z, "predicted", "manual"
            )
            z_spec = _judge_and_maybe_save(
                conn, None, z_prediction_id, "z", capacity_rate_pred, thresholds.get("spec_lower_z")
            )
            z_training_rows = repo.get_xy_to_z_training_rows(conn)
            z_means = compute_factor_means(z_training_rows, z_x_columns)
            z_causes = _diagnose_if_fail(
                conn, None, z_prediction_id, "z", z_spec["spec_result"],
                z_x_columns, z_run["coefficients"], x_with_y, z_means,
            )
            z_block = {
                "available": True,
                "run_id": z_run["run_id"],
                "run_at": z_run.get("run_at"),
                "predicted_discharge_amount": predicted_z,
                "predicted_capacity_rate": capacity_rate_pred,
                "input_y_source": "predicted",
                "spec": z_spec,
                "causes": z_causes,
            }

        x_with_y = {**payload.x, "retention_rate": predicted_y}
        sae_cca_run = _load_cca_ah_run(conn, "xy_to_sae_cca")
        en_cca_run = _load_cca_ah_run(conn, "xy_to_en_cca")
        checkpoint_runs = _load_checkpoint_runs(conn)
        sae_cca_block = _predict_sae_cca_block(conn, sae_cca_run, checkpoint_runs, None, x_with_y, "manual")
        en_cca_block = _predict_en_cca_block(conn, en_cca_run, checkpoint_runs, None, x_with_y, "manual")

        return {
            "model_name": payload.model_name,
            "y": {
                "run_id": y_run["run_id"],
                "run_at": y_run.get("run_at"),
                "predicted_value": predicted_y,
                "spec": y_spec,
                "causes": y_causes,
            },
            "z": z_block,
            "sae_cca": sae_cca_block,
            "en_cca": en_cca_block,
        }
    finally:
        conn.close()


@router.post("/predict/batch-unmatched")
def predict_batch_unmatched():
    """④-1/④-2 미매칭 로트 Y·Z 일괄 예측(시험 미실시 로트 전체 대상)."""
    conn = repo.get_connection()
    try:
        y_run = _require_latest_run(conn, "x_to_y")
        z_run = repo.get_latest_analysis_run(conn, "xy_to_z")

        lots = repo.get_unmatched_lots_x(conn)
        y_training_rows = repo.get_x_to_y_training_rows(conn)
        y_means = compute_factor_means(y_training_rows, X_COLUMNS)
        z_training_rows = repo.get_xy_to_z_training_rows(conn) if z_run else []
        z_means = compute_factor_means(z_training_rows, z_run["x_columns"]) if z_run else {}
        thresholds_by_model = {r["model_name"]: r for r in repo.get_spec_thresholds(conn)}
        sae_cca_run = _load_cca_ah_run(conn, "xy_to_sae_cca")
        en_cca_run = _load_cca_ah_run(conn, "xy_to_en_cca")
        checkpoint_runs = _load_checkpoint_runs(conn)

        results = []
        for lot in lots:
            x = {c: lot[c] for c in X_COLUMNS}
            model_name = lot["model_name"]
            model_thresholds = thresholds_by_model.get(model_name, {})

            spec_lower_y = model_thresholds.get("spec_lower_y")
            if spec_lower_y is None:
                spec_lower_y = DEFAULT_SPEC_LOWER_Y
            spec_lower_z = model_thresholds.get("spec_lower_z")
            if spec_lower_z is None:
                spec_lower_z = DEFAULT_SPEC_LOWER_Z

            predicted_y = predict(y_run["coefficients"], y_run["intercept"], x)
            y_prediction_id = repo.save_prediction(
                conn, lot["lot_id"], y_run["run_id"], "y", predicted_y, None, "batch_unmatched"
            )
            y_spec = _judge_and_maybe_save(
                conn, lot["lot_id"], y_prediction_id, "y", predicted_y, spec_lower_y,
            )
            _diagnose_if_fail(
                conn, lot["lot_id"], y_prediction_id, "y", y_spec["spec_result"],
                X_COLUMNS, y_run["coefficients"], x, y_means,
            )

            x_with_y = {**x, "retention_rate": predicted_y}

            z_entry: dict = {"available": False}
            capacity_rate_pred = None
            predicted_z = None
            if z_run is not None:
                predicted_z = predict(z_run["coefficients"], z_run["intercept"], x_with_y)
                rated_capacity = lot["rated_capacity"]
                capacity_rate_pred = (
                    (predicted_z / rated_capacity * 100) if rated_capacity else None
                )
                z_prediction_id = repo.save_prediction(
                    conn, lot["lot_id"], z_run["run_id"], "z", predicted_z, "predicted", "batch_unmatched"
                )
                z_spec = _judge_and_maybe_save(
                    conn, lot["lot_id"], z_prediction_id, "z", capacity_rate_pred, spec_lower_z,
                )
                _diagnose_if_fail(
                    conn, lot["lot_id"], z_prediction_id, "z", z_spec["spec_result"],
                    z_run["x_columns"], z_run["coefficients"], x_with_y, z_means,
                )
                z_entry = {
                    "available": True,
                    "predicted_discharge_amount": predicted_z,
                    "predicted_capacity_rate": capacity_rate_pred,
                    "spec": z_spec,
                    "input_y_source": "predicted",
                }

            is_outlier = _is_outlier(
                predicted_y, predicted_z if predicted_z is not None else 0.0,
                capacity_rate_pred if capacity_rate_pred is not None else 0.0,
            )

            sae_cca_entry = _predict_sae_cca_block(
                conn, sae_cca_run, checkpoint_runs, lot["lot_id"], x_with_y, "batch_unmatched"
            )
            en_cca_entry = _predict_en_cca_block(
                conn, en_cca_run, checkpoint_runs, lot["lot_id"], x_with_y, "batch_unmatched"
            )

            results.append({
                "lot_id": lot["lot_id"],
                "model_name": model_name,
                "uploaded_date": lot["uploaded_date"],
                "y": {"predicted_value": predicted_y, "spec": y_spec},
                "z": z_entry,
                "sae_cca": sae_cca_entry,
                "en_cca": en_cca_entry,
                "is_outlier": is_outlier,
            })

        def _run_summary(run: dict | None) -> dict | None:
            return {"run_id": run["run_id"], "run_at": run.get("run_at"), "n": run.get("n")} if run else None

        return {
            "total": len(results),
            "y_run": _run_summary(y_run),
            "z_run": _run_summary(z_run),
            "sae_cca_run": _run_summary(sae_cca_run),
            "en_cca_run": _run_summary(en_cca_run),
            "results": results,
        }
    finally:
        conn.close()
