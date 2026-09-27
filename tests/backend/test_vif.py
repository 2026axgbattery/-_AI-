from backend.analysis.vif import compute_vif


def test_perfectly_collinear_columns_have_high_vif():
    a = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    b = [2.0 * v for v in a]  # b = 2a, 완전 공선
    c = [5.0, 1.0, 9.0, 2.0, 7.0, 3.0, 8.0, 4.0, 6.0, 10.0]

    result = compute_vif({"a": a, "b": b, "c": c})

    assert result["a"] > 100 or result["a"] == float("inf")
    assert result["b"] > 100 or result["b"] == float("inf")


def test_single_column_has_no_vif():
    result = compute_vif({"only": [1.0, 2.0, 3.0]})
    assert result["only"] is None


def test_insufficient_sample_returns_none():
    result = compute_vif({"a": [1.0, 2.0], "b": [3.0, 4.0], "c": [5.0, 6.0]})
    # n=2, others=2개라 n <= len(others)+1 조건에 걸려 전부 None이어야 함
    assert result == {"a": None, "b": None, "c": None}
