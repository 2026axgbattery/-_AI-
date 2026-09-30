"""충전 프로그램에 명시된 바이어 코드로만 국한한 신규 더미 데이터 생성 스크립트(`.docs/36` 참조).

**2026-09-30 수정**: 처음에는 이 컴퓨터에 실제 충전 프로그램 원본("★ 260428 AGM CF 충전 프로그램
3.xlsx")이 없어 2026-09-26 세션 기록(CLAUDE.md)에 의존해 (정격용량, 바이어) 조합을 추정했으나,
사용자가 원본 파일을 저장소 루트에 넣어준 뒤 실제로 파싱해보니 그 기록이 부정확했다(예: "K"
바이어는 원본 어디에도 없고, 50Ah는 H/Y 2종뿐 — 아래 `BUYERS_BY_CAPACITY`는 원본을 직접 파싱해
확정한 32개 조합으로 교체함). 이제부터는 이 파일이 있으면 항상 직접 파싱해 재확인할 것 — 과거
세션 기록을 그대로 믿지 말 것.

- (정격용량, 바이어) 조합은 `backend/etl/charge_program.py`로 원본 파일을 직접 파싱해 확정한
  32개(`BUYERS_BY_CAPACITY`). 90/105Ah는 원본에 "All"(바이어 무관 공통) 프로그램 하나뿐이라
  특정 바이어로 제한할 근거가 없어 기존 로트와 동일하게 H/K/S를 그대로 쓴다(`lookup_charge_program_total_ah`가
  정확히 일치하는 바이어가 없으면 "All"로 폴백하므로 어떤 바이어를 골라도 매칭된다).
- 공정 조건(전해액온도·수조온도 등) 풀 분포는 실측 재계산이 아니라 도메인상 타당한 추정값
  (`_POOLED_STATS`)을 쓴다. Y/Z/CCA 드라이버 방향·크기는 `docs/correlation-reliability-review.md`
  실측 검증값을 그대로 재사용(`scripts/generate_agm60_70_dummy.py`와 동일 로직)하므로 회귀가
  학습할 상대적 신호 구조는 보존된다 — 절대 스케일의 실측 정합성만 낮아진 것.
- `charge_amount`는 기존 더미 스크립트들과 동일하게 `charge_ratio`(정격용량 대비 ~100~125%)
  기반 소규모 스케일을 그대로 쓴다(원본 충전 프로그램의 Total 충전량[Ah]과 스케일이 다르다는
  이슈는 CLAUDE.md에 이미 "사용자 미결정"으로 기록된 별개 이슈라 여기서 임의로 재정의하지
  않음) — 그래서 `charge_program_deviation_pct`는 큰 음수(대략 -80% 안팎)로 일관되게 나오는
  것이 기존 스크립트와 동일하게 **의도된 정상 동작**이다. 회귀가 필요로 하는 건 이 컬럼이
  NULL이 아니라 실제 수치로 채워지는 것이지, 값이 0 근처인 것이 아니다.

**산출물 포맷이 기존 스크립트와 다른 점**: 시험 데이터는 요청대로 `.xlsx`(raw 신뢰성 시험
워크북 구조, `backend/etl/test_raw.py`와 1:1 대응 — 그대로 업로드하면 완전히 동작)로 저장하지만,
공정 데이터는 `.xlsx`가 아니라 `.csv`로 저장한다. `backend/etl/process_raw.py`는 raw 엑셀 경로에서
`electrolyte_temp`/`charge_amount`/`tank_temp` 3개 필드를 코드 레벨에서 항상 `None`으로 고정한다
(실제 현장 raw data에도 이 필드가 없어서 그런 것 — 워크북을 아무리 잘 만들어도 우회 불가). 공정
데이터를 raw 엑셀로 만들면 업로드는 성공하지만 1단 회귀에 필수인 charge_ratio·전해액/수조온도가
전부 비어 회귀 자체가 안 돈다. 기존 두 더미 스크립트가 공정 데이터만 CSV로 저장해 온 것도 같은
이유(CSV도 업로드 API가 그대로 받는 포맷이라 "업로드 즉시 반영 가능" 목표는 동일하게 달성됨).

시험 데이터 300건은 전량 20시간율(discharge_amount 등 Z 계열)을 채우고, 150건은 EN CCA
체크포인트만, 나머지 150건은 SAE CCA 체크포인트만 채운다(같은 샘플에 둘 다 채우지 않음 —
실측도 샘플마다 어떤 신뢰성 서브시험을 탔는지 갈리는 것과 동일한 설계, EN/SAE 배정은
32개 조합에 걸쳐 무작위로 섞되 정확히 150/150 비율을 맞춘다).

저장소 루트에서 실행: python scripts/generate_charge_restricted_dummy.py
산출물: "충전바이어_더미_process.csv", "충전바이어_더미_test.xlsx" (둘 다 저장소 루트)
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import openpyxl
import pandas as pd

OUT_PROCESS = "충전바이어_더미_process.csv"
OUT_TEST = "충전바이어_더미_test.xlsx"
RNG_SEED = 2026
YEAR = 2026

# 2026-09-30, 원본 "★ 260428 AGM CF 충전 프로그램 3.xlsx"을 backend/etl/charge_program.py로
# 직접 파싱해 확정(재확인 방법: scripts/generate_charge_restricted_dummy.py 상단 docstring 참조).
# 50Ah는 원본에 H/Y 2종뿐이고("K" 없음), 60/70/80Ah도 실제로는 K가 전혀 없다 — 과거 세션 기록을
# 그대로 믿었던 게 오류였음. 90/105Ah는 "All" 하나뿐이라 임의의 바이어를 써도 폴백 매칭된다.
BUYERS_BY_CAPACITY: dict[float, list[str]] = {
    50.0: ["H", "Y"],
    60.0: ["B", "C", "D", "G", "H", "S", "V", "Y", "Z"],
    70.0: ["B", "C", "D", "G", "H", "S", "Y", "Z"],
    80.0: ["B", "C", "D", "H", "S", "Y", "Z"],
    90.0: ["H", "K", "S"],
    105.0: ["H", "K", "S"],
}
COMBOS: list[tuple[float, str]] = [
    (cap, buyer) for cap, buyers in BUYERS_BY_CAPACITY.items() for buyer in buyers
]  # 32개 조합

ROWS_PER_COMBO = 156  # 32 x 156 = 4,992건("약 5천개")
N_MONTHS = 12
PER_MONTH = ROWS_PER_COMBO // N_MONTHS  # 13

TOTAL_TEST_SAMPLES = 300
BASE_TEST_PER_COMBO = TOTAL_TEST_SAMPLES // len(COMBOS)  # 9
EXTRA_COMBOS = TOTAL_TEST_SAMPLES - BASE_TEST_PER_COMBO * len(COMBOS)  # 12개 조합만 +1(=10건)

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

# 실측 검증된 상관관계(docs/correlation-reliability-review.md) — 기존 더미 스크립트와 동일.
Y_DRIVERS = {"cell_weight_std": -0.308, "charge_ratio": 0.210}
Z_DRIVERS = {"electrolyte_temp": 0.613, "charge_ratio": 0.650, "tank_temp": 0.400, "retention_rate": 0.228}
Z_TARGET_R2 = 0.75
CCA_DRIVERS = {"cell_weight_std": -0.35, "charge_ratio": 0.25, "electrolyte_temp": 0.20}
CCA_TARGET_R2 = 0.55

Y_MEAN, Y_STD = 92.09, 0.97
Z_MEAN, Z_STD = 97.70, 2.59

# 실측 process_data.csv가 이 컴퓨터에 없어 도메인상 타당한 추정값을 쓴다(mean, std, min, max).
# Y/Z/CCA 드라이버는 이 값들의 z-score(정규화 편차)만 사용하므로, 회귀가 학습할 신호 구조
# 자체는 절대 스케일과 무관하게 보존된다.
_POOLED_STATS: dict[str, tuple[float, float, float, float]] = {
    "electrolyte_temp": (25.0, 3.0, 15.0, 35.0),
    "tank_temp": (25.0, 3.0, 15.0, 35.0),
    "soaking_time_sec": (1800.0, 300.0, 600.0, 3000.0),
    "aging_days": (3.0, 1.0, 1.0, 7.0),
    "voltage_1st": (2.05, 0.03, 1.95, 2.15),
    "voltage_2nd": (2.10, 0.03, 2.00, 2.20),
    "bath_no": (5.0, 2.0, 1.0, 10.0),
    "circuit_no": (10.0, 4.0, 1.0, 20.0),
    "line_no": (3.0, 1.0, 1.0, 5.0),
    "charge_ratio": (112.0, 6.0, 100.0, 125.0),
    "cell_weight_std": (3.0, 1.0, 0.5, 8.0),
}


def _capacity_group_stats(rated_capacity: float) -> dict[str, tuple[float, float, float, float]]:
    """정격용량에 physically 비례하는 컬럼(fill_weight, cell_weight_mean) — 용량에 선형 비례하는
    추정 스케일(실측 없음, 상대적 크기 순서만 물리적으로 타당하면 됨)."""
    fill_mean = rated_capacity * 9.0
    cell_mean = rated_capacity * 3.0
    return {
        "fill_weight": (fill_mean, fill_mean * 0.02, fill_mean * 0.9, fill_mean * 1.1),
        "cell_weight_mean": (cell_mean, cell_mean * 0.02, cell_mean * 0.9, cell_mean * 1.1),
    }


def _unit_weights(drivers: dict[str, float]) -> dict[str, float]:
    norm = float(np.sqrt(sum(v * v for v in drivers.values())))
    return {k: v / norm for k, v in drivers.items()}


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


def build_process_rows() -> list[dict]:
    y_w = _unit_weights(Y_DRIVERS)
    rows: list[dict] = []

    for rated_capacity, buyer in COMBOS:
        model_name = f"AGM{int(rated_capacity)}_{buyer}1"
        cap_stats = _capacity_group_stats(rated_capacity)
        rng = np.random.default_rng(RNG_SEED + int(rated_capacity) * 100 + ord(buyer[0]))
        for month_idx in range(1, N_MONTHS + 1):
            for _ in range(PER_MONTH):
                row: dict = {
                    "lot_id": _make_lot_id(rng, rated_capacity, buyer, month_idx),
                    "model_name": model_name,
                    "prod_date": _prod_date(rng, month_idx),
                }
                for col in _POOLED_COLUMNS:
                    row[col] = _sample(rng, _POOLED_STATS, col)
                charge_ratio = _sample(rng, _POOLED_STATS, "charge_ratio")
                cell_weight_std_target = _sample(rng, _POOLED_STATS, "cell_weight_std")
                cell_weight_mean = _sample(rng, cap_stats, "cell_weight_mean")
                fill_weight = _sample(rng, cap_stats, "fill_weight")

                z_cws = (cell_weight_std_target - _POOLED_STATS["cell_weight_std"][0]) / _POOLED_STATS["cell_weight_std"][1]
                z_cr = (charge_ratio - _POOLED_STATS["charge_ratio"][0]) / _POOLED_STATS["charge_ratio"][1]
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
    assert len(rows) == len(COMBOS) * ROWS_PER_COMBO
    return rows


def _cca_values(rng: np.random.Generator, rated_capacity: float, z_cws: float, z_cr: float, electrolyte_temp: float) -> dict:
    """CCA 체크포인트(전압·지속시간)를 공정 인자 기반 수식+노이즈로 생성(기존 스크립트와 동일 로직)."""
    cca_w = _unit_weights(CCA_DRIVERS)
    z_et = (electrolyte_temp - _POOLED_STATS["electrolyte_temp"][0]) / _POOLED_STATS["electrolyte_temp"][1]
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


def _test_quota() -> dict[tuple[float, str], int]:
    quota = dict.fromkeys(COMBOS, BASE_TEST_PER_COMBO)
    for combo in COMBOS[:EXTRA_COMBOS]:
        quota[combo] += 1
    assert sum(quota.values()) == TOTAL_TEST_SAMPLES
    return quota


def build_test_samples(process_rows: list[dict]) -> tuple[dict[str, list[dict]], dict[str, float]]:
    """32개 조합에 9~10건씩(총 300건) 분산 배정하고, EN/SAE CCA를 정확히 150/150으로 무작위 배정."""
    z_w = _unit_weights(Z_DRIVERS)
    noise_std_z = float(np.sqrt(max(1.0 - Z_TARGET_R2, 0.0)))
    quota = _test_quota()

    type_rng = np.random.default_rng(RNG_SEED + 9999)
    cca_types = ["EN"] * (TOTAL_TEST_SAMPLES // 2) + ["SAE"] * (TOTAL_TEST_SAMPLES // 2)
    type_rng.shuffle(cca_types)
    type_iter = iter(cca_types)

    by_model: dict[str, list[dict]] = {}
    rated_capacity_of: dict[str, float] = {}

    for rated_capacity, buyer in COMBOS:
        model_name = f"AGM{int(rated_capacity)}_{buyer}1"
        rated_capacity_of[model_name] = rated_capacity
        candidates = [r for r in process_rows if r["model_name"] == model_name]
        n = quota[(rated_capacity, buyer)]
        rng = np.random.default_rng(RNG_SEED + 5000 + int(rated_capacity) * 100 + ord(buyer[0]))
        chosen_idx = np.linspace(0, len(candidates) - 1, n).astype(int)
        chosen = [candidates[i] for i in chosen_idx]

        samples = []
        for proc_row in chosen:
            z_et = (proc_row["electrolyte_temp"] - _POOLED_STATS["electrolyte_temp"][0]) / _POOLED_STATS["electrolyte_temp"][1]
            z_tt = (proc_row["tank_temp"] - _POOLED_STATS["tank_temp"][0]) / _POOLED_STATS["tank_temp"][1]
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
            cca_vals = _cca_values(rng, rated_capacity, proc_row["_z_cws"], z_cr, proc_row["electrolyte_temp"])
            cca_type = next(type_iter)
            sample["cca_type"] = cca_type
            if cca_type == "EN":
                sample["en_cca_10s_voltage"] = cca_vals["en_cca_10s_voltage"]
                sample["en_cca_6v_hold_sec"] = cca_vals["en_cca_6v_hold_sec"]
                sample["en_cca"] = cca_vals["en_cca"]
                sample["sae_cca_7v2_hold_sec"] = None
                sample["sae_cca"] = None
            else:
                sample["sae_cca_7v2_hold_sec"] = cca_vals["sae_cca_7v2_hold_sec"]
                sample["sae_cca"] = cca_vals["sae_cca"]
                sample["en_cca_10s_voltage"] = None
                sample["en_cca_6v_hold_sec"] = None
                sample["en_cca"] = None
            samples.append(sample)
        by_model[model_name] = samples

    remaining = list(type_iter)
    assert not remaining, f"EN/SAE 배정에서 남은 타입이 있습니다: {remaining}"
    return by_model, rated_capacity_of


def _fmt_hold(value: float | None) -> str | None:
    return None if value is None else f"{value:g}초"


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
        row(None, "7.2V 지속시간", [_fmt_hold(s["sae_cca_7v2_hold_sec"]) for s in samples])
        row(None, "방전량", [s["sae_cca"] for s in samples])
        row("EN CCA 18℃", "10초 전압", [s["en_cca_10s_voltage"] for s in samples])
        row(None, "6.0V 지속시간", [_fmt_hold(s["en_cca_6v_hold_sec"]) for s in samples])
        row(None, "방전량", [s["en_cca"] for s in samples])

    wb.save(OUT_TEST)


def main() -> None:
    process_rows = build_process_rows()
    process_df = pd.DataFrame(process_rows)[PROCESS_COLUMNS]
    process_df.to_csv(OUT_PROCESS, index=False)

    by_model, rated_capacity_of = build_test_samples(process_rows)
    _write_test_workbook(by_model, rated_capacity_of)

    from backend.analysis.cca_spec import judge_en_cca, judge_sae_cca  # noqa: E402

    total_en_evaluated = total_sae_evaluated = 0
    for model_name, samples in by_model.items():
        en_samples = [s for s in samples if s["cca_type"] == "EN"]
        sae_samples = [s for s in samples if s["cca_type"] == "SAE"]
        total_en_evaluated += len(en_samples)
        total_sae_evaluated += len(sae_samples)
        en_pass = sum(
            1 for s in en_samples if judge_en_cca(s["en_cca_10s_voltage"], s["en_cca_6v_hold_sec"])["result"] == "pass"
        )
        sae_pass = sum(
            1 for s in sae_samples if judge_sae_cca(s["sae_cca_7v2_hold_sec"])["result"] == "pass"
        )
        print(
            f"[{model_name}] 시험 샘플={len(samples)}건(EN {len(en_samples)}/SAE {len(sae_samples)}), "
            f"EN 합격={en_pass}/{len(en_samples)}, SAE 합격={sae_pass}/{len(sae_samples)}"
        )

    combo_count = len(COMBOS)
    total_test = sum(len(s) for s in by_model.values())
    print(
        f"\n생성 완료: {OUT_PROCESS}({len(process_df)}행, {combo_count}개 조합), "
        f"{OUT_TEST}({total_test}건, EN {total_en_evaluated}/SAE {total_sae_evaluated})"
    )


if __name__ == "__main__":
    main()
