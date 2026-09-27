"""형명별 Y(포화도) 추이 집계(docs/prd.md §6-③-4). `prod_date` 기준 단순 시계열 group-by — 학습 없음.

순수 함수만 둔다(웹 프레임워크·DB 비의존).
"""
from __future__ import annotations

from collections import defaultdict
from statistics import mean

_PERIOD_KEY_LENGTH = {"day": 10, "month": 7, "year": 4}  # "YYYY-MM-DD"를 앞에서 자르는 길이


def aggregate_by_period(rows: list[dict], period: str) -> list[dict]:
    """rows: [{"prod_date": "YYYY-MM-DD", "retention_rate": float}, ...].

    period별(day/month/year) 평균 retention_rate와 표본 수(n)를 시간순으로 반환한다.
    """
    if period not in _PERIOD_KEY_LENGTH:
        raise ValueError(f"지원하지 않는 period입니다: {period}")
    key_length = _PERIOD_KEY_LENGTH[period]

    buckets: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        prod_date = row.get("prod_date")
        retention_rate = row.get("retention_rate")
        if not prod_date or retention_rate is None:
            continue
        buckets[prod_date[:key_length]].append(retention_rate)

    return [
        {"period": key, "avg_retention_rate": mean(values), "n": len(values)}
        for key, values in sorted(buckets.items())
    ]
