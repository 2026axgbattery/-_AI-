"""AGM60_S1/AGM70_S1 신규 더미 데이터 생성 스크립트(`.docs/21`, `.docs/26` 참조).

기존 `process_data.csv`의 실측 분포에서 형명별 약 500행(총 약 1,000행)의 공정 데이터를
합성하고, 그중 형명별 20개 lot_id를 골라 시험 raw 워크북("AGM 시험현황_raw data.xlsx"와
같은 세로 시험항목 트리 구조)을 만든다.

**2026-09-25 재설계(`.docs/26`)**: 최초 버전은 공정 인자(X)를 완전히 독립적으로 샘플링해
Y(포화도/잔존율)·Z(20시간 용량)·CCA 체크포인트가 X와 실제로 연결되지 않았다(1단 회귀
R²=0.032, VIF 최대 61.9, CCA 채점 71~74%가 사실상 구조적 한계였음). 이번 버전은
`docs/correlation-reliability-review.md`에 실측 검증된 방향·크기(셀중량표준편차·충전율→Y,
전해액온도·충전율·수조온도·Y→Z)를 "수식 + 가우시안 노이즈"로 반영해, 회귀분석이 실제로
학습할 신호가 있는 더미 데이터를 만든다. 또한 charge_ratio·전해액온도·수조온도 등 물리적으로
정격용량과 무관해야 하는 공정 조건은 형명별이 아니라 **전체 실측 데이터 풀에서 공통 분포**로
샘플링해, 두 형명을 합친 회귀에서 발생하던 인위적 다중공선성(VIF 급등)을 없앤다.

저장소 루트에서 실행: python scripts/generate_agm60_70_dummy.py
산출물: "더미 데이터_process.csv", "더미 데이터_test.xlsx" (둘 다 저장소 루트)
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import openpyxl
import pandas as pd

SOURCE_PROCESS_CSV = "process_data.csv"
SOURCE_TEST_CSV = "test_data.csv"
OUT_PROCESS = "더미 데이터_process.csv"
OUT_TEST = "더미 데이터_test.xlsx"
RNG_SEED = 7
YEAR = 2026
BUYER_SUFFIX = "S1"  # ChargeProgramSpec에 buyer_code='S'가 60/70Ah 둘 다 있어 X 결측을 막음

MODELS = {
    60.0: "AGM60_S1",
    70.0: "AGM70_S1",
}
ROWS_PER_MODEL = 5000
TEST_SAMPLES_PER_MODEL = 5000  # 2026-09-25: CCA 회귀가 "표본 부족" 경고 없이 항상 가능하도록 대량화(형명당 전량 시험)

PROCESS_COLUMNS = [
    "lot_id", "model_name", "line_no", "prod_date",
    "cell1_weight", "cell2_weight", "cell3_weight", "cell4_weight", "cell5_weight", "cell6_weight",
    "cell1_ginap", "cell2_ginap", "cell3_ginap", "cell4_ginap", "cell5_ginap", "cell6_ginap",
    "fill_weight", "water_loss", "voltage_1st", "bath_no", "circuit_no",
    "soaking_time_sec", "aging_days", "voltage_2nd", "electrolyte_temp", "charge_amount", "tank_temp",
]

# 물리적으로 정격용량(모델 크기)과 무관해야 하는 "공정 조건" 컬럼 — 전체 실측 데이터 풀에서
# 공통 분포로 샘플링한다(docs/correlation-reliability-review.md §3 "무차원화가 다중공선성을
# 해소" 원칙을 생성 단계에서부터 지킴). charge_ratio는 원본에 없는 파생값이라 별도 계산한다.
_POOLED_COLUMNS = [
    "electrolyte_temp", "tank_temp", "soaking_time_sec", "aging_days",
    "voltage_1st", "voltage_2nd", "bath_no", "circuit_no", "line_no",
]

# 배터리 크기(정격용량)에 physically 비례하는 컬럼 — 형명별(용량군별) 분포를 그대로 쓴다.
_CAPACITY_GROUP_COLUMNS = ["fill_weight"]

# 실측 검증된 상관관계(docs/correlation-reliability-review.md). 값은 (변수, 부호 포함 목표 r).
Y_DRIVERS = {"cell_weight_std": -0.308, "charge_ratio": 0.210}
Z_DRIVERS = {"electrolyte_temp": 0.613, "charge_ratio": 0.650, "tank_temp": 0.400, "retention_rate": 0.228}
Z_TARGET_R2 = 0.75  # 개별 r 절대값 제곱합(1.01)이 1을 넘어 독립성분으로 못 쓰므로, 비율은 유지하되 전체 설명력만 캘리브레이션
CCA_DRIVERS = {"cell_weight_std": -0.35, "charge_ratio": 0.25, "electrolyte_temp": 0.20}
CCA_TARGET_R2 = 0.55  # docs에 실측 근거가 없는 신규(v1.1) 필드라 Y·Z보다 보수적으로 설정

# 실측 데이터(process_data.csv+test_data.csv 매칭 59건) 기준 모수 — `docs/correlation-reliability-review.md`,
# `docs/prd.md` §10에 이미 인용된 값과 동일. CSV가 바뀌지 않는 한 재계산 불필요.
Y_MEAN, Y_STD = 92.09, 0.97
Z_MEAN, Z_STD = 97.70, 2.59


def _unit_weights(drivers: dict[str, float]) -> dict[str, float]:
    """r 절대값 비율을 유지한 채 (부호 포함) 단위벡터로 정규화."""
    norm = float(np.sqrt(sum(v * v for v in drivers.values())))
    return {k: v / norm for k, v in drivers.items()}


def _pooled_stats() -> dict[str, tuple[float, float, float, float]]:
    """공정 조건 컬럼의 전체(형명 무관) 마진 분포 — process_data.csv 전 행 기준."""
    df = pd.read_csv(SOURCE_PROCESS_CSV)
    stats: dict[str, tuple[float, float, float, float]] = {}
    for col in _POOLED_COLUMNS:
        series = df[col].dropna()
        mean, std = float(series.mean()), float(series.std())
        stats[col] = (mean, max(std, 1e-6), float(series.min()), float(series.max()))
    # charge_ratio는 원본에 컬럼이 없어 charge_amount/rated_capacity로 직접 계산한다.
    rated = df["model_name"].str.extract(r"[A-Za-z]+(\d+)_")[0].astype(float)
    charge_ratio = df["charge_amount"] / rated * 100
    stats["charge_ratio"] = (
        float(charge_ratio.mean()), float(charge_ratio.std()),
        float(charge_ratio.min()), float(charge_ratio.max()),
    )
    # cell_weight_std(로트 내 6셀 편차)의 실측 분포 — Y·CCA의 핵심 드라이버이자
    # 개별 셀 중량을 역산할 때의 "목표 편차"로 재사용한다.
    cellcols = [f"cell{i}_weight" for i in range(1, 7)]
    cws = df[cellcols].std(axis=1, ddof=0)
    stats["cell_weight_std"] = (
        float(cws.mean()), float(cws.std()), float(cws.min()), float(cws.max()),
    )
    return stats


def _capacity_group_stats(rated_capacity: float) -> dict[str, tuple[float, float, float, float]]:
    """정격용량에 physically 비례하는 컬럼(fill_weight, cell_weight_mean)의 형명별 분포."""
    df = pd.read_csv(SOURCE_PROCESS_CSV)
    rated = df["model_name"].str.extract(r"[A-Za-z]+(\d+)_")[0].astype(float)
    sub = df[rated == rated_capacity]
    stats: dict[str, tuple[float, float, float, float]] = {}
    for col in _CAPACITY_GROUP_COLUMNS:
        series = sub[col].dropna()
        mean, std = float(series.mean()), float(series.std())
        stats[col] = (mean, max(std, 1e-6), float(series.min()), float(series.max()))
    cellcols = [f"cell{i}_weight" for i in range(1, 7)]
    cell_mean = sub[cellcols].mean(axis=1)
    stats["cell_weight_mean"] = (
        float(cell_mean.mean()), float(cell_mean.std()), float(cell_mean.min()), float(cell_mean.max()),
    )
    return stats


def _sample(rng: np.random.Generator, stats: dict, col: str) -> float:
    mean, std, lo, hi = stats[col]
    return float(np.clip(rng.normal(mean, std), lo, hi))


def _make_lot_id(rng: np.random.Generator, rated_capacity: float, month_idx: int) -> str:
    cap_prefix = f"{int(rated_capacity):03d}"
    month_letter = "ABCDEFGHIJKL"[month_idx - 1]
    serial = rng.integers(0, 10**9)
    return f"{cap_prefix}C{YEAR % 100}{month_letter}{serial:09d}{BUYER_SUFFIX}"


def _prod_date(rng: np.random.Generator, month_idx: int) -> dt.date:
    return dt.date(YEAR, month_idx, int(rng.integers(1, 28)))


def build_process_rows() -> list[dict]:
    pooled = _pooled_stats()
    y_w = _unit_weights(Y_DRIVERS)

    rows: list[dict] = []
    for rated_capacity, model_name in MODELS.items():
        cap_stats = _capacity_group_stats(rated_capacity)
        rng = np.random.default_rng(RNG_SEED + int(rated_capacity))
        n_months = 10
        per_month = ROWS_PER_MODEL // n_months
        for month_idx in range(1, n_months + 1):
            for _ in range(per_month):
                row: dict = {
                    "lot_id": _make_lot_id(rng, rated_capacity, month_idx),
                    "model_name": model_name,
                    "prod_date": _prod_date(rng, month_idx),
                }
                for col in _POOLED_COLUMNS:
                    row[col] = _sample(rng, pooled, col)
                charge_ratio = _sample(rng, pooled, "charge_ratio")
                cell_weight_std_target = _sample(rng, pooled, "cell_weight_std")
                cell_weight_mean = _sample(rng, cap_stats, "cell_weight_mean")
                fill_weight = _sample(rng, cap_stats, "fill_weight")

                # X→Y(잔존율) — 실측 r(-0.308, +0.210)을 그대로 신호 크기로 사용(합이 1을
                # 넘지 않아 독립성분 가정 그대로 적용 가능).
                z_cws = (cell_weight_std_target - pooled["cell_weight_std"][0]) / pooled["cell_weight_std"][1]
                z_cr = (charge_ratio - pooled["charge_ratio"][0]) / pooled["charge_ratio"][1]
                noise_std_y = float(np.sqrt(max(1.0 - Y_DRIVERS["cell_weight_std"] ** 2 - Y_DRIVERS["charge_ratio"] ** 2, 0.0)))
                raw_y = y_w["cell_weight_std"] * z_cws + y_w["charge_ratio"] * z_cr + noise_std_y * rng.normal()
                retention_rate = float(np.clip(Y_MEAN + Y_STD * raw_y, 88.0, 96.0))
                water_loss = fill_weight * (1 - retention_rate / 100)

                # 6셀 개별 중량 — 목표 로트내 편차(cell_weight_std_target)를 그대로 재현하도록
                # 평균 주위에 표준정규 노이즈*목표편차로 흩뿌린다(n=6이라 실현 std는 목표 근방에서 흔들림).
                cell_noise = rng.normal(0, 1, size=6)
                cell_weights = cell_weight_mean + cell_noise * cell_weight_std_target

                row["fill_weight"] = fill_weight
                row["water_loss"] = water_loss
                row["charge_amount"] = charge_ratio / 100 * rated_capacity
                for i in range(6):
                    row[f"cell{i + 1}_weight"] = cell_weights[i]
                    row[f"cell{i + 1}_ginap"] = float(np.clip(rng.normal(45.0, 1.0), 40.0, 50.0))
                row["_charge_ratio"] = charge_ratio
                row["_cell_weight_std"] = cell_weight_std_target
                row["_retention_rate"] = retention_rate
                row["_z_cr"] = z_cr
                row["_z_cws"] = z_cws
                row["_rated_capacity"] = rated_capacity
                rows.append(row)

    for row in rows:
        for col in ("cell1_weight", "cell2_weight", "cell3_weight", "cell4_weight", "cell5_weight", "cell6_weight"):
            row[col] = round(row[col], 3)
        for col in ("cell1_ginap", "cell2_ginap", "cell3_ginap", "cell4_ginap", "cell5_ginap", "cell6_ginap"):
            row[col] = round(row[col], 2)
        for col in ("line_no", "bath_no", "circuit_no", "soaking_time_sec", "aging_days"):
            row[col] = int(round(row[col]))
        for col in ("charge_amount", "electrolyte_temp", "tank_temp", "fill_weight", "water_loss"):
            row[col] = round(row[col], 1)
        for col in ("voltage_1st", "voltage_2nd"):
            row[col] = round(row[col], 2)

    assert len({r["lot_id"] for r in rows}) == len(rows), "lot_id 중복 발생"
    return rows


def _cca_values(rng: np.random.Generator, rated_capacity: float, z_cws: float, z_cr: float, electrolyte_temp: float, pooled: dict) -> dict:
    """CCA 체크포인트(전압·지속시간)를 공정 인자 기반 수식+노이즈로 생성 —
    이 값 자체가 `fit_xy_to_en_cca_voltage10s`류 회귀의 예측 타깃이자
    `cca_spec.judge_en_cca`/`judge_sae_cca`의 판정 대상이다(사전 배분 방식 폐기)."""
    cca_w = _unit_weights(CCA_DRIVERS)
    z_et = (electrolyte_temp - pooled["electrolyte_temp"][0]) / pooled["electrolyte_temp"][1]
    noise_std = float(np.sqrt(max(1.0 - CCA_TARGET_R2, 0.0)))
    shared = cca_w["cell_weight_std"] * z_cws + cca_w["charge_ratio"] * z_cr + cca_w["electrolyte_temp"] * z_et
    shared *= float(np.sqrt(CCA_TARGET_R2))

    # 평균을 판정 임계값(EN 7.5V/90초, SAE 30초)에서 약 1.2 표준편차 위로 잡아 합격률
    # ~85~90%인 "양산이 안정된 공정"을 재현한다 — 임계값 바로 근처(0.2~0.5σ)에 평균을 두면
    # 회귀가 설명하는 신호(R²)가 그대로여도 문턱 근방 표본이 너무 많아 판정 일치율이
    # 낮게 나온다(이론상 Δaccuracy, `history/26` 시뮬레이션으로 확인). 실측 20개 샘플 범위
    # (전압 7.0~7.9V, EN 46~129초, SAE 14~44초)보다 합격 쪽으로 다소 치우치지만, 표본이
    # 20건→5,000건으로 커지면 꼬리 값 자체가 넓어지는 것은 자연스럽다.
    en_10s_voltage = round(float(np.clip(7.85 + 0.22 * (shared + noise_std * rng.normal()), 6.9, 8.4)), 2)
    en_6v_hold_sec = round(float(np.clip(125.0 + 22.0 * (shared + noise_std * rng.normal()), 40.0, 170.0)), 1)
    sae_7v2_hold_sec = round(float(np.clip(40.0 + 7.0 * (shared + noise_std * rng.normal()), 12.0, 60.0)), 1)

    en_cca = round(rated_capacity * float(np.clip(0.10 + 0.01 * shared + rng.normal(0, 0.003), 0.09, 0.11)), 3)
    sae_cca = round(rated_capacity * float(np.clip(0.08 + 0.008 * shared + rng.normal(0, 0.003), 0.07, 0.09)), 3)
    return {
        "en_cca_10s_voltage": en_10s_voltage,
        "en_cca_6v_hold_sec": en_6v_hold_sec,
        "sae_cca_7v2_hold_sec": sae_7v2_hold_sec,
        "en_cca": en_cca,
        "sae_cca": sae_cca,
    }


def build_test_samples(process_rows: list[dict]) -> dict[str, list[dict]]:
    """형명별로 process_rows 중 20개 lot_id를 골라 raw 워크북용 시험 샘플을 만든다."""
    pooled = _pooled_stats()
    z_w = _unit_weights(Z_DRIVERS)
    noise_std_z = float(np.sqrt(max(1.0 - Z_TARGET_R2, 0.0)))

    by_model: dict[str, list[dict]] = {name: [] for name in MODELS.values()}
    for name in MODELS.values():
        candidates = [r for r in process_rows if r["model_name"] == name]
        rated_capacity = next(cap for cap, m in MODELS.items() if m == name)
        rng = np.random.default_rng(RNG_SEED + 1000 + int(rated_capacity))
        chosen_idx = np.linspace(0, len(candidates) - 1, TEST_SAMPLES_PER_MODEL).astype(int)
        chosen = [candidates[i] for i in chosen_idx]

        for proc_row in chosen:
            z_et = (proc_row["electrolyte_temp"] - pooled["electrolyte_temp"][0]) / pooled["electrolyte_temp"][1]
            z_tt = (proc_row["tank_temp"] - pooled["tank_temp"][0]) / pooled["tank_temp"][1]
            z_cr = proc_row["_z_cr"]
            z_y = (proc_row["_retention_rate"] - Y_MEAN) / Y_STD

            raw_z = (
                z_w["electrolyte_temp"] * z_et
                + z_w["charge_ratio"] * z_cr
                + z_w["tank_temp"] * z_tt
                + z_w["retention_rate"] * z_y
            ) * float(np.sqrt(Z_TARGET_R2)) + noise_std_z * rng.normal()
            capacity_rate = round(float(np.clip(Z_MEAN + Z_STD * raw_z, 90.0, 105.0)), 1)
            discharge_amount = round(rated_capacity * capacity_rate / 100, 2)
            charge_rate = round(float(rng.uniform(104, 110)), 1)
            charge_amount_20h = round(discharge_amount * charge_rate / 100, 2)

            sample = {
                "lot_id": proc_row["lot_id"],
                "initial_voltage": round(float(rng.uniform(12.80, 12.95)), 2),
                "initial_resistance": round(float(rng.uniform(3.0, 3.5)), 2),
                "initial_weight": round(rated_capacity * 288 + float(rng.normal(0, 60)), 0),
                "mt_voltage": round(float(rng.uniform(12.80, 12.90)), 2),
                "mt_current": round(rated_capacity * 11 + float(rng.normal(0, 15)), 0),
                "discharge_amount": discharge_amount,
                "charge_amount_20h": charge_amount_20h,
                "capacity_rate": capacity_rate,
                "charge_rate": charge_rate,
            }
            sample.update(
                _cca_values(rng, rated_capacity, proc_row["_z_cws"], z_cr, proc_row["electrolyte_temp"], pooled)
            )
            by_model[name].append(sample)
    return by_model


def _write_test_workbook(by_model: dict[str, list[dict]], rated_capacity_of: dict[str, float]) -> None:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    for model_name, samples in by_model.items():
        ws = wb.create_sheet(title=model_name)
        rated_capacity = rated_capacity_of[model_name]
        sheet_label = f"AGM{int(rated_capacity)}"
        n = len(samples)

        def row(section, field, values):
            ws.append([section, field, *values])

        row("구분", "시험항목", [sheet_label] + [None] * (n - 1))
        row("초기상태", "제조로트", [s["lot_id"] for s in samples])
        row(None, "전압", [s["initial_voltage"] for s in samples])
        row(None, "내부저항", [s["initial_resistance"] for s in samples])
        row(None, "중량", [s["initial_weight"] for s in samples])
        row("공정 SPC DATA", "MT(V)", [s["mt_voltage"] for s in samples])
        row(None, "MT(A)", [s["mt_current"] for s in samples])
        row("20HR용량(1차)", "방전량", [s["discharge_amount"] for s in samples])
        row(None, "충전량", [s["charge_amount_20h"] for s in samples])
        row(None, "용량(%)", [s["capacity_rate"] for s in samples])
        row(None, "충전율(%)", [s["charge_rate"] for s in samples])
        row("SAE CCA(1차)\n18℃ 24H 방치", "10초 전압", [None] * n)
        row(None, "7.2V 지속시간", [f"{s['sae_cca_7v2_hold_sec']:g}초" for s in samples])
        row(None, "방전량", [s["sae_cca"] for s in samples])
        row("EN CCA 18℃", "10초 전압", [s["en_cca_10s_voltage"] for s in samples])
        row(None, "6.0V 지속시간", [f"{s['en_cca_6v_hold_sec']:g}초" for s in samples])
        row(None, "방전량", [s["en_cca"] for s in samples])

    wb.save(OUT_TEST)


def main() -> None:
    process_rows = build_process_rows()
    process_df = pd.DataFrame(process_rows)[PROCESS_COLUMNS]
    assert len(process_df) == len(MODELS) * ROWS_PER_MODEL
    process_df.to_csv(OUT_PROCESS, index=False)

    by_model = build_test_samples(process_rows)
    rated_capacity_of = {name: cap for cap, name in MODELS.items()}
    _write_test_workbook(by_model, rated_capacity_of)

    from backend.analysis.cca_spec import judge_en_cca, judge_sae_cca  # noqa: E402 (스크립트 실행 시점 임포트)

    for model_name, samples in by_model.items():
        en_pass = sum(
            1 for s in samples if judge_en_cca(s["en_cca_10s_voltage"], s["en_cca_6v_hold_sec"])["result"] == "pass"
        )
        sae_pass = sum(
            1 for s in samples if judge_sae_cca(s["sae_cca_7v2_hold_sec"])["result"] == "pass"
        )
        print(
            f"[{model_name}] 시험 샘플={len(samples)}건, "
            f"EN 합격={en_pass}/{len(samples)}, SAE 합격={sae_pass}/{len(samples)}"
        )
    print(f"생성 완료: {OUT_PROCESS}({len(process_df)}행), {OUT_TEST}")


if __name__ == "__main__":
    main()
