"""backend/routers/dashboard.py의 CCA "worst 정렬" 순수 로직 단위 테스트(.docs/34).

`GET /api/analysis/y-vs-cca?sort=worst`가 EN/SAE 규격 기준 대비 여유가 가장 적은 로트를
상위로 정렬하는지 확인한다 — DB 연결 없이 판정 결과(judge_en_cca/judge_sae_cca 반환 dict)만
가지고 계산하는 `_cca_margin`/`_worst_score`만 검증한다.
"""
from __future__ import annotations

from backend.analysis.cca_spec import judge_en_cca, judge_sae_cca
from backend.routers.dashboard import _cca_margin, _worst_score


def _pair(en_voltage, en_hold, sae_hold) -> dict:
    return {
        "en_cca_spec": judge_en_cca(en_voltage, en_hold),
        "sae_cca_spec": judge_sae_cca(sae_hold),
    }


def test_en_margin_negative_when_below_threshold():
    spec = judge_en_cca(voltage_10s=7.4, hold_6v_sec=95)  # 전압만 미달(기준 7.5V)
    margin = _cca_margin(spec)
    assert margin is not None
    assert margin < 0


def test_en_margin_positive_when_above_threshold():
    spec = judge_en_cca(voltage_10s=8.0, hold_6v_sec=120)
    margin = _cca_margin(spec)
    assert margin is not None
    assert margin > 0


def test_en_margin_none_when_measurement_missing():
    spec = judge_en_cca(voltage_10s=None, hold_6v_sec=95)
    assert _cca_margin(spec) is None


def test_sae_margin_negative_when_below_threshold():
    spec = judge_sae_cca(hold_7v2_sec=20)  # 기준 30초 미달
    assert _cca_margin(spec) < 0


def test_worst_score_picks_min_of_en_and_sae():
    # EN은 크게 미달(-0.2 근처), SAE는 여유 있음(+) — 더 나쁜 EN 쪽이 대표값이어야 한다.
    pair = _pair(en_voltage=6.0, en_hold=95, sae_hold=60)
    assert _worst_score(pair) < 0


def test_worst_score_infinite_when_undetermined():
    pair = _pair(en_voltage=None, en_hold=None, sae_hold=None)
    assert _worst_score(pair) == float("inf")


def test_sorting_by_worst_score_ranks_failures_first():
    pairs = [
        _pair(en_voltage=8.0, en_hold=120, sae_hold=60),  # 전부 여유 있음
        _pair(en_voltage=6.0, en_hold=95, sae_hold=60),  # EN 크게 미달
        _pair(en_voltage=None, en_hold=None, sae_hold=None),  # 판정 불가
    ]
    ranked = sorted(pairs, key=_worst_score)
    assert ranked[0] is pairs[1]
    assert ranked[-1] is pairs[2]
