"""1·2단 캐스케이드 회귀(X→Y, X+Y→Z, X→Z 베이스라인). `docs/prd.md` §6-③ 기준.

순수 함수만 둔다(웹 프레임워크·DB 비의존) — 라우터(`backend/routers/dashboard.py`)만 이 모듈을 호출하고,
학습 데이터 조회는 `backend/db/repository.py`가 담당한다.
"""
from __future__ import annotations

from sklearn.linear_model import LinearRegression

from backend.analysis.significance import pearson_r_p
from backend.analysis.vif import compute_vif

# 1단 X셋(docs/prd.md §6-③-1). fill_weight/water_loss/mt_voltage/mt_current는 Y를 구성하거나
# 시험 전용 컬럼이라 원천 제외한다.
X_COLUMNS = [
    "electrolyte_temp", "tank_temp", "soaking_time_sec", "aging_days",
    "formation_dv", "cell_weight_mean", "cell_weight_std", "charge_ratio",
    "charge_program_deviation_pct",
]
_FORBIDDEN_X_COLUMNS = {"fill_weight", "water_loss", "mt_voltage", "mt_current"}


class InsufficientSampleError(ValueError):
    """회귀에 필요한 최소 표본 수를 만족하지 못했을 때(에러가 아니라 정상적인 데이터 부족 상태)."""


def _fit_linear(rows: list[dict], x_columns: list[str], target: str) -> dict:
    forbidden_used = _FORBIDDEN_X_COLUMNS & set(x_columns)
    if forbidden_used:
        raise ValueError(f"1단 X에서 제외해야 하는 컬럼이 섞여 있습니다: {forbidden_used}")

    valid_rows = [
        r for r in rows
        if all(r.get(c) is not None for c in x_columns) and r.get(target) is not None
    ]
    min_required = len(x_columns) + 2
    if len(valid_rows) < min_required:
        raise InsufficientSampleError(
            f"회귀에 필요한 최소 표본 수({min_required}건) 미달: 유효 표본 {len(valid_rows)}건"
        )

    x_matrix = [[r[c] for c in x_columns] for r in valid_rows]
    y_vector = [r[target] for r in valid_rows]

    model = LinearRegression()
    model.fit(x_matrix, y_vector)
    r_squared = model.score(x_matrix, y_vector)

    columns_data = {c: [r[c] for r in valid_rows] for c in x_columns}
    vif = compute_vif(columns_data)
    significance = {c: pearson_r_p(columns_data[c], y_vector) for c in x_columns}

    return {
        "target": target,
        "x_columns": x_columns,
        "coefficients": dict(zip(x_columns, (float(c) for c in model.coef_), strict=True)),
        "intercept": float(model.intercept_),
        "r_squared": float(r_squared),
        "vif": vif,
        "significance": significance,
        "n": len(valid_rows),
    }


def fit_x_to_y(rows: list[dict]) -> dict:
    """1단(X→Y): 1단 X셋 → retention_rate(Y, 잔존율 proxy). rows는 ProcessData+LotDerived 조인 결과."""
    return _fit_linear(rows, X_COLUMNS, "retention_rate")


def fit_xy_to_z(rows: list[dict]) -> dict:
    """2단(X+Y→Z): 1단 X셋 + 실측 retention_rate → discharge_amount. rows는 시험 매칭 로트만(학습은 반드시 실측 Y로)."""
    return _fit_linear(rows, [*X_COLUMNS, "retention_rate"], "discharge_amount")


def fit_x_to_z_baseline(rows: list[dict]) -> dict:
    """베이스라인(X→Z): 1단 X셋만(Y 없이) → discharge_amount. 캐스케이드와 비교하기 위한 대조군."""
    return _fit_linear(rows, X_COLUMNS, "discharge_amount")


def fit_xy_to_sae_cca(rows: list[dict]) -> dict:
    """2단(X+Y→SAE CCA, 신규 history/19 Phase C): 1단 X셋 + 실측 retention_rate → sae_cca.
    현재 신뢰성 배치 표본이 n=2뿐이라 `InsufficientSampleError`가 정상적으로 발생할 수 있다."""
    return _fit_linear(rows, [*X_COLUMNS, "retention_rate"], "sae_cca")


def fit_xy_to_en_cca(rows: list[dict]) -> dict:
    """2단(X+Y→EN CCA, 신규 history/19 Phase C): 1단 X셋 + 실측 retention_rate → en_cca.
    현재 신뢰성 배치 표본이 n=2뿐이라 `InsufficientSampleError`가 정상적으로 발생할 수 있다."""
    return _fit_linear(rows, [*X_COLUMNS, "retention_rate"], "en_cca")


def fit_xy_to_en_cca_voltage10s(rows: list[dict]) -> dict:
    """EN CCA 10초 전압 체크포인트 예측(.docs/24) — EN/SAE 합격배지(cca_spec.py)는 방전량이 아니라
    이 전압·지속시간 체크포인트로 판정되므로, "예측 합격/불합격"을 만들려면 이 값 자체를 예측해야
    한다. 채점 모듈에서 그때그때 학습하는 비영속 회귀라 AnalysisRun에는 저장하지 않는다."""
    return _fit_linear(rows, [*X_COLUMNS, "retention_rate"], "en_cca_10s_voltage")


def fit_xy_to_en_cca_hold6v(rows: list[dict]) -> dict:
    """EN CCA 6.0V까지 지속시간(초) 체크포인트 예측. 위 함수와 동일 취지(.docs/24)."""
    return _fit_linear(rows, [*X_COLUMNS, "retention_rate"], "en_cca_6v_hold_sec")


def fit_xy_to_sae_cca_hold7v2(rows: list[dict]) -> dict:
    """SAE CCA 7.2V까지 지속시간(초) 체크포인트 예측. 위 함수와 동일 취지(.docs/24)."""
    return _fit_linear(rows, [*X_COLUMNS, "retention_rate"], "sae_cca_7v2_hold_sec")


def predict(coefficients: dict[str, float], intercept: float, x: dict[str, float]) -> float:
    """저장된 회귀계수를 실제 X(+Ŷ) 값에 적용한 예측값. Day 3 예측 화면(④)에서 재사용."""
    return sum(coefficients[col] * x[col] for col in coefficients) + intercept
