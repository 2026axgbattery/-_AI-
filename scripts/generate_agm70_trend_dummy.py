"""AGM70_S1 단일 형명 12개월 추이 더미 데이터 생성 스크립트.

`history/17_agm70-12개월-추이-더미데이터-생성-계획.md` 참조.
`AGM 시험현황_raw data.xlsx`의 실측값(20개 샘플 초기상태, 그중 12개 샘플 20HR 용량 시험)을
근거로 공정 데이터 1,200행(월 100건×12개월)과 시험 데이터 24행(월 2건×12개월)을 생성한다.
저장소 루트에서 실행: python scripts/generate_agm70_trend_dummy.py
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import openpyxl
import pandas as pd

RAW_PATH = "AGM 시험현황_raw data.xlsx"
MODEL_NAME = "AGM70_S1"
RATED_CAPACITY = 70.0
YEAR = 2026
RNG_SEED = 42

PROCESS_COLUMNS = [
    "lot_id", "model_name", "line_no", "prod_date",
    "cell1_weight", "cell2_weight", "cell3_weight", "cell4_weight", "cell5_weight", "cell6_weight",
    "cell1_ginap", "cell2_ginap", "cell3_ginap", "cell4_ginap", "cell5_ginap", "cell6_ginap",
    "fill_weight", "water_loss", "voltage_1st", "bath_no", "circuit_no",
    "soaking_time_sec", "aging_days", "voltage_2nd", "electrolyte_temp", "charge_amount", "tank_temp",
]
TEST_COLUMNS = [
    "lot_id", "initial_voltage", "initial_resistance", "initial_weight", "initial_cca",
    "rated_capacity", "discharge_amount", "charge_amount_20h", "capacity_rate", "charge_rate",
    "mt_voltage", "mt_current",
]

# 기존 process_data.csv의 AGM70_* 18행에서 산출한 합성용 분포 파라미터 (mean, std, min, max)
SYNTH_PARAMS = {
    "cell1_weight": (3.033, 0.062, 2.85, 3.20),
    "cell2_weight": (3.047, 0.096, 2.80, 3.25),
    "cell3_weight": (3.027, 0.089, 2.80, 3.25),
    "cell4_weight": (3.062, 0.088, 2.85, 3.25),
    "cell5_weight": (3.049, 0.099, 2.80, 3.28),
    "cell6_weight": (3.057, 0.077, 2.85, 3.22),
    "cell1_ginap": (44.643, 1.073, 42.0, 47.5),
    "cell2_ginap": (45.061, 0.941, 42.5, 47.5),
    "cell3_ginap": (44.924, 1.083, 42.5, 47.5),
    "cell4_ginap": (45.377, 0.616, 43.5, 47.0),
    "cell5_ginap": (44.903, 1.280, 42.0, 47.5),
    "cell6_ginap": (45.051, 0.734, 43.0, 46.5),
    "bath_no": (20.8, 11.9, 1, 40),
    "circuit_no": (20.3, 10.8, 1, 40),
    "soaking_time_sec": (72.8, 5.9, 60, 90),
    "aging_days": (7.0, 1.24, 5, 9),
    "charge_amount": (80.4, 2.1, 75.0, 86.0),
    "electrolyte_temp": (34.6, 2.5, 29.0, 41.0),
    "tank_temp": (37.0, 2.3, 33.0, 43.0),
    "line_no": (2.1, 0.68, 1, 3),
}


def extract_raw_samples() -> tuple[list[dict], list[dict]]:
    wb = openpyxl.load_workbook(RAW_PATH, data_only=True)
    ws = wb[wb.sheetnames[0]]

    def row_vals(r: int) -> list:
        return [ws.cell(r, c).value for c in range(3, 23)]  # C..V = 샘플 1~20

    lot_ids = row_vals(4)
    voltage = row_vals(5)
    resistance = row_vals(6)
    weight = row_vals(7)
    fill_weight = row_vals(8)
    water_loss = row_vals(9)
    ocv2 = row_vals(11)
    finish_date = row_vals(12)
    mt_v = row_vals(14)
    mt_a = row_vals(15)

    discharge = row_vals(23)
    charge20h = row_vals(24)
    capacity_rate = row_vals(25)
    charge_rate = row_vals(26)

    initial_samples = []
    test_samples = []
    for i in range(20):
        if not lot_ids[i]:
            continue
        finish_dt = finish_date[i]
        sample = {
            "lot_id": str(lot_ids[i]).strip(),
            "voltage_1st": float(voltage[i]),
            "resistance": float(resistance[i]),
            "weight": float(weight[i]),
            "fill_weight": float(fill_weight[i]),
            "water_loss": float(water_loss[i]),
            "voltage_2nd": float(ocv2[i]),
            "finish_date": finish_dt.date() if isinstance(finish_dt, dt.datetime) else None,
            "mt_voltage": float(mt_v[i]),
            "mt_current": float(mt_a[i]),
        }
        initial_samples.append(sample)

        has_test = isinstance(capacity_rate[i], (int, float)) and capacity_rate[i] not in (0, None)
        if has_test:
            test_samples.append({
                "lot_id": sample["lot_id"],
                "initial_voltage": sample["voltage_1st"],
                "initial_resistance": sample["resistance"],
                "initial_weight": sample["weight"],
                "initial_cca": sample["mt_current"],
                "rated_capacity": RATED_CAPACITY,
                "discharge_amount": float(discharge[i]),
                "charge_amount_20h": float(charge20h[i]),
                "capacity_rate": float(capacity_rate[i]),
                "charge_rate": float(charge_rate[i]),
                "mt_voltage": sample["mt_voltage"],
                "mt_current": sample["mt_current"],
            })

    return initial_samples, test_samples


def month_date(month_idx: int, day: int) -> dt.date:
    day = min(day, 28)
    return dt.date(YEAR, month_idx, day)


def make_lot_id(rng: np.random.Generator, month_idx: int, seq: int) -> str:
    month_letter = "ABCDEFGHIJKL"[month_idx - 1]
    serial = rng.integers(0, 10**9)
    suffix = rng.choice(["H1", "H3", "K1", "K3", "S1", "S3"])
    return f"070C{YEAR % 100}{month_letter}{serial:09d}{suffix}"


def synth_value(rng: np.random.Generator, col: str) -> float:
    mean, std, lo, hi = SYNTH_PARAMS[col]
    val = rng.normal(mean, std)
    return float(np.clip(val, lo, hi))


def build_process_rows(initial_samples: list[dict], test_lot_ids: set[str]) -> list[dict]:
    rng = np.random.default_rng(RNG_SEED)
    n_samples = len(initial_samples)

    # 실측 20개 lot_id를 12개월에 분산 배치: 시험 실측이 있는 12개는 1개월에 1개씩,
    # 나머지 8개(시험 없음)는 앞 8개월에 1개씩 추가 배치한다.
    test_anchor_samples = [s for s in initial_samples if s["lot_id"] in test_lot_ids]
    plain_anchor_samples = [s for s in initial_samples if s["lot_id"] not in test_lot_ids]
    month_of_lot: dict[str, int] = {}
    for i, s in enumerate(test_anchor_samples):
        month_of_lot[s["lot_id"]] = i + 1  # 1~12
    for i, s in enumerate(plain_anchor_samples):
        month_of_lot[s["lot_id"]] = (i % 8) + 1  # 1~8

    rows: list[dict] = []
    real_preserved = 0
    real_bootstrap = 0
    pure_synth = 0

    for month_idx in range(1, 13):
        preserved_this_month = [s for s in initial_samples if month_of_lot[s["lot_id"]] == month_idx]
        month_rows: list[dict] = []

        for s in preserved_this_month:
            row = {
                "lot_id": s["lot_id"],
                "model_name": MODEL_NAME,
                "prod_date": month_date(month_idx, rng.integers(1, 28)),
                "fill_weight": s["fill_weight"],
                "water_loss": s["water_loss"],
                "voltage_1st": s["voltage_1st"],
                "voltage_2nd": s["voltage_2nd"],
            }
            for col in SYNTH_PARAMS:
                row[col] = synth_value(rng, col)
            month_rows.append(row)
            real_preserved += 1

        n_real_bootstrap = 50 - len(preserved_this_month)
        for _ in range(max(n_real_bootstrap, 0)):
            anchor = initial_samples[rng.integers(0, n_samples)]
            row = {
                "lot_id": make_lot_id(rng, month_idx, len(month_rows)),
                "model_name": MODEL_NAME,
                "prod_date": month_date(month_idx, rng.integers(1, 28)),
                "fill_weight": anchor["fill_weight"],
                "water_loss": anchor["water_loss"],
                "voltage_1st": anchor["voltage_1st"],
                "voltage_2nd": anchor["voltage_2nd"],
            }
            for col in SYNTH_PARAMS:
                row[col] = synth_value(rng, col)
            month_rows.append(row)
            real_bootstrap += 1

        n_pure_synth = 100 - len(month_rows)
        for _ in range(n_pure_synth):
            fill = float(np.clip(rng.normal(5850, 180), 5400, 6300))
            water_loss_ratio = rng.normal(0.078, 0.012)
            row = {
                "lot_id": make_lot_id(rng, month_idx, len(month_rows)),
                "model_name": MODEL_NAME,
                "prod_date": month_date(month_idx, rng.integers(1, 28)),
                "fill_weight": round(fill, 1),
                "water_loss": round(fill * water_loss_ratio, 1),
                "voltage_1st": round(float(np.clip(rng.normal(12.87, 0.09), 12.5, 13.1)), 2),
                "voltage_2nd": round(float(np.clip(rng.normal(12.80, 0.10), 12.4, 13.1)), 2),
            }
            for col in SYNTH_PARAMS:
                row[col] = synth_value(rng, col)
            month_rows.append(row)
            pure_synth += 1

        rows.extend(month_rows)

    for row in rows:
        row["cell1_weight"] = round(row["cell1_weight"], 3)
        row["cell2_weight"] = round(row["cell2_weight"], 3)
        row["cell3_weight"] = round(row["cell3_weight"], 3)
        row["cell4_weight"] = round(row["cell4_weight"], 3)
        row["cell5_weight"] = round(row["cell5_weight"], 3)
        row["cell6_weight"] = round(row["cell6_weight"], 3)
        row["cell1_ginap"] = round(row["cell1_ginap"], 2)
        row["cell2_ginap"] = round(row["cell2_ginap"], 2)
        row["cell3_ginap"] = round(row["cell3_ginap"], 2)
        row["cell4_ginap"] = round(row["cell4_ginap"], 2)
        row["cell5_ginap"] = round(row["cell5_ginap"], 2)
        row["cell6_ginap"] = round(row["cell6_ginap"], 2)
        row["line_no"] = int(round(row["line_no"]))
        row["bath_no"] = int(round(row["bath_no"]))
        row["circuit_no"] = int(round(row["circuit_no"]))
        row["soaking_time_sec"] = int(round(row["soaking_time_sec"]))
        row["aging_days"] = int(round(row["aging_days"]))
        row["charge_amount"] = round(row["charge_amount"], 1)
        row["electrolyte_temp"] = round(row["electrolyte_temp"], 1)
        row["tank_temp"] = round(row["tank_temp"], 1)
        row["fill_weight"] = round(row["fill_weight"], 1)
        row["water_loss"] = round(row["water_loss"], 1)
        row["voltage_1st"] = round(row["voltage_1st"], 2)
        row["voltage_2nd"] = round(row["voltage_2nd"], 2)

    print(f"[process] 실측 lot_id 보존행={real_preserved}, 실측값 부트스트랩행={real_bootstrap}, 순수합성행={pure_synth}, 총={len(rows)}")
    return rows


def build_test_rows(
    test_samples: list[dict],
    process_test_lot_month: dict[str, int],
    month_candidate_lots: dict[int, list[str]],
) -> list[dict]:
    rng = np.random.default_rng(RNG_SEED + 1)

    vals = {
        "discharge_amount": [s["discharge_amount"] for s in test_samples],
        "charge_amount_20h": [s["charge_amount_20h"] for s in test_samples],
        "capacity_rate": [s["capacity_rate"] for s in test_samples],
        "charge_rate": [s["charge_rate"] for s in test_samples],
        "initial_voltage": [s["initial_voltage"] for s in test_samples],
        "initial_resistance": [s["initial_resistance"] for s in test_samples],
        "initial_weight": [s["initial_weight"] for s in test_samples],
        "initial_cca": [s["initial_cca"] for s in test_samples],
        "mt_voltage": [s["mt_voltage"] for s in test_samples],
        "mt_current": [s["mt_current"] for s in test_samples],
    }
    stats = {k: (float(np.mean(v)), float(np.std(v))) for k, v in vals.items()}

    rows: list[dict] = []
    for month_idx in range(1, 13):
        real = next(s for s in test_samples if process_test_lot_month[s["lot_id"]] == month_idx)
        rows.append(dict(real))

        # 더미 시험행은 같은 달의 공정 데이터(실측 lot_id 제외) 중 하나와 매칭되도록 lot_id를 재사용한다.
        candidates = [lot for lot in month_candidate_lots[month_idx] if lot != real["lot_id"]]
        dummy_lot_id = candidates[rng.integers(0, len(candidates))]
        dummy = {
            "lot_id": dummy_lot_id,
            "rated_capacity": RATED_CAPACITY,
        }
        for k, (mean, std) in stats.items():
            dummy[k] = round(float(rng.normal(mean, max(std, 1e-6))), 3)
        rows.append(dummy)

    for row in rows:
        for k in ("initial_voltage", "mt_voltage"):
            row[k] = round(row[k], 2)
        for k in ("initial_resistance",):
            row[k] = round(row[k], 2)
        for k in ("initial_weight",):
            row[k] = round(row[k], 1)
        for k in ("initial_cca", "mt_current"):
            row[k] = round(row[k], 1)
        for k in ("discharge_amount", "charge_amount_20h"):
            row[k] = round(row[k], 1)
        for k in ("capacity_rate", "charge_rate"):
            row[k] = round(row[k], 1)

    print(f"[test] 실측행=12, 합성행=12, 총={len(rows)}")
    return rows


def main() -> None:
    initial_samples, test_samples = extract_raw_samples()
    test_lot_ids = {s["lot_id"] for s in test_samples}

    process_rows = build_process_rows(initial_samples, test_lot_ids)

    process_test_lot_month = {}
    month_candidate_lots: dict[int, list[str]] = {m: [] for m in range(1, 13)}
    for row in process_rows:
        month_candidate_lots[row["prod_date"].month].append(row["lot_id"])
        if row["lot_id"] in test_lot_ids:
            process_test_lot_month[row["lot_id"]] = row["prod_date"].month

    test_rows = build_test_rows(test_samples, process_test_lot_month, month_candidate_lots)

    process_df = pd.DataFrame(process_rows)[PROCESS_COLUMNS]
    test_df = pd.DataFrame(test_rows)[TEST_COLUMNS]

    assert process_df["lot_id"].is_unique, "process lot_id 중복 발생"
    assert test_df["lot_id"].is_unique, "test lot_id 중복 발생"
    assert len(process_df) == 1200
    assert len(test_df) == 24
    assert set(test_lot_ids).issubset(set(process_df["lot_id"]))

    process_df.to_csv("agm70_trend_process_data.csv", index=False)
    test_df.to_csv("agm70_trend_test_data.csv", index=False)
    print("생성 완료: agm70_trend_process_data.csv, agm70_trend_test_data.csv")


if __name__ == "__main__":
    main()
