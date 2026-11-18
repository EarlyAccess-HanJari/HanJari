"""만차 인원 재산출(11-17) — 정류장 출발 뒤 인원을 출발 35초 이후 첫 관측으로 잡아 정류장별 순승차를 계산한다.
짧은 구간(2번출구→녹십자 약 30초)에서도 인원 반영 지연(약 27초) 때문에 한 칸 밀리지 않는다. 결과: docs/PRACTICAL_CAPACITY_20261117.md
python src/exp_capacity_aligned.py <api_logs 폴더> <출력 pkl>"""
import glob, json, os, re, sys, datetime as dt
from multiprocessing import Pool
import numpy as np, pandas as pd
ROOT, OUT = sys.argv[1], sys.argv[2]

def items(p):
    try:
        a = json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return []
    x = (a.get("msgBody") or {}).get("itemList") if isinstance(a, dict) else None
    return x if isinstance(x, list) else ([x] if x else [])

def day(args):
    d, route = args
    pos, cnt = [], []
    for f in sorted(glob.glob(f"{ROOT}/{d}/{route}_pos_*.json")):
        t = dt.datetime.strptime(d + re.search(r"_(\d{6})\.json", f).group(1), "%Y%m%d%H%M%S")
        for v in items(f):
            if v.get("plainNo"):
                pos.append((v["plainNo"].strip(), str(v.get("vehId")), t, int(v.get("sectOrd") or 0), int(v.get("stopFlag") or 0)))
        g = f.replace("_pos_", "_arr_")
        if os.path.exists(g):
            seen = {}
            for it in items(g):
                for i in "12":
                    p, r = (it.get("plainNo" + i) or "").strip(), it.get("reride_Num" + i)
                    if p and it.get("rerdie_Div" + i) == "2" and r not in (None, "") and str(it.get("vehId" + i)):
                        seen[p] = (int(r), it.get("busType" + i))
            cnt += [(p, t, r, bt) for p, (r, bt) in seen.items()]
    P = pd.DataFrame(pos, columns=["plate", "veh", "t", "sect", "flag"])
    C = pd.DataFrame(cnt, columns=["plate", "t", "n", "bt"])
    out = []
    for plate, g in P.groupby("plate"):
        g = g.sort_values("t")
        c = C[C.plate == plate].sort_values("t")
        if c.empty:
            continue
        ct, cn, cb = c.t.values, c.n.values, c.bt.values
        # 출발: 구간 j 를 '달리는 중'(flag 0)으로 처음 본 시각(직전 관측이 j 가 아니거나 j 정차)
        s, f, t = g.sect.values, g.flag.values, g.t.values
        deps = []
        for i in range(1, len(g)):
            if f[i] == 0 and (s[i - 1] != s[i] or f[i - 1] == 1) and (t[i] - t[i - 1]) <= np.timedelta64(120, "s"):
                deps.append((s[i], t[i]))
        for k, (j, tj) in enumerate(deps):
            nxt = deps[k + 1][1] if k + 1 < len(deps) else tj + np.timedelta64(600, "s")
            lo, hi = tj + np.timedelta64(35, "s"), min(nxt + np.timedelta64(20, "s"), tj + np.timedelta64(150, "s"))
            m = (ct >= lo) & (ct <= hi)
            if m.any():
                i0 = np.flatnonzero(m)[0]
                out.append((d, route, plate, cb[i0], j, pd.Timestamp(tj), int(cn[i0])))
    return out

days = sorted(x for x in os.listdir(ROOT) if re.fullmatch(r"2026\d{4}", x))
with Pool(32) as pool:
    rows = [r for part in pool.map(day, [(d, r) for d in days for r in ("sb02", "jr03")]) for r in part]
e = pd.DataFrame(rows, columns=["date", "route", "plate", "bt", "stop", "dep", "after"])
e = e.sort_values(["route", "plate", "dep"])
g = e.groupby(["route", "plate"])
e["prev_stop"], e["prev_after"], e["prev_dep"] = g.stop.shift(), g["after"].shift(), g.dep.shift()
e = e[(e.prev_stop == e.stop - 1) & ((e.dep - e.prev_dep) <= pd.Timedelta(minutes=10))].copy()
e["before"], e["net"] = e.prev_after, e["after"] - e.prev_after
e.to_pickle(OUT)
print("사건", len(e), "날짜", len(days))
