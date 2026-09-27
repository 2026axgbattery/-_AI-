from backend.analysis.trend import aggregate_by_period


def test_aggregate_by_month():
    rows = [
        {"prod_date": "2026-01-05", "retention_rate": 90.0},
        {"prod_date": "2026-01-20", "retention_rate": 92.0},
        {"prod_date": "2026-02-10", "retention_rate": 88.0},
    ]
    result = aggregate_by_period(rows, "month")
    assert result == [
        {"period": "2026-01", "avg_retention_rate": 91.0, "n": 2},
        {"period": "2026-02", "avg_retention_rate": 88.0, "n": 1},
    ]


def test_aggregate_by_day_and_year():
    rows = [
        {"prod_date": "2026-01-05", "retention_rate": 90.0},
        {"prod_date": "2026-01-05", "retention_rate": 94.0},
        {"prod_date": "2027-03-01", "retention_rate": 80.0},
    ]
    day_result = aggregate_by_period(rows, "day")
    assert day_result[0] == {"period": "2026-01-05", "avg_retention_rate": 92.0, "n": 2}

    year_result = aggregate_by_period(rows, "year")
    assert year_result == [
        {"period": "2026", "avg_retention_rate": 92.0, "n": 2},
        {"period": "2027", "avg_retention_rate": 80.0, "n": 1},
    ]


def test_rows_with_null_retention_rate_are_skipped():
    rows = [
        {"prod_date": "2026-01-05", "retention_rate": None},
        {"prod_date": "2026-01-06", "retention_rate": 90.0},
    ]
    result = aggregate_by_period(rows, "day")
    assert len(result) == 1
    assert result[0]["period"] == "2026-01-06"


def test_invalid_period_raises():
    import pytest
    with pytest.raises(ValueError):
        aggregate_by_period([], "week")
