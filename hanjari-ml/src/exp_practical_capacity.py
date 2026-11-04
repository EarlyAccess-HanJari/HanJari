"""실제 만차 인원(정원) 근거 — 원본 수집 로그만으로 다시 계산한다(11-04).
python src/exp_practical_capacity.py <api_logs 폴더(날짜별)> [출력 json]

1. 정류장 사건: 차량마다 위치 API 구간(sectOrd)이 s-1 → s 로 넘어갈 때, s-1 구간 마지막 인원 = s 도착 인원(before),
   s 구간 마지막 인원 = s 출발 인원(after). 재차는 정류장을 떠날 때 갱신되므로 after-before 가 s 에서의 순증감.
2. 만차 인원: 평일 혼잡 시간·붐비는 정류장을 떠날 때 인원 상위 1%, 도착 인원별 '1명 이하만 늘어난' 비율.
3. 카운터 누적 점검: 종점 출발 직후(구간 1~2, 거의 빈 차여야 함) 차량별 인원.
API 인원 기준이다(현장 계수 아님). 공공 카드 자료의 미태그 하차는 승객의 약 2%(README·PRACTICAL_CAPACITY 문서).
"""
import glob, json, os, re, sys
from multiprocessing import Pool
import numpy as np, pandas as pd

ROOT = sys.argv[1]
CAL = os.path.join(os.path.dirname(__file__), "../data/processed/calendar.csv")
BUSY = {  # (노선, 정류장, 시간 구간) — 평소 증가가 큰 곳·때
    "sb02": [("31", 7.75, 9.25), ("32", 7.75, 9.25), ("32", 11.0, 12.0)],
    "jr03": [("19", 17.0, 19.5), ("20", 17.0, 19.5), ("19", 8.0, 9.5), ("20", 8.0, 9.5)],
}


def items(path):
    try:
        a = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return []
    x = a.get("msgBody", a).get("itemList", []) if isinstance(a, dict) else a
    return x if isinstance(x, list) else ([x] if x else [])


def day(args):
    d, route = args
    load, pos = {}, []
    for f in sorted(glob.glob(f"{ROOT}/{d}/{route}_arr_*.json")):
        t = re.search(r"_(\d{6})\.json", f).group(1)
        for it in items(f):
            p = (it.get("plainNo1") or "").strip()
            if p and it.get("rerdie_Div1") == "2":
                load[(t, p)] = (max(load.get((t, p), (0, ""))[0], int(it.get("reride_Num1") or 0)), it.get("busType1"))
        g = f.replace("_arr_", "_pos_")
        for v in items(g) if os.path.exists(g) else []:
            p = (v.get("plainNo") or "").strip()
            if (t, p) in load:
                pos.append((d, route, t, p, load[(t, p)][1], int(v.get("sectOrd") or 0), load[(t, p)][0]))
    return pos


def events(m):
    out = []
    for (r, p), x in m.groupby(["route", "plate"], sort=False):
        x = x.sort_values("sec")
        s, n, sec, bt = x.sect.values, x.n.values, x.sec.values, x.bt.values
        brk = np.r_[0, np.flatnonzero(s[1:] != s[:-1]) + 1, len(x)]  # 같은 구간이 이어지는 묶음
        runs = [(s[a], n[b - 1], sec[a], sec[b - 1], bt[a]) for a, b in zip(brk[:-1], brk[1:])]
        for (s0, n0, _, t0, b0), (s1, n1, t1a, _, _) in zip(runs[:-1], runs[1:]):
            if s1 == s0 + 1 and (t1a - t0) <= np.timedelta64(10, "m"):
                out.append((r, p, b0, str(s1), t1a, n0, n1))
    return pd.DataFrame(out, columns=["route", "plate", "bt", "stop", "sec", "before", "after"])


def main():
    days = sorted(x for x in os.listdir(ROOT) if re.fullmatch(r"2026\d{4}", x))
    with Pool(min(16, os.cpu_count() or 1)) as pool:
        rows = [r for part in pool.map(day, [(d, r) for d in days for r in BUSY]) for r in part]
    m = pd.DataFrame(rows, columns=["date", "route", "t", "plate", "bt", "sect", "n"])
    m["sec"] = pd.to_datetime(m.date + m.t, format="%Y%m%d%H%M%S")
    cal = pd.read_csv(CAL, dtype=str)
    off = set(cal[(cal.holiday.fillna("") != "") | (cal.weekday == "일")].date)
    ev = events(m)
    ev = ev[~ev.sec.dt.strftime("%Y%m%d").isin(off)]
    ev["h"], ev["net"] = ev.sec.dt.hour + ev.sec.dt.minute / 60, ev.after - ev.before
    busy = np.zeros(len(ev), bool)
    for r, spec in BUSY.items():
        for stop, a, b in spec:
            busy |= (ev.route == r).values & (ev.stop == stop).values & ev.h.between(a, b).values
    res = {"days": days, "events": int(len(ev)), "busy_events": int(busy.sum()), "groups": {}}
    for (r, bt), g in ev[busy].groupby(["route", "bt"]):
        bins = pd.cut(g.before, [-1, 9, 14, 19, 24, 29, 34, 39, 44, 49, 54, 59, 99])
        res["groups"][f"{r}/{bt}"] = {
            "busy_events": int(len(g)), "after_p99": float(g.after.quantile(.99)), "before_max": int(g.before.max()),
            "le1_by_before": {str(k): [int(len(v)), round(float((v.net <= 1).mean()), 3), round(float(v.net.mean()), 2)]
                              for k, v in g.groupby(bins, observed=True) if len(v) >= 5}}
    term = m[m.sect.isin([1, 2])].groupby(["route", "bt", "plate"]).n
    res["post_terminal"] = {f"{r}/{bt}/{p}": [int(v.size), round(float(v.mean()), 2), int(v.max())] for (r, bt, p), v in term}
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), "../reports/practical_capacity_20261104.json")
    open(out, "w", encoding="utf-8").write(json.dumps(res, ensure_ascii=False, indent=1))
    for k, v in res["groups"].items():
        print(k, "혼잡 사건", v["busy_events"], "| 출발 인원 상위 1%", v["after_p99"], "| 도착 최대", v["before_max"])
        print("   도착 인원별 [사건, 1명 이하 비율, 평균 증가]:", v["le1_by_before"])
    print("종점 직후 차량별 [기록, 평균, 최대]:", res["post_terminal"])


if __name__ == "__main__":
    main()
