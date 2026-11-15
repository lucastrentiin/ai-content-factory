import math

from app.services.stats import betainc, confidence_interval, prob_best, t_cdf, t_ppf, welch_test, welford


def test_t_distribution_matches_known_values():
    assert abs(t_cdf(0, 10) - 0.5) < 1e-9
    assert abs(t_cdf(2.228, 10) - 0.975) < 1e-3  # tabela t
    assert abs(t_ppf(0.975, 30) - 2.042) < 1e-2
    assert abs(betainc(2, 3, 0.4) - 0.5248) < 1e-3


def test_welford_and_ci():
    n, mean, m2 = welford([1, 2, 3, 4, 5])
    assert n == 5 and mean == 3 and math.isclose(m2 / (n - 1), 2.5)
    lo, hi = confidence_interval(n, mean, m2, 0.95)
    assert lo < 3 < hi
    assert confidence_interval(1, 1.0, 0.0) == (None, None)


def test_welch_detects_real_difference_and_not_noise():
    a = [10 + (i % 3) * 0.1 for i in range(30)]
    b = [9 + (i % 3) * 0.1 for i in range(30)]
    assert welch_test(a, b)["p_value"] < 0.001
    same = welch_test([1, 2, 3, 4, 5], [1.1, 2.1, 2.9, 4.0, 5.2])
    assert same["p_value"] > 0.5
    assert welch_test([1], [2])["p_value"] is None


def test_prob_best_prefers_clear_winner():
    pb = prob_best({"a": welford([5, 5.2, 4.9, 5.1] * 5), "b": welford([3, 3.1, 2.9, 3.0] * 5)})
    assert pb["a"] > 0.99 and abs(sum(pb.values()) - 1) < 1e-9
