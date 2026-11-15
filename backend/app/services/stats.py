"""Estatística sem dependências pesadas: Welford, IC por t de Student, teste de Welch, P(melhor) por amostragem."""
from __future__ import annotations

import math
import random


def _betacf(a: float, b: float, x: float) -> float:
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    d = 1 / (d if abs(d) > 1e-30 else 1e-30)
    h = d
    for m in range(1, 200):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d
        d = 1 / (d if abs(d) > 1e-30 else 1e-30)
        c = 1 + aa / c if abs(c) > 1e-30 else 1e-30
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d
        d = 1 / (d if abs(d) > 1e-30 else 1e-30)
        c = 1 + aa / c if abs(c) > 1e-30 else 1e-30
        de = d * c
        h *= de
        if abs(de - 1) < 3e-10:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x)
    if x < (a + 1) / (a + b + 2):
        return math.exp(lbeta) * _betacf(a, b, x) / a
    return 1 - math.exp(lbeta) * _betacf(b, a, 1 - x) / b


def t_cdf(t: float, df: float) -> float:
    x = df / (df + t * t)
    p = 0.5 * betainc(df / 2, 0.5, x)
    return 1 - p if t > 0 else p


def t_ppf(q: float, df: float) -> float:
    lo, hi = -50.0, 50.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if t_cdf(mid, df) < q:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def welford(values: list[float]) -> tuple[int, float, float]:
    n, mean, m2 = 0, 0.0, 0.0
    for v in values:
        n += 1
        d = v - mean
        mean += d / n
        m2 += d * (v - mean)
    return n, mean, m2


def confidence_interval(n: int, mean: float, m2: float, confidence: float = 0.9) -> tuple[float | None, float | None]:
    if n < 2:
        return None, None
    s = math.sqrt(m2 / (n - 1))
    half = t_ppf(0.5 + confidence / 2, n - 1) * s / math.sqrt(n)
    return mean - half, mean + half


def welch_test(a: list[float], b: list[float]) -> dict:
    na, ma, m2a = welford(a)
    nb, mb, m2b = welford(b)
    if na < 2 or nb < 2:
        return {"p_value": None, "reason": "amostra insuficiente"}
    va, vb = m2a / (na - 1), m2b / (nb - 1)
    se = math.sqrt(va / na + vb / nb)
    if se == 0:
        return {"p_value": 1.0 if ma == mb else 0.0, "t": 0.0, "df": na + nb - 2, "mean_a": ma, "mean_b": mb}
    t = (ma - mb) / se
    df = (va / na + vb / nb) ** 2 / ((va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1))
    p = 2 * (1 - t_cdf(abs(t), df))
    return {"p_value": p, "t": t, "df": df, "mean_a": ma, "mean_b": mb, "lift": (ma - mb) / abs(mb) if mb else None}


def prob_best(arms: dict[str, tuple[int, float, float]], draws: int = 4000, seed: int = 7) -> dict[str, float]:
    """P(cada braço ser o melhor) com posterior aproximada Normal(mean, s²/n)."""
    rng = random.Random(seed)
    params = {}
    for k, (n, mean, m2) in arms.items():
        s = math.sqrt(m2 / (n - 1)) if n > 1 else 1.0
        params[k] = (mean, max(1e-6, s / math.sqrt(max(1, n))))
    wins = dict.fromkeys(arms, 0)
    for _ in range(draws):
        best = max(params, key=lambda k: rng.gauss(*params[k]))
        wins[best] += 1
    return {k: v / draws for k, v in wins.items()}
