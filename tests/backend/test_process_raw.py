"""backend/etl/process_raw.py 단위 테스트.

.docs/14_raw-data-업로드-지원-계획.md의 매핑표를 근거로, 실제 "D라인 전체 고율방전" 계열
raw data의 헤더 구조(2행 헤더 + 병합 셀)를 축소 재현한 워크북으로 검증한다.
"""
from __future__ import annotations

import io

import pandas as pd

from backend.etl.process_raw import parse_process_raw_workbook

# 컬럼 정의: (섹션, 필드, [LOT001, LOT002, LOT003, LOT004]용 값)
# LOT004는 Model Name이 공백 문자만 있는 셀(실제 raw data에서 발견된 사례, .docs/14)이라 건너뛰어야 함.
_COLUMNS = [
    ("No", None, [1, 2, 3, 4]),
    ("serial no", None, ["LOT001", "LOT002", "LOT003", "LOT004"]),
    ("Model Name", None, ["AGM90_H3", "AGM70_S1", "AGM90_H3", "              "]),
    ("Line No", None, [3, 1, 2, 1]),
    ("Stacker Weight", "Cell 1 Weight", [3.036, 2.9, 3.01, 3.0]),
    (None, "Cell 2 Weight", [3.039, 2.91, 3.02, 3.0]),
    (None, "Cell 3 Weight", [3.038, 2.92, 3.03, 3.0]),
    (None, "Cell 4 Weight", [3.044, 2.93, 3.04, 3.0]),
    (None, "Cell 5 Weight", [3.041, 2.94, 3.05, 3.0]),
    (None, "Cell 6 Weight", [3.033, 2.95, 3.06, 3.0]),
    ("Stacker Force", "Cell 1 Force", [43.9, 44.0, 44.1, 44.0]),
    (None, "Cell 2 Force", [45.4, 44.1, 44.2, 44.0]),
    (None, "Cell 3 Force", [45.1, 44.2, 44.3, 44.0]),
    (None, "Cell 4 Force", [44.5, 44.3, 44.4, 44.0]),
    (None, "Cell 5 Force", [45.2, 44.4, 44.5, 44.0]),
    (None, "Cell 6 Force", [45.8, 44.5, 44.6, 44.0]),
    (None, "Date/Time", ["2026-07-23 00:13:04", "2026-07-24 00:00:00", None, "2026-07-26 00:00:00"]),
    ("Filling", "Fill Weight", [5924, 4500, 5900, 5000]),
    (None, "Date/Time", [None, None, "2026-07-25 12:00:00", None]),
    ("Pre Test(Weight)", "Water Loss", [465, 400, 460, 400]),
    ("Pre Test(OCV)", "Voltage", [12.97, 12.90, 12.95, 12.9]),
    ("Final Test(HRD/OCV)", "OCV", [12.88, 12.80, 12.85, 12.8]),
    ("Charging(Bath)", "Bath No", [26, 5, 10, 5]),
    (None, "Circiut No", [25, 3, 7, 3]),
    (None, "Soaking Time", ["1분14초", "0분51초", "2분8초", "1분0초"]),
    ("Aging Pallet", "Aging Start", [20260725, 20260730180521, 20260726, 20260727]),
    (None, "Aging End", [20260801, 20260805, 20260802, 20260803]),
]


def _build_workbook_bytes() -> bytes:
    n_rows = len(_COLUMNS[0][2])
    section_row = [c[0] for c in _COLUMNS]
    field_row = [c[1] for c in _COLUMNS]
    blank_row = [None] * len(_COLUMNS)
    data_rows = [[c[2][i] for c in _COLUMNS] for i in range(n_rows)]

    matrix = [blank_row, blank_row, section_row, field_row, *data_rows]
    buffer = io.BytesIO()
    pd.DataFrame(matrix).to_excel(buffer, header=False, index=False, engine="openpyxl")
    buffer.seek(0)
    return buffer.read()


def test_parse_process_raw_workbook_maps_all_fields():
    rows = parse_process_raw_workbook(_build_workbook_bytes())
    assert len(rows) == 3
    lot1 = next(r for r in rows if r["lot_id"] == "LOT001")

    assert lot1["model_name"] == "AGM90_H3"
    assert lot1["line_no"] == "3"  # TEXT 컬럼, 정수처럼 표기(소수부 제거)
    assert lot1["cell1_weight"] == 3.036
    assert lot1["cell6_ginap"] == 45.8
    assert lot1["fill_weight"] == 5924
    assert lot1["water_loss"] == 465
    assert lot1["voltage_1st"] == 12.97
    assert lot1["voltage_2nd"] == 12.88
    assert lot1["bath_no"] == "26"
    assert lot1["circuit_no"] == "25"
    assert lot1["soaking_time_sec"] == 74.0  # "1분14초" = 60+14
    assert lot1["aging_days"] == 7  # 2026-08-01 - 2026-07-25
    assert lot1["prod_date"] == "2026-07-23"
    assert lot1["electrolyte_temp"] is None
    assert lot1["tank_temp"] is None
    assert lot1["charge_amount"] is None


def test_bath_no_uses_charging_bath_section():
    rows = parse_process_raw_workbook(_build_workbook_bytes())
    lot1 = next(r for r in rows if r["lot_id"] == "LOT001")
    assert lot1["bath_no"] == "26"


def test_aging_days_handles_full_timestamp_start():
    """Aging Start가 8자리(yyyymmdd)가 아니라 14자리(yyyymmddHHMMSS) 전체 타임스탬프로
    저장된 경우에도 앞 8자리만 날짜로 파싱해 올바른 aging_days를 계산해야 한다."""
    rows = parse_process_raw_workbook(_build_workbook_bytes())
    lot2 = next(r for r in rows if r["lot_id"] == "LOT002")
    assert lot2["soaking_time_sec"] == 51.0  # "0분51초"
    assert lot2["aging_days"] == 6  # 2026-08-05 - 2026-07-30(14자리 중 앞 8자리)


def test_prod_date_falls_back_when_stacker_date_missing():
    """Stacker Force 단계 Date/Time이 비어 있으면 다음 후보(Filling Date/Time)를 사용한다."""
    rows = parse_process_raw_workbook(_build_workbook_bytes())
    lot3 = next(r for r in rows if r["lot_id"] == "LOT003")
    assert lot3["prod_date"] == "2026-07-25"
    assert lot3["soaking_time_sec"] == 128.0  # "2분8초" = 120+8
    assert lot3["aging_days"] == 7  # 2026-08-02 - 2026-07-26


def test_whitespace_only_model_name_is_skipped_not_crashed():
    """Model Name 셀이 공백 문자만 있는 경우(NaN이 아니라 " " 등) — 실제 raw data에서 발견된
    사례. pd.isna()로는 걸러지지 않으므로 strip() 후 빈 문자열인지 반드시 확인해야 한다.
    이 로트만 건너뛰고 나머지 로트는 정상 파싱돼야 한다(파일 전체가 실패하면 안 됨)."""
    rows = parse_process_raw_workbook(_build_workbook_bytes())
    lot_ids = {r["lot_id"] for r in rows}
    assert "LOT004" not in lot_ids
    assert lot_ids == {"LOT001", "LOT002", "LOT003"}
