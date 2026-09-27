from backend.analysis.significance import pearson_r_p


def test_perfect_positive_correlation_is_significant():
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    y = [2.0, 4.0, 6.0, 8.0, 10.0]
    result = pearson_r_p(x, y)
    assert round(result["r"], 6) == 1.0
    assert result["significant"] is True
    assert result["n"] == 5


def test_no_correlation_signal_returns_low_significance_confidence():
    x = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    y = [3.0, 1.0, 4.0, 1.0, 5.0, 9.0]
    result = pearson_r_p(x, y)
    assert result["r"] is not None
    assert result["p_value"] is not None


def test_too_few_samples_returns_none():
    result = pearson_r_p([1.0, 2.0], [1.0, 2.0])
    assert result == {"r": None, "p_value": None, "significant": False, "n": 2}
