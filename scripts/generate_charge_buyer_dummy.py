"""충전 프로그램("★ 260428 AGM CF 충전 프로그램 3.xlsx")에 등재된 바이어 코드를 기반으로,
아직 Lot 데이터가 없는 (정격용량, 바이어) 조합에 대해 신규 더미 데이터를 만든다(`.docs/31` 참조).

기존 Lot에는 6개 용량군 전체에 H/K/S 3개 바이어 코드만 있다 — 이 스크립트는 충전 프로그램
엑셀을 실제로 파싱해 그 외 바이어 코드(예: 60Ah의 B/D/Y/Z/C/G/V)를 자동으로 찾아내고,
`scripts/generate_agm60_70_dummy.py`(`.docs/26` 재설계)와 동일한 통계 로직(공정조건은 전체
풀 공통분포, 용량비례 컬럼은 용량군별 분포, Y/Z/CCA는 실측 검증된 방향·크기의 수식+노이즈)으로
모델당 소규모(공정데이터 60행 + 시험 20건) 더미를 생성한다.

`charge_amount`는 기존 로트와 동일하게 charge_ratio(정격용량 대비 ~100~125%) 기반 소규모
스케일을 그대로 쓴다 — 충전 프로그램 Total 충전량[Ah]과의 스케일 불일치는 별도로 추적 중인
이슈(`충전량_이탈도_점검.xlsx`)라 이 스크립트에서 임의로 재정의하지 않는다.

저장소 루트에서 실행: python scripts/generate_charge_buyer_dummy.py
산출물: "충전프로그램_바이어_더미_process.csv", "충전프로그램_바이어_더미_test.xlsx" (저장소 루트)
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import openpyxl
import pandas as pd

from backend.etl.charge_program import parse_charge_program_workbook

CHARGE_PROGRAM_XLSX = "★ 260428 AGM CF 충전 프로그램 3.xlsx"
SOURCE_PROCESS_CSV = "process_data.csv"
OUT_PROCESS = "충전프로그램_바이어_더미_process.csv"
OUT_TEST = "충전프로그램_바이어_더미_test.xlsx"
RNG_SEED = 42
YEAR = 2026

EXISTING_BUYERS = {"H", "K", "S"}  # 현재 Lot에 이미 있는 바이어 코드(6개 용량군 전체 공통)

ROWS_PER_MODEL = 60          # 월 5행 x 12개월 — 통계적 검정력이 아니라 커버리지 확인이 목적
TEST_SAMPLES_PER_MODEL = 20

PROCESS_COLUMNS = [
    "lot_id", "model_name", "line_no", "prod_date",
    "cell1_weight", "cell2_weight", "cell3_weight", "cell4_weight", "cell5_weight", "cell6_weight",
    "cell1_ginap", "cell2_ginap", "cell3_ginap", "cell4_ginap", "cell5_ginap", "cell6_ginap",
    "fill_weight", "water_loss", "voltage_1st", "bath_no", "circuit_no",
    "soaking_time_sec", "aging_days", "voltage_2nd", "electrolyte_temp", "charge_amount", "tank_temp",
]

_POOLED_COLUMNS = [
    "electrolyte_temp", "tank_temp", "soaking_time_sec", "aging_days",
    "voltage_1st", "voltage_2nd", "bath_no", "circuit_no", "line_no",
]
_CAPACITY_GROUP_COLUMNS = ["fill_weight"]

Y_DRIVERS = {"cell_weight_std": -0.308, "charge_ratio": 0.210}
Z_DRIVERS = {"electrolyte_temp": 0.613, "charge_ratio": 0.650, "tank_temp": 0.400, "retention_rate": 0.228}
Z_TARGET_R2 = 0.75
CCA_DRIVERS = {"cell_weight_std": -0.35, "charge_ratio": 0.25, "electrolyte_temp": 0.20}
CCA_TARGET_R2 = 0.55

Y_MEAN, Y_STD = 92.09, 0.97
Z_MEAN, Z_STD = 97.70, 2.59


def find_new_buyer_combos() -> list[tuple[float, str]]:
    """엑셀을 파싱해 기존 H/K/S·"All"을 제외한 (정격용량, 바이어) 조합을 찾는다."""
    with open(CHARGE_PROGRAM_XLSX, "rb") as f:
        rows = parse_charge_program_workbook(f.read())
    combos = {(r["rated_capacity"], r["buyer_code"]) for r in rows}
    new_combos = sorted(
        c for c in combos if c[1] != "All" and c[1] not in EXISTING_BUYERS
    )
    return new_combos


def _unit_weights(drivers: dict[str, float]) -> dict[str, float]:
    norm = float(np.sqrt(sum(v * v for v in drivers.values())))
    return {k: v / norm for k, v in drivers.items()}


def _pooled_stats() -> dict[str, tuple[float, float, float, float]]:
    df = pd.read_csv(SOURCE_PROCESS_CSV)
    stats: dict[str, tuple[float, float, float, float]] = {}
    for col in _POOLED_COLUMNS:
        series = df[col].dropna()
        mean, std = float(series.mean()), float(series.std())
        stats[col] = (mean, max(std, 1e-6), float(series.min()), float(series.max()))
    rated = df["model_name"].str.extract(r"[A-Za-z]+(\d+)_")[0].astype(float)
    charge_ratio = df["charge_amount"] / rated * 100
    stats["charge_ratio"] = (
        float(charge_ratio.mean()), float(charge_ratio.std()),
        float(charge_ratio.min()), float(charge_ratio.max()),
    )
    cellcols = [f"cell{i}_weight" for i in range(1, 7)]
    cws = df[cellcols].std(axis=1, ddof=0)
    stats["cell_weight_std"] = (
        float(cws.mean()), float(cws.std()), float(cws.min()), float(cws.max()),
    )
    return stats


def _capacity_group_stats(rated_capacity: float) -> dict[str, tuple[float, float, float, float]]:
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


def _make_lot_id(rng: np.random.Generator, rated_capacity: float, buyer: str, month_idx: int) -> str:
    cap_prefix = f"{int(rated_capacity):03d}"
    month_letter = "ABCDEFGHIJKL"[month_idx - 1]
    serial = rng.integers(0, 10**9)
    return f"{cap_prefix}C{YEAR % 100}{month_letter}{serial:09d}{buyer}1"


def _prod_date(rng: np.random.Generator, month_idx: int) -> dt.date:
    return dt.date(YEAR, month_idx, int(rng.integers(1, 28)))


def build_process_rows(combos: list[tuple[float, str]]) -> list[dict]:
    pooled = _pooled_stats()
    y_w = _unit_weights(Y_DRIVERS)

    rows: list[dict] = []
    for rated_capacity, buyer in combos:
        model_name = f"AGM{int(rated_capacity)}_{buyer}1"
        cap_stats = _capacity_group_stats(rated_capacity)
        rng = np.random.default_rng(RNG_SEED + int(rated_capacity) * 100 + ord(buyer[0]))
        n_months = 12
        per_month = ROWS_PER_MODEL // n_months
        for month_idx in range(1, n_months + 1):
            for _ in range(per_month):
                row: dict = {
                    "lot_id": _make_lot_id(rng, rated_capacity, buyer, month_idx),
                    "model_name": model_name,
                    "prod_date": _prod_date(rng, month_idx),
                }
                for col in _POOLED_COLUMNS:
                    row[col] = _sample(rng, pooled, col)
                charge_ratio = _sample(rng, pooled, "charge_ratio")
                cell_weight_std_target = _sample(rng, pooled, "cell_weight_std")
                cell_weight_mean = _sample(rng, cap_stats, "cell_weight_mean")
                fill_weight = _sample(rng, cap_stats, "fill_weight")

                z_cws = (cell_weight_std_target - pooled["cell_weight_std"][0]) / pooled["cell_weight_std"][1]
                z_cr = (charge_ratio - pooled["charge_ratio"][0]) / pooled["charge_ratio"][1]
                noise_std_y = float(np.sqrt(max(1.0 - Y_DRIVERS["cell_weight_std"] ** 2 - Y_DRIVERS["charge_ratio"] ** 2, 0.0)))
                raw_y = y_w["cell_weight_std"] * z_cws + y_w["charge_ratio"] * z_cr + noise_std_y * rng.normal()
                retention_rate = float(np.clip(Y_MEAN + Y_STD * raw_y, 88.0, 96.0))
                water_loss = fill_weight * (1 - retention_rate / 100)

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
                row["_buyer"] = buyer
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
    cca_w = _unit_weights(CCA_DRIVERS)
    z_et = (electrolyte_temp - pooled["electrolyte_temp"][0]) / pooled["electrolyte_temp"][1]
    noise_std = float(np.sqrt(max(1.0 - CCA_TARGET_R2, 0.0)))
    shared = cca_w["cell_weight_std"] * z_cws + cca_w["charge_ratio"] * z_cr + cca_w["electrolyte_temp"] * z_et
    shared *= float(np.sqrt(CCA_TARGET_R2))

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


def build_test_samples(process_rows: list[dict], combos: list[tuple[float, str]]) -> dict[str, list[dict]]:
    pooled = _pooled_stats()
    z_w = _unit_weights(Z_DRIVERS)
    noise_std_z = float(np.sqrt(max(1.0 - Z_TARGET_R2, 0.0)))

    by_model: dict[str, list[dict]] = {}
    for rated_capacity, buyer in combos:
        model_name = f"AGM{int(rated_capacity)}_{buyer}1"
        candidates = [r for r in process_rows if r["model_name"] == model_name]
        rng = np.random.default_rng(RNG_SEED + 2000 + int(rated_capacity) * 100 + ord(buyer[0]))
        chosen_idx = np.linspace(0, len(candidates) - 1, TEST_SAMPLES_PER_MODEL).astype(int)
        chosen = [candidates[i] for i in chosen_idx]

        samples = []
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
            samples.append(sample)
        by_model[model_name] = samples
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
    combos = find_new_buyer_combos()
    print(f"신규 (정격용량, 바이어) 조합 {len(combos)}건: {combos}")

    process_rows = build_process_rows(combos)
    process_df = pd.DataFrame(process_rows)[PROCESS_COLUMNS]
    assert len(process_df) == len(combos) * ROWS_PER_MODEL
    process_df.to_csv(OUT_PROCESS, index=False)

    by_model = build_test_samples(process_rows, combos)
    rated_capacity_of = {f"AGM{int(cap)}_{buyer}1": cap for cap, buyer in combos}
    _write_test_workbook(by_model, rated_capacity_of)

    from backend.analysis.cca_spec import judge_en_cca, judge_sae_cca

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
