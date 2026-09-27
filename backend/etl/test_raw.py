"""시험 raw data(.xlsx, 예: "AGM 시험현황_raw data" 계열 파일) 파서.

원본은 시트 1개당 세로 방향 시험항목 트리(1열=대분류, 2열=세부항목) × 가로 방향 샘플(로트)
컬럼(3번째 열부터)의 전치된 구조다. 신뢰성 서브시험별로 선택된 일부 샘플만 값이 채워지므로,
표준 20시간 용량 시험(`20HR용량(1차)`)이 아직 없는 샘플은 건너뛴다. 매핑 근거는
`.docs/14_raw-data-업로드-지원-계획.md` 참조.
"""
from __future__ import annotations

import io
import re

import pandas as pd

_SAMPLE_START_COL = 2


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


_NUMERIC_PREFIX = re.compile(r"-?\d+(?:\.\d+)?")


def _numeric(value) -> float | None:
    """CCA 체크포인트 셀은 종종 숫자에 단위 문자열이 섞여 있다(실제 raw data 확인, history/20:
    "25초"·"60초"). 앞의 숫자만 뽑아 float로 변환한다 — 이미 숫자형이면 그대로 반환."""
    if _blank(value):
        return None
    if isinstance(value, (int, float)):
        return _native(value)
    match = _NUMERIC_PREFIX.search(str(value))
    return float(match.group()) if match else None


def _parse_rated_capacity_from_sheet_label(label) -> float | None:
    if _blank(label):
        return None
    match = re.search(r"(\d+)", str(label))
    return float(match.group(1)) if match else None


def _canon_field(label: str) -> str:
    """줄바꿈 뒤에 붙는 보충 설명만 제거한다(예: "6.0V 지속시간\\n(17초 포함)" ->
    "6.0V 지속시간"). 같은 체크포인트가 occurrence마다 표기가 살짝 다른 경우를 하나의
    (구간, 필드) 키로 묶기 위함(history/20) — "MT(V)"처럼 줄바꿈 없이 괄호가 붙은 필드명은
    건드리지 않는다."""
    return re.sub(r"\n\(.*?\)\s*$", "", label).strip()


def _build_row_map(df: pd.DataFrame) -> dict[tuple[str | None, str | None], list[int]]:
    """(구간, 필드) -> 해당 구간명이 등장하는 모든 행 번호 목록.

    신뢰성 시험 raw data는 같은 구간명(예: "EN CCA 18℃")이 시험 프로토콜의 서로 다른
    체크포인트에서 여러 번 반복될 수 있다. 어떤 occurrence를 쓸지는 필드별로 다르게
    정한다 — `_first_row`(기존 필드, 최초 occurrence 유지)와 `_best_row`(실측값이 채워진
    occurrence 우선, CCA류 신규 필드)를 각각 사용한다.
    """
    row_map: dict[tuple[str | None, str | None], list[int]] = {}
    current_section: str | None = None
    for i in range(df.shape[0]):
        sec = df.iat[i, 0]
        fld = df.iat[i, 1] if df.shape[1] > 1 else None
        if not _blank(sec):
            current_section = str(sec).strip()
        key_field = None if _blank(fld) else _canon_field(str(fld).strip())
        row_map.setdefault((current_section, key_field), []).append(i)
    return row_map


def _first_row(row_map: dict, key: tuple[str | None, str | None]) -> int | None:
    rows = row_map.get(key)
    return rows[0] if rows else None


def _best_row(df: pd.DataFrame, row_map: dict, key: tuple[str | None, str | None]) -> int | None:
    """같은 (구간, 필드)가 여러 번 등장하면 샘플 컬럼 중 실측값이 가장 많이 채워진 occurrence를
    고른다(동률이면 더 나중 occurrence). 구간명 최초 등장만 보면 빈 블록을 골라 조용히 전부
    NULL이 되는 문제가 생기기 때문."""
    rows = row_map.get(key)
    if not rows:
        return None
    best_row, best_count = rows[0], -1
    for r in rows:
        count = int(df.iloc[r, _SAMPLE_START_COL:].notna().sum())
        if count >= best_count:
            best_row, best_count = r, count
    return best_row


def parse_test_raw_workbook(
    file_bytes: bytes, rated_capacity_lookup: dict[str, float] | None = None
) -> list[dict]:
    """시험 raw 워크북의 모든 시트를 `ingest_test_rows`가 바로 받는 dict 리스트로 변환한다."""
    rated_capacity_lookup = rated_capacity_lookup or {}
    xl = pd.ExcelFile(io.BytesIO(file_bytes))

    rows: list[dict] = []
    for sheet_name in xl.sheet_names:
        df = xl.parse(sheet_name, header=None)
        if df.shape[1] <= _SAMPLE_START_COL:
            continue

        row_map = _build_row_map(df)
        lot_row = _first_row(row_map, ("초기상태", "제조로트"))
        if lot_row is None:
            continue

        voltage_row = _first_row(row_map, ("초기상태", "전압"))
        resistance_row = _first_row(row_map, ("초기상태", "내부저항"))
        weight_row = _first_row(row_map, ("초기상태", "중량"))
        mt_v_row = _first_row(row_map, ("공정 SPC DATA", "MT(V)"))
        mt_a_row = _first_row(row_map, ("공정 SPC DATA", "MT(A)"))
        discharge_row = _first_row(row_map, ("20HR용량(1차)", "방전량"))
        charge_row = _first_row(row_map, ("20HR용량(1차)", "충전량"))
        capacity_rate_row = _first_row(row_map, ("20HR용량(1차)", "용량(%)"))
        charge_rate_row = _first_row(row_map, ("20HR용량(1차)", "충전율(%)"))
        # history/19: 신뢰성 시험 raw data 전용 CCA 필드 — "SAE CCA(1차)\n18℃ 24H 방치"/
        # "EN CCA 18℃" 구간의 방전량(Ah). "EN CCA 18℃"는 프로토콜상 여러 체크포인트에서
        # 반복 등장하므로 실측값이 채워진 occurrence를 고른다.
        sae_cca_row = _best_row(df, row_map, ("SAE CCA(1차)\n18℃ 24H 방치", "방전량"))
        en_cca_row = _best_row(df, row_map, ("EN CCA 18℃", "방전량"))
        # history/20: EN/SAE CCA 규격 판정(analysis/cca_spec.py)에 쓰는 전압·시간 체크포인트.
        # 필드명은 _canon_field로 정규화된 키를 쓴다.
        en_10s_voltage_row = _best_row(df, row_map, ("EN CCA 18℃", "10초 전압"))
        en_6v_hold_sec_row = _best_row(df, row_map, ("EN CCA 18℃", "6.0V 지속시간"))
        sae_7v2_hold_sec_row = _best_row(
            df, row_map, ("SAE CCA(1차)\n18℃ 24H 방치", "7.2V 지속시간")
        )

        sheet_rated_capacity = _parse_rated_capacity_from_sheet_label(df.iat[0, _SAMPLE_START_COL])

        for col_idx in range(_SAMPLE_START_COL, df.shape[1]):
            lot_id_val = df.iat[lot_row, col_idx]
            # 공백 문자만 든 셀은 pandas 기준 결측(NaN)이 아니라 _blank()로 걸러지지 않는다 —
            # strip() 이후에 비어 있는지 확인해야 한다(backend/etl/process_raw.py와 동일한 이유).
            lot_id = "" if _blank(lot_id_val) else str(lot_id_val).strip()
            if not lot_id:
                continue

            discharge = df.iat[discharge_row, col_idx] if discharge_row is not None else None
            if _blank(discharge):
                # 20HR용량(1차) 데이터가 없는 샘플은 아직 표준 용량 시험을 하지 않은 것이므로 건너뛴다.
                continue
            mt_current = _native(df.iat[mt_a_row, col_idx]) if mt_a_row is not None else None

            rows.append({
                "lot_id": lot_id,
                "initial_voltage": _native(df.iat[voltage_row, col_idx]) if voltage_row is not None else None,
                "initial_resistance": (
                    _native(df.iat[resistance_row, col_idx]) if resistance_row is not None else None
                ),
                "initial_weight": _native(df.iat[weight_row, col_idx]) if weight_row is not None else None,
                # 사용자 확인(history/19): MT(A)는 공정 SPC DATA의 간이 측정치로 CCA의 참고 근사값일
                # 뿐, sae_cca/en_cca(정식 SAE/EN CCA 시험 결과)와는 단위·성격이 다르다.
                "initial_cca": mt_current,
                "mt_voltage": _native(df.iat[mt_v_row, col_idx]) if mt_v_row is not None else None,
                "mt_current": mt_current,
                "rated_capacity": rated_capacity_lookup.get(lot_id, sheet_rated_capacity),
                "discharge_amount": _native(discharge),
                "charge_amount_20h": _native(df.iat[charge_row, col_idx]) if charge_row is not None else None,
                "capacity_rate": (
                    _native(df.iat[capacity_rate_row, col_idx]) if capacity_rate_row is not None else None
                ),
                "charge_rate": (
                    _native(df.iat[charge_rate_row, col_idx]) if charge_rate_row is not None else None
                ),
                "sae_cca": _numeric(df.iat[sae_cca_row, col_idx]) if sae_cca_row is not None else None,
                "en_cca": _numeric(df.iat[en_cca_row, col_idx]) if en_cca_row is not None else None,
                "en_cca_10s_voltage": (
                    _numeric(df.iat[en_10s_voltage_row, col_idx])
                    if en_10s_voltage_row is not None else None
                ),
                "en_cca_6v_hold_sec": (
                    _numeric(df.iat[en_6v_hold_sec_row, col_idx])
                    if en_6v_hold_sec_row is not None else None
                ),
                "sae_cca_7v2_hold_sec": (
                    _numeric(df.iat[sae_7v2_hold_sec_row, col_idx])
                    if sae_7v2_hold_sec_row is not None else None
                ),
            })

    return rows
