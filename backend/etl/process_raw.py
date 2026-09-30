"""공정 라인 실적 raw data(.xls, 예: "D라인 전체 고율방전" 계열 파일) 파서.

원본은 2행 헤더(1행=섹션명, 2행=세부 필드명, 병합 셀이라 섹션명은 해당 블록의 첫 컬럼에만
있고 나머지는 빈칸)를 가진 로트별 1행 구조다. 매핑 근거·컬럼 대응표는
`.docs/14_raw-data-업로드-지원-계획.md` 참조.
"""
from __future__ import annotations

import io
import re
from datetime import date

import pandas as pd

_SOAKING_RE = re.compile(r"(\d+)\D+(\d+)\D+")

# prod_date 후보(섹션, "Date/Time") — 공정 순서대로. 앞쪽이 비어 있으면 다음 후보로 넘어간다.
# 마지막 "Final Test(HRD/OCV)"는 전 행 100% 채워져 있어 최종 안전망 역할을 한다(계획서 확인).
_PROD_DATE_CANDIDATES = [
    "Stacker Force",
    "Cell Insert",
    "High Voolt Test",
    "Short-Missport",
    "Term Welding",
    "Air Tight",
    "Filling",
    "Pre Test(Weight)",
    "Pre Test(OCV)",
    "Aging Pallet",
    "Final Test(HRD/OCV)",
]


def _blank(value) -> bool:
    try:
        result = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return bool(result)


def _native(value):
    """pandas/numpy 스칼라를 sqlite3가 바인딩할 수 있는 순수 파이썬 값으로 변환한다."""
    if _blank(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _int_like_text(value) -> str | None:
    """line_no/bath_no/circuit_no(TEXT 컬럼, 그룹 변수)용 변환.

    pandas가 결측 섞인 정수 컬럼을 float64로 읽어 26.0처럼 저장하면 TEXT 컬럼에
    "26.0"으로 들어가 CSV 경로("26")와 표기가 달라진다 — 정수값이면 소수부를 제거한다.
    """
    native = _native(value)
    if native is None:
        return None
    if isinstance(native, float) and native.is_integer():
        return str(int(native))
    return str(native)


def _build_header_map(section_row: list, field_row: list) -> dict[tuple[str | None, str | None], int]:
    header_map: dict[tuple[str | None, str | None], int] = {}
    current_section: str | None = None
    for i, (sec, fld) in enumerate(zip(section_row, field_row)):
        if not _blank(sec):
            current_section = str(sec).strip()
        key_field = None if _blank(fld) else str(fld).strip()
        key = (current_section, key_field)
        header_map.setdefault(key, i)
    return header_map


def _parse_soaking_seconds(value) -> float | None:
    if _blank(value):
        return None
    match = _SOAKING_RE.match(str(value).strip())
    if not match:
        return None
    minutes, seconds = match.groups()
    return float(int(minutes) * 60 + int(seconds))


def _parse_yyyymmdd(value) -> date | None:
    if _blank(value):
        return None
    digits = str(int(value))[:8]
    try:
        return date(int(digits[0:4]), int(digits[4:6]), int(digits[6:8]))
    except ValueError:
        return None


def parse_process_raw_workbook(file_bytes: bytes) -> list[dict]:
    """공정 raw 워크북(첫 시트)을 `ingest_process_rows`가 바로 받는 dict 리스트로 변환한다."""
    # 헤더(4행)와 본문을 각각 read_excel로 따로 읽으면 같은 워크북을 두 번 파싱하게 돼(openpyxl
    # 워크북 전체를 다시 열고 다시 순회) 대용량 파일에서 업로드마다 시간이 거의 2배가 된다 —
    # 한 번만 읽고 같은 DataFrame에서 헤더 행과 본문을 나눠 쓴다.
    full_df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=0, header=None)
    section_row = full_df.iloc[2].tolist()
    field_row = full_df.iloc[3].tolist()
    header_map = _build_header_map(section_row, field_row)

    def col(section: str | None, field: str | None = None) -> int | None:
        return header_map.get((section, field))

    def get(r, section: str | None, field: str | None = None):
        idx = col(section, field)
        return None if idx is None else r.iloc[idx]

    df = full_df.iloc[4:].reset_index(drop=True)

    date_candidate_cols = [col(name, "Date/Time") for name in _PROD_DATE_CANDIDATES]

    rows: list[dict] = []
    for _, r in df.iterrows():
        lot_id_raw = get(r, "serial no")
        # 공백 문자만 든 셀(예: "              ")은 pandas 기준 결측(NaN)이 아니라서
        # _blank()로 걸러지지 않는다 — 반드시 strip() 이후에 비어 있는지 확인해야 한다.
        # (실제 raw data에서 확인된 사례: Model Name이 공백만 채워진 행이 존재)
        lot_id = "" if _blank(lot_id_raw) else str(lot_id_raw).strip()
        if not lot_id:
            continue

        model_name_raw = get(r, "Model Name")
        model_name = "" if _blank(model_name_raw) else str(model_name_raw).strip()
        if not model_name:
            continue

        prod_date = None
        for idx in date_candidate_cols:
            if idx is None:
                continue
            value = r.iloc[idx]
            if not _blank(value):
                ts = pd.Timestamp(value)
                prod_date = ts.date().isoformat()
                break
        if prod_date is None:
            continue

        aging_start = _parse_yyyymmdd(get(r, "Aging Pallet", "Aging Start"))
        aging_end = _parse_yyyymmdd(get(r, "Aging Pallet", "Aging End"))
        aging_days = (aging_end - aging_start).days if aging_start and aging_end else None

        row: dict = {
            "lot_id": lot_id,
            "model_name": model_name,
            "line_no": _int_like_text(get(r, "Line No")),
            "prod_date": prod_date,
            "fill_weight": _native(get(r, "Filling", "Fill Weight")),
            "water_loss": _native(get(r, "Pre Test(Weight)", "Water Loss")),
            "voltage_1st": _native(get(r, "Pre Test(OCV)", "Voltage")),
            "voltage_2nd": _native(get(r, "Final Test(HRD/OCV)", "OCV")),
            "bath_no": _int_like_text(get(r, "Charging(Bath)", "Bath No")),
            "circuit_no": _int_like_text(get(r, "Charging(Bath)", "Circiut No")),
            "soaking_time_sec": _parse_soaking_seconds(get(r, "Charging(Bath)", "Soaking Time")),
            "aging_days": aging_days,
            "electrolyte_temp": None,
            "charge_amount": None,
            "tank_temp": None,
        }
        for i in range(1, 7):
            row[f"cell{i}_weight"] = _native(get(r, "Stacker Weight", f"Cell {i} Weight"))
            row[f"cell{i}_ginap"] = _native(get(r, "Stacker Force", f"Cell {i} Force"))
        rows.append(row)

    return rows
