"""충전 STEP/SPEC 기준표(예: "AGM CF 충전 프로그램" 계열 .xlsx) 파서.

원본은 정격용량군별 시트(예: "70") 안에 바이어 코드 그룹별 충전 프로그램이 가로로 여러 개
나란히 배치된 구조다. 각 블록은 제목 행(예: "AGM70_H, Y, Z, C_35hr") 아래 STEP별
구분(CHA/DCH/PAU)·전류[A]·시간[Hr]·충전량[Ah]·전기량[C] 행이 나열되고 "Total" 행으로 끝난다.
매핑 근거·범위 확정 경위는 `history/19_v1.1-충전step-cca-확장-계획.md` Phase B 참조.
"""
from __future__ import annotations

import io
import json
import re

import pandas as pd

# 이 파일에서 다루는 시트만 대상으로 한다. "1세대"(구형 1G- 모델)는 현재 로트를 어느 세대로
# 볼지 판단할 근거(예: 극판 세대)가 우리 데이터에 없어 제외하기로 확정(history/19 Phase B 질의응답,
# 2026-09-21). "방전효율"은 요약/참고용 별도 표라 이번 이탈도 계산에는 쓰지 않는다.
_CAPACITY_SHEET_NAMES = {"50", "60", "70", "80", "92", "105"}

# 원본 파일은 정격 90Ah 제품을 "AGM92"로 표기한다(사용자 확인, history/19 Phase B, 2026-09-21) —
# 방전효율 요약 시트의 "AGM90" 행과 총 충전량[Ah]이 정확히 일치함으로 교차검증됨. 우리 시스템의
# model_name(AGM90_*)과 매칭되도록 90으로 정규화해서 저장한다.
_CAPACITY_ALIAS = {92.0: 90.0}

_HR_SUFFIX_RE = re.compile(r"^(?P<buyers>.*?)_(?P<hours>\d+(?:\.\d+)?)\s*hr\s*$", re.IGNORECASE)
_TRAILING_PAREN_RE = re.compile(r"\s*\(([^)]*)\)\s*$")
_CAPACITY_PREFIX_RE = re.compile(r"^AGM(?P<capacity>\d+(?:\.\d+)?)_(?P<rest>.+)$")


def _blank(value) -> bool:
    try:
        result = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return bool(result)


def _native(value):
    if _blank(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _parse_block_title(title: str) -> dict | None:
    """블록 제목(예: "AGM70_D_44hr (6.5C 임시 사양)")을 (정격용량, 바이어 코드 목록,
    임시/변경 버전 여부, 시간[Hr])로 분해한다. 형식을 인식 못 하면 None(무시).

    일부 제목 셀은 엑셀 줄바꿈이 섞여 있다(예: "AGM70_G 변경 프로그램\\n(2~4라인)") — 정규식의
    `.`이 개행을 못 건너뛰어 파싱이 통째로 실패하므로 먼저 공백류를 한 칸으로 정규화한다.
    """
    text = re.sub(r"\s+", " ", str(title).strip())
    match = _CAPACITY_PREFIX_RE.match(text)
    if not match:
        return None
    capacity = float(match.group("capacity"))
    capacity = _CAPACITY_ALIAS.get(capacity, capacity)
    rest = match.group("rest").strip()

    is_variant = False
    paren = _TRAILING_PAREN_RE.search(rest)
    if paren:
        is_variant = True
        rest = _TRAILING_PAREN_RE.sub("", rest).strip()

    hours = None
    hr_match = _HR_SUFFIX_RE.match(rest)
    if hr_match:
        buyer_part = hr_match.group("buyers").strip()
        hours = float(hr_match.group("hours"))
    else:
        # "G 변경 프로그램" / "H 임시 프로그램"처럼 "_NNhr" 접미가 없는 경우 — 첫 공백 앞까지가
        # 바이어 코드, 나머지는 부가 설명(임시/변경 여부 판단용).
        parts = rest.split(None, 1)
        buyer_part = parts[0]
        remainder = parts[1] if len(parts) > 1 else ""
        if "임시" in remainder or "변경" in remainder:
            is_variant = True

    if "임시" in rest or "변경" in rest:
        is_variant = True

    buyer_codes = [c.strip() for c in buyer_part.split(",") if c.strip()]
    if not buyer_codes:
        return None

    return {
        "rated_capacity": capacity,
        "buyer_codes": buyer_codes,
        "is_variant": is_variant,
        "charge_hours": hours,
        "program_label": text,
    }


def _find_block_starts(df: pd.DataFrame, title_row: int) -> list[int]:
    return [j for j in range(df.shape[1]) if not _blank(df.iat[title_row, j])]


def _find_header_row(df: pd.DataFrame, title_row: int, col_start: int, col_end: int) -> tuple[int, int] | None:
    """블록 안에서 "구분" 헤더 셀의 (행, 열)을 찾는다. 블록마다 "Step"/"No" 같은 선행 컬럼
    유무가 달라 열 위치가 고정돼 있지 않다."""
    for i in range(title_row, min(title_row + 5, df.shape[0])):
        for j in range(col_start, col_end):
            if not _blank(df.iat[i, j]) and str(df.iat[i, j]).strip() == "구분":
                return i, j
    return None


def _parse_block(df: pd.DataFrame, title_row: int, col_start: int, col_end: int) -> dict | None:
    title = df.iat[title_row, col_start]
    if _blank(title):
        return None
    meta = _parse_block_title(title)
    if meta is None:
        return None

    header = _find_header_row(df, title_row, col_start, col_end)
    if header is None:
        return None
    header_row, col_type = header
    col_current, col_hours, col_charge_ah, col_electricity_c = (
        col_type + 1, col_type + 2, col_type + 3, col_type + 4
    )

    steps: list[dict] = []
    total_row = None
    for i in range(header_row + 1, df.shape[0]):
        block_cells = [df.iat[i, j] for j in range(col_start, col_end)]
        if all(_blank(v) for v in block_cells):
            # STEP 나열이 끝나고 "Total" 행 사이에 빈 행이 끼어 있는 블록이 있다(예: "50" 시트) —
            # 첫 빈 행에서 바로 멈추면 Total을 못 찾으므로 건너뛰고 계속 스캔한다.
            continue
        # "Total" 라벨이 항상 "구분" 컬럼에 있지는 않다 — 원본 일부 블록은 Total 행에서만
        # 한 칸 밀려 있다(예: "60" 시트 "AGM60_H 임시 프로그램" 블록). 블록 폭 전체에서 찾는다.
        if any(not _blank(v) and str(v).strip().startswith("Total") for v in block_cells):
            total_row = i
            break
        type_val = df.iat[i, col_type] if col_type < df.shape[1] else None
        if _blank(type_val):
            continue
        type_text = str(type_val).strip()
        # col_current~col_electricity_c는 반드시 이 블록의 폭(col_end) 안에서만 읽어야 한다 —
        # df.shape[1](시트 전체 폭)까지 허용하면 옆 블록의 컬럼 수가 이 블록보다 적을 때
        # 인접 블록의 셀 값을 이 블록 것으로 잘못 읽어온다.
        steps.append({
            "step_type": type_text,
            "current_a": _native(df.iat[i, col_current]) if col_current < col_end else None,
            "hours": _native(df.iat[i, col_hours]) if col_hours < col_end else None,
            "charge_ah": _native(df.iat[i, col_charge_ah]) if col_charge_ah < col_end else None,
            "electricity_c": _native(df.iat[i, col_electricity_c]) if col_electricity_c < col_end else None,
        })

    charge_hours = meta["charge_hours"]
    total_charge_ah = None
    total_electricity_c = None
    if total_row is not None:
        if charge_hours is None:
            charge_hours = _native(df.iat[total_row, col_hours]) if col_hours < col_end else None
        total_charge_ah = _native(df.iat[total_row, col_charge_ah]) if col_charge_ah < col_end else None
        total_electricity_c = (
            _native(df.iat[total_row, col_electricity_c]) if col_electricity_c < col_end else None
        )

    return {
        "rated_capacity": meta["rated_capacity"],
        "buyer_codes": meta["buyer_codes"],
        "is_variant": meta["is_variant"],
        "program_label": meta["program_label"],
        "charge_hours": charge_hours,
        "total_charge_ah": total_charge_ah,
        "total_electricity_c": total_electricity_c,
        "steps": steps,
    }


def parse_charge_program_workbook(file_bytes: bytes) -> list[dict]:
    """충전 프로그램 워크북을 `ChargeProgramSpec` 행(바이어 코드 1개당 1행)으로 변환한다.

    같은 (정격용량, 바이어 코드) 조합에 기본/임시(변경) 두 버전이 있을 수 있다 — 여기서는
    원본 그대로 전부 반환하고, "어떤 버전을 쓸지"는 조회 시점(repository)에서 결정한다
    (history/19: 기본 버전을 우선하고, 기본이 없으면 유일한 후보를 그대로 쓴다).
    """
    xl = pd.ExcelFile(io.BytesIO(file_bytes))
    rows: list[dict] = []
    for sheet_name in xl.sheet_names:
        if sheet_name not in _CAPACITY_SHEET_NAMES:
            continue
        df = xl.parse(sheet_name, header=None)
        if df.shape[0] == 0 or df.shape[1] == 0:
            continue

        block_starts = _find_block_starts(df, title_row=0)
        for idx, col_start in enumerate(block_starts):
            col_end = block_starts[idx + 1] if idx + 1 < len(block_starts) else df.shape[1]
            block = _parse_block(df, title_row=0, col_start=col_start, col_end=col_end)
            if block is None:
                continue
            for buyer_code in block["buyer_codes"]:
                rows.append({
                    "rated_capacity": block["rated_capacity"],
                    "buyer_code": buyer_code,
                    "program_label": block["program_label"],
                    "is_variant": block["is_variant"],
                    "charge_hours": block["charge_hours"],
                    "total_charge_ah": block["total_charge_ah"],
                    "total_electricity_c": block["total_electricity_c"],
                    "steps_json": json.dumps(block["steps"], ensure_ascii=False),
                })
    return rows
