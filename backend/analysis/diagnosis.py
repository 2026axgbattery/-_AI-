"""SPEC 판정·원인진단(⑤). 순수 함수만 둔다(웹 프레임워크·DB 비의존).

`docs/prd.md` §6-⑤ 기준. 원인진단 수식("회귀계수 × SPEC 이탈 정도")은 PRD에 구체적 계산식이
명시돼 있지 않아 `history/17_day3-예측-spec판정-원인진단-구현계획.md`에서 다음과 같이 정했다:

    contribution_i = coefficient_i * (x_i - mean_i)

`mean_i`는 그 회귀를 학습한 표본의 인자 평균이다. 관리기준(SPEC) 같은 구체적 수치는 확보한
적이 없으므로 지어내지 않고, 실제로 가진 훈련 데이터 평균과의 비교로 권고 문구를 만든다.
"""
from __future__ import annotations

# 인자별 권고 문구(방향별). §6-⑤: "주액량 증대"로만 귀결되지 않도록 인자마다 다른 공정 단계를
# 가리키게 분기한다.
_RECOMMENDATIONS: dict[str, dict[str, str]] = {
    "electrolyte_temp": {
        "high": "전해액온도가 훈련 데이터 평균보다 높습니다 — 전해액 주입 전 예비냉각 공정과 조 내 온도센서 캘리브레이션을 점검하세요.",
        "low": "전해액온도가 훈련 데이터 평균보다 낮습니다 — 예비가온 공정과 온도센서 캘리브레이션을 점검하세요.",
    },
    "tank_temp": {
        "high": "수조온도가 훈련 데이터 평균보다 높습니다 — 수조 온도 제어 설비를 점검하세요.",
        "low": "수조온도가 훈련 데이터 평균보다 낮습니다 — 수조 온도 제어 설비를 점검하세요.",
    },
    "soaking_time_sec": {
        "high": "함침시간이 훈련 데이터 평균보다 깁니다 — 함침 공정 타이머 설정을 점검하세요.",
        "low": "함침시간이 훈련 데이터 평균보다 짧습니다 — 함침 공정 타이머 설정을 점검하세요.",
    },
    "aging_days": {
        "high": "에이징일수가 훈련 데이터 평균보다 깁니다 — 에이징 팔레트 운용 일정을 점검하세요.",
        "low": "에이징일수가 훈련 데이터 평균보다 짧습니다 — 에이징 팔레트 운용 일정을 점검하세요.",
    },
    "formation_dv": {
        "high": "화성전압차(2차-1차)가 훈련 데이터 평균보다 큽니다 — 화성 충전 레시피를 점검하세요.",
        "low": "화성전압차(2차-1차)가 훈련 데이터 평균보다 작습니다 — 화성 충전이 목표치까지 도달했는지 점검하세요(화성 부족·계량오류 가능).",
    },
    "cell_weight_mean": {
        "high": "6셀 평균 중량이 훈련 데이터 평균보다 무겁습니다 — 극판 도포량 설정을 점검하세요.",
        "low": "6셀 평균 중량이 훈련 데이터 평균보다 가볍습니다 — 극판 도포량 설정을 점검하세요.",
    },
    "cell_weight_std": {
        "high": "6셀 간 중량 편차가 훈련 데이터 평균보다 큽니다 — 극판 도포·재단 공정의 셀간 균일성을 점검하세요.",
        "low": "6셀 간 중량 편차가 훈련 데이터 평균보다 작습니다.",
    },
    "charge_ratio": {
        "high": "충전율(정격 대비 %)이 훈련 데이터 평균보다 높습니다 — 과충전에 따른 산소 재결합·물 전기분해량 증가 가능성을 점검하세요.",
        "low": "충전율(정격 대비 %)이 훈련 데이터 평균보다 낮습니다 — 화성 충전 레시피의 목표 충전율 도달 여부를 점검하세요.",
    },
    "retention_rate": {
        "high": "포화도(Y)가 훈련 데이터 평균보다 높습니다.",
        "low": "포화도(Y)가 훈련 데이터 평균보다 낮습니다 — 액 부피 자체보다 화성으로 인한 극판 공극 증가가 원인일 수도 있습니다(주액량 증대만이 해법은 아님, docs/prd.md §6-③).",
    },
}


def compute_factor_means(rows: list[dict], columns: list[str]) -> dict[str, float]:
    """훈련 표본(rows)에서 각 컬럼의 평균을 계산한다. `rank_causes`의 `factor_means` 입력용."""
    means: dict[str, float] = {}
    for col in columns:
        values = [r[col] for r in rows if r.get(col) is not None]
        if values:
            means[col] = sum(values) / len(values)
    return means


def judge_spec(value: float | None, spec_lower: float | None) -> dict:
    """value(예측/실측)를 spec_lower(SPEC 하한)와 비교. spec_lower가 없으면 판정 불가(§8)."""
    if spec_lower is None:
        return {
            "spec_result": None,
            "spec_lower": None,
            "deviation": None,
            "note": "SPEC 미설정, 판정 불가",
        }
    if value is None:
        return {
            "spec_result": None,
            "spec_lower": spec_lower,
            "deviation": None,
            "note": "예측값 없음",
        }
    deviation = value - spec_lower
    return {
        "spec_result": "pass" if deviation >= 0 else "fail",
        "spec_lower": spec_lower,
        "deviation": deviation,
        "note": None,
    }


def rank_causes(
    x_columns: list[str],
    coefficients: dict[str, float],
    x_values: dict[str, float],
    factor_means: dict[str, float],
    top_n: int = 3,
) -> list[dict]:
    """인자별 기여도(계수 × 평균 대비 편차)로 원인 인자 순위화 + 권고 문구.

    동률(같은 |contribution|) 처리 규칙은 §10-12 확정 전까지 임시로 "계수 절댓값 큰 순 +
    동률 시 인자명 알파벳 순"을 적용한다. TODO: §10-12 확정되면 이 임시 규칙을 교체할 것.
    """
    ranked: list[dict] = []
    for col in x_columns:
        if col not in x_values or col not in factor_means or col not in coefficients:
            continue
        # x_values[col]은 키가 있어도 값이 None일 수 있다(예: retention_rate가 미측정인 로트를
        # X+Y→Z 원인진단에 넣는 경우) — None - float는 TypeError이므로 여기서 건너뛴다.
        if x_values[col] is None or factor_means[col] is None:
            continue
        deviation = x_values[col] - factor_means[col]
        contribution = coefficients[col] * deviation
        direction = "high" if deviation >= 0 else "low"
        recommendation = _RECOMMENDATIONS.get(col, {}).get(
            direction, f"{col} 값이 훈련 데이터 평균과 다릅니다."
        )
        ranked.append({
            "factor": col,
            "contribution": contribution,
            "value": x_values[col],
            "mean": factor_means[col],
            "deviation": deviation,
            "recommendation": recommendation,
        })

    ranked.sort(key=lambda r: (-abs(r["contribution"]), -abs(coefficients[r["factor"]]), r["factor"]))
    for i, r in enumerate(ranked[:top_n], start=1):
        r["rank"] = i
    return ranked[:top_n]
