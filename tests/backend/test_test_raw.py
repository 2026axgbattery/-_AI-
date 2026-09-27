"""backend/etl/test_raw.py 단위 테스트.

.docs/14_raw-data-업로드-지원-계획.md의 매핑표를 근거로, 실제 "AGM 시험현황_raw data" 계열
raw data의 세로 시험항목 트리 × 가로 샘플 구조를 축소 재현한 워크북으로 검증한다.
"""
from __future__ import annotations

import io

import pandas as pd

from backend.etl.test_raw import parse_test_raw_workbook

# (섹션, 필드, [LOT_A, LOT_B, LOT_C, LOT_D]용 값)
# LOT_C는 20HR용량(1차)이 비어 있어 건너뛰어야 하고, LOT_D는 제조로트 셀이 공백 문자만
# 있는 경우(실제 raw data에서 발견된 사례, .docs/14)라 용량 데이터가 있어도 건너뛰어야 한다.
_ROWS = [
    ("구분", "시험항목", ["AGM70", None, None, None]),
    ("초기상태", "제조로트", ["LOT_A", "LOT_B", "LOT_C", "              "]),
    (None, "전압", [12.87, 12.88, 12.89, 12.91]),
    (None, "내부저항", [3.27, 3.30, 3.28, 3.29]),
    (None, "중량", [20188, 20099, 20124, 20100]),
    ("공정 SPC DATA", "주액량", [4525, 4517, 4520, 4519]),
    (None, "MT(V)", [12.86, 12.87, 12.88, 12.89]),
    (None, "MT(A)", [785, 784, 786, 787]),
    ("20HR용량(1차)", "시험일자", ["2026-06-15", None, None, "2026-06-15"]),
    (None, "회로", [78, None, None, 78]),
    (None, "방전량", [75.37, 74.5, None, 74.0]),
    (None, "충전량", [80.33, 80.0, None, 80.0]),
    (None, "용량(%)", [107.67, 105.0, None, 105.0]),
    (None, "충전율(%)", [106.58, 104.0, None, 104.0]),
    ("SAE CCA(1차)\n18℃ 24H 방치", "10초 전압", [7.9, None, None, None]),
    ("SAE CCA(1차)\n18℃ 24H 방치", "30초 전압", [7.6, None, None, None]),
    ("SAE CCA(1차)\n18℃ 24H 방치", "7.2V 지속시간", [35.0, None, None, None]),
    ("SAE CCA(1차)\n18℃ 24H 방치", "방전량", [5.457, None, None, None]),
    # "EN CCA 18℃"는 실제 raw data처럼 두 번 등장한다. 첫 occurrence(신뢰성 프로토콜 초반
    # 체크포인트)는 이 배치에서 전부 공란이고, 두 번째 occurrence(SAE CCA 이후 체크포인트)에만
    # 실측값이 있다 — 최초 occurrence만 보면 조용히 전부 None이 되는 버그를 재현/검증한다.
    ("EN CCA 18℃", "10초 전압", [None, None, None, None]),
    ("EN CCA 18℃", "6.0V 지속시간\n(17초 포함)", [None, None, None, None]),
    ("EN CCA 18℃", "방전량", [None, None, None, None]),
    # 두 번째 occurrence는 "6.0V 지속시간" 표기에 괄호 보충설명이 없다(history/20) — 실제
    # raw data에서 발견된 표기 불일치. _canon_field로 정규화해 첫 번째 occurrence의
    # "6.0V 지속시간\n(17초 포함)"과 같은 키로 묶여야 한다.
    ("EN CCA 18℃", "10초 전압", [None, 7.7, None, None]),
    # 실제 raw data에서 이 필드는 순수 숫자가 아니라 "92초"처럼 단위 문자열이 붙어 있을 수
    # 있다(history/20) — 텍스트로 들어와도 숫자만 뽑아내야 한다.
    ("EN CCA 18℃", "6.0V 지속시간", [None, "92초", None, None]),
    ("EN CCA 18℃", "방전량", [None, 6.903, None, None]),
]


def _build_workbook_bytes() -> bytes:
    matrix = [[label[0], label[1], *label[2]] for label in _ROWS]
    buffer = io.BytesIO()
    pd.DataFrame(matrix).to_excel(buffer, header=False, index=False, engine="openpyxl")
    buffer.seek(0)
    return buffer.read()


def test_parse_test_raw_workbook_skips_samples_without_capacity_data():
    rows = parse_test_raw_workbook(_build_workbook_bytes())
    lot_ids = {r["lot_id"] for r in rows}
    assert lot_ids == {"LOT_A", "LOT_B"}  # LOT_C는 20HR용량(1차) 데이터가 없어 제외, LOT_D는 아래 참조


def test_whitespace_only_lot_id_is_skipped_not_crashed():
    """제조로트 셀이 공백 문자만 있으면 용량 데이터가 있어도 건너뛰어야 한다(파일 전체가
    실패하면 안 됨) — pd.isna()로는 걸러지지 않으므로 strip() 후 확인해야 한다."""
    rows = parse_test_raw_workbook(_build_workbook_bytes())
    lot_ids = {r["lot_id"] for r in rows}
    assert "" not in lot_ids
    assert lot_ids == {"LOT_A", "LOT_B"}


def test_mt_a_is_reflected_in_both_mt_current_and_initial_cca():
    rows = parse_test_raw_workbook(_build_workbook_bytes())
    lot_a = next(r for r in rows if r["lot_id"] == "LOT_A")
    assert lot_a["mt_current"] == 785
    assert lot_a["initial_cca"] == 785
    assert lot_a["mt_voltage"] == 12.86


def test_capacity_fields_mapped_from_20hr_section():
    rows = parse_test_raw_workbook(_build_workbook_bytes())
    lot_a = next(r for r in rows if r["lot_id"] == "LOT_A")
    assert lot_a["discharge_amount"] == 75.37
    assert lot_a["charge_amount_20h"] == 80.33
    assert lot_a["capacity_rate"] == 107.67
    assert lot_a["charge_rate"] == 106.58
    assert lot_a["initial_voltage"] == 12.87
    assert lot_a["initial_resistance"] == 3.27
    assert lot_a["initial_weight"] == 20188


def test_sae_and_en_cca_are_extracted_and_duplicate_section_picks_populated_occurrence():
    """history/19: sae_cca/en_cca는 신뢰성 시험 raw data 전용 필드. "EN CCA 18℃" 구간명은
    파일 내에 두 번 등장하는데, 첫 occurrence는 공란이고 값은 두 번째 occurrence에 있다 —
    최초 occurrence만 쓰면 조용히 None이 되는 버그를 여기서 잡는다."""
    rows = parse_test_raw_workbook(_build_workbook_bytes())
    by_lot = {r["lot_id"]: r for r in rows}
    assert by_lot["LOT_A"]["sae_cca"] == 5.457
    assert by_lot["LOT_A"]["en_cca"] is None
    assert by_lot["LOT_B"]["sae_cca"] is None
    assert by_lot["LOT_B"]["en_cca"] == 6.903


def test_cca_checkpoint_fields_extracted_and_label_variant_normalized():
    """history/20: 신규 en_cca_10s_voltage/en_cca_6v_hold_sec/sae_cca_7v2_hold_sec 추출 확인.
    EN CCA 6.0V 지속시간은 occurrence마다 "\\n(17초 포함)" 유무가 달라 정규화 없이는
    두 번째(실측값이 있는) occurrence를 못 찾는다."""
    rows = parse_test_raw_workbook(_build_workbook_bytes())
    by_lot = {r["lot_id"]: r for r in rows}
    assert by_lot["LOT_A"]["sae_cca_7v2_hold_sec"] == 35.0
    assert by_lot["LOT_B"]["en_cca_10s_voltage"] == 7.7
    assert by_lot["LOT_B"]["en_cca_6v_hold_sec"] == 92.0


def test_rated_capacity_falls_back_to_sheet_label_and_lookup_overrides():
    rows = parse_test_raw_workbook(_build_workbook_bytes())
    by_lot = {r["lot_id"]: r for r in rows}
    assert by_lot["LOT_A"]["rated_capacity"] == 70.0  # 시트 헤더 "AGM70"에서 파싱
    assert by_lot["LOT_B"]["rated_capacity"] == 70.0

    rows_with_lookup = parse_test_raw_workbook(
        _build_workbook_bytes(), rated_capacity_lookup={"LOT_A": 90.0}
    )
    by_lot2 = {r["lot_id"]: r for r in rows_with_lookup}
    assert by_lot2["LOT_A"]["rated_capacity"] == 90.0  # lookup이 시트 헤더보다 우선
    assert by_lot2["LOT_B"]["rated_capacity"] == 70.0  # lookup에 없으면 시트 헤더로 폴백
