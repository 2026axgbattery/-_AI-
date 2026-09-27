"""backend/etl/charge_program.py 단위 테스트.

실제 "AGM CF 충전 프로그램" 계열 워크북에서 발견된 세 가지 함정을 각각 재현해 회귀를
막는다: (1) 제목 셀에 엑셀 줄바꿈이 섞여 있는 경우, (2) STEP 나열과 Total 행 사이에
빈 행이 끼어 있는 경우, (3) Total 라벨이 "구분" 컬럼이 아니라 그 앞(No/Step 등 선행
컬럼)에 잘못 들어가 있는 경우. 근거: `history/19_v1.1-충전step-cca-확장-계획.md` Phase B.
"""
from __future__ import annotations

import io
import json

import pandas as pd

from backend.etl.charge_program import parse_charge_program_workbook

_HEADER = ["구분", "전류[A]", "시간 [Hr]", "충전량 [Ah] ", "전기량[C]"]


def _build_workbook_bytes() -> bytes:
    # 시트 "70": 블록 A(정상, Total 앞에 빈 행 2개) + 블록 B("No" 선행 컬럼 + 개행 섞인
    # 제목 + Total 라벨이 "No" 컬럼에 잘못 들어간 경우, 변경 프로그램이라 임시 버전으로 취급)
    rows = [[None] * 12 for _ in range(12)]
    rows[0][0] = "AGM70_B, S_44hr"
    rows[2][0:5] = _HEADER
    rows[3][0:5] = ["CHA", 3.0, 1.0, 3.0, 0.043]
    rows[4][0:5] = ["DCH", -18.0, 0.5, -9.0, -0.129]
    # 5~6행은 완전히 빈 행(Total 앞 padding)
    rows[7][0:5] = ["Total　", None, 1.5, -6.0, -0.086]

    rows[0][6] = "AGM70_G 변경 프로그램\n(2~4라인)"
    rows[2][6:12] = ["No", *_HEADER]
    rows[3][6:12] = [1, "CHA", 17.0, 1.0, 17.0, 0.243]
    rows[4][6:12] = [2, "DCH", -18.0, 0.5, -9.0, -0.129]
    # Total 라벨이 "No" 컬럼(6)에 들어가고 "구분" 컬럼(7)은 비어 있는, 원본에서 실제 발견된
    # 오탈자 패턴. 나머지 값(시간/충전량/전기량)은 평소와 같이 "구분" 기준 상대 위치를 지킨다.
    rows[5][6] = "Total　"
    rows[5][9] = 1.5
    rows[5][10] = 8.0
    rows[5][11] = 0.114

    matrix = pd.DataFrame(rows)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        matrix.to_excel(writer, sheet_name="70", header=False, index=False)
    buffer.seek(0)
    return buffer.read()


def test_parses_both_blocks_with_correct_totals():
    rows = parse_charge_program_workbook(_build_workbook_bytes())
    by_buyer = {r["buyer_code"]: r for r in rows}

    assert set(by_buyer) == {"B", "S", "G"}
    assert by_buyer["B"]["total_charge_ah"] == -6.0
    assert by_buyer["B"]["charge_hours"] == 44.0  # 제목의 "_44hr"가 Total 행 값보다 우선
    assert by_buyer["B"]["is_variant"] is False


def test_title_with_embedded_newline_is_parsed_not_dropped():
    """엑셀 줄바꿈이 섞인 제목("...\\n(2~4라인)")도 정상 인식돼야 한다 — 정규식 `.`이
    개행을 못 건너뛰어 블록 전체가 통째로 버려지는 버그의 회귀 테스트."""
    rows = parse_charge_program_workbook(_build_workbook_bytes())
    by_buyer = {r["buyer_code"]: r for r in rows}
    assert "G" in by_buyer
    assert by_buyer["G"]["is_variant"] is True  # "변경"이 포함돼 임시/변경 버전으로 표시


def test_total_row_with_misplaced_label_column_still_found():
    """Total 라벨이 "구분" 컬럼이 아니라 선행("No") 컬럼에 잘못 들어간 경우에도 Total 값을
    찾아야 한다 — 라벨을 "구분" 컬럼에서만 찾으면 조용히 None이 되는 버그의 회귀 테스트."""
    rows = parse_charge_program_workbook(_build_workbook_bytes())
    by_buyer = {r["buyer_code"]: r for r in rows}
    assert by_buyer["G"]["total_charge_ah"] == 8.0
    assert by_buyer["G"]["total_electricity_c"] == 0.114


def test_blank_rows_between_steps_and_total_do_not_truncate_scan():
    """STEP 나열과 Total 행 사이에 완전히 빈 행이 끼어 있어도 Total까지 계속 스캔해야 한다."""
    rows = parse_charge_program_workbook(_build_workbook_bytes())
    by_buyer = {r["buyer_code"]: r for r in rows}
    steps = json.loads(by_buyer["B"]["steps_json"])
    assert len(steps) == 2  # 빈 행은 STEP으로 세지 않음
    assert steps[0]["step_type"] == "CHA"
    assert steps[1]["step_type"] == "DCH"


def test_capacity_92_is_normalized_to_90():
    """원본 파일은 정격 90Ah 제품을 "AGM92"로 표기한다(사용자 확인, history/19) — 우리 시스템의
    model_name(AGM90_*)과 매칭되도록 90으로 저장해야 한다."""
    rows = [[None] * 6 for _ in range(10)]
    rows[0][0] = "AGM92_All_35hr"
    rows[2][0:5] = _HEADER
    rows[3][0:5] = ["CHA", 6.0, 0.5, 3.0, 0.029]
    rows[4][0:5] = ["Total　", None, 0.5, 3.0, 0.029]
    matrix = pd.DataFrame(rows)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        matrix.to_excel(writer, sheet_name="92", header=False, index=False)
    buffer.seek(0)

    parsed = parse_charge_program_workbook(buffer.read())
    assert len(parsed) == 1
    assert parsed[0]["rated_capacity"] == 90.0
    assert parsed[0]["buyer_code"] == "All"


def test_variant_program_shares_buyer_code_with_base_when_present():
    """같은 (정격용량, 바이어 코드)에 기본/변경 버전이 둘 다 있으면 둘 다 반환하고, 어떤 걸
    쓸지는 조회 시점(repository)에서 결정한다(history/19)."""
    rows = parse_charge_program_workbook(_build_workbook_bytes())
    g_rows = [r for r in rows if r["buyer_code"] == "G"]
    assert len(g_rows) == 1
    assert g_rows[0]["rated_capacity"] == 70.0
