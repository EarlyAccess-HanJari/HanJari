"""P(탑승) 규칙 — 단계 0(CSV 기준 모델).

남은 자리 = C − (도착 재차 − 하차) 이고, 내 앞 N명이 먼저 타므로
탑승 ⇔ 순재차 X = 도착재차 − 하차 ≤ C − N − 1.
X ~ Poisson(평균)  # ponytail: 분산=평균 가정. 실측 로그가 쌓이면 경험분포/분위수 회귀로 교체.
평균 = 실시간 재차(r_now)가 있으면 r_now − 하차평균, 없으면 CSV 기준 모델(baseline_csv.csv) 값.
"""
import csv, math
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "data/processed/baseline_csv.csv"
CAPACITY = {0: 33, 1: 55}  # busType 0=작은 차, 1=큰 차(추정). 법정+10 잠정값, docs/DESIGN.md 2절
STOPS = {30: "5번출구", 31: "2번출구", 32: "녹십자약국"}

_mean = None


def baseline(stop, term, hour):
    """(도착재차 평균, 하차 평균): 같은 학기구분·시간대 월별 값의 평균."""
    global _mean
    if _mean is None:
        g = defaultdict(list)
        for r in csv.DictReader(open(BASE)):
            g[(r["stop"], r["term"], int(r["hour"]))].append((float(r["load"]), float(r["off"])))
        _mean = {k: tuple(sum(x) / len(v) for x in zip(*v)) for k, v in g.items()}
    return _mean[(STOPS[stop], term, hour)]


def poisson_cdf(k, lam):
    if k < 0:
        return 0.0
    lam = max(lam, 1e-9)
    term = total = math.exp(-lam)
    for i in range(1, k + 1):
        term *= lam / i
        total += term
    return min(total, 1.0)


def p_board(stop, term, hour, n_ahead, bus_type=0, r_now=None):
    load, off = baseline(stop, term, hour)
    lam = max((r_now if r_now is not None else load) - off, 0.0)
    return poisson_cdf(CAPACITY[bus_type] - n_ahead - 1, lam)


if __name__ == "__main__":
    # 자체 점검
    assert abs(poisson_cdf(0, 2.0) - math.exp(-2)) < 1e-12
    assert p_board(31, "학기", 8, 0) > p_board(31, "학기", 8, 30)            # 앞사람 많으면 확률↓
    assert p_board(31, "학기", 8, 25, r_now=30) < p_board(31, "학기", 8, 25)  # 실시간 재차 많으면↓
    assert p_board(31, "학기", 8, 40) == 0.0                                  # 정원 초과 대기는 0
    print("학기 08시, 작은 차(C=33) / 큰 차(C=55) 기준 P(탑승)")
    print("정류장     N=0   10    20    25    30   | 큰차 N=40  50")
    for s, name in STOPS.items():
        row = [p_board(s, "학기", 8, n) for n in (0, 10, 20, 25, 30)]
        big = [p_board(s, "학기", 8, n, bus_type=1) for n in (40, 50)]
        print(f"{name:6} " + " ".join(f"{p:5.2f}" for p in row) + " | " + " ".join(f"{p:5.2f}" for p in big))
    print("\n실시간 재차가 25명일 때 2번출구(작은 차):",
          " ".join(f"N={n}:{p_board(31, '학기', 8, n, r_now=25):.2f}" for n in (0, 3, 5, 8, 10)))
