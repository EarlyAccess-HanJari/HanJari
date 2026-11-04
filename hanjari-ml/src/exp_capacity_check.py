"""정원(만차 인원)으로 낸 확률이 실제 정류장 사건과 맞는지 — 과거로 학습, 이후 날짜로 확인(11-04).
python src/exp_capacity_check.py <api_logs 폴더> <검증용 모델 폴더(export until=CUT)> CUT

라벨(API 인원 변화로 판정, 현장 계수 아님):
  탔음(N)  : 그 정류장에서 N+1 명 넘게 늘어남 → 앞에 N 명이 있어도 탈 자리가 있었다
  못 탐    : 정원-5 명 이상으로 도착해 1명 이하만 늘어남 → 꽉 차서 못 탐
각 사건의 1정류장 전 마지막 조회로 낸 확률·안내를 본다.
"""
import json, sys
import numpy as np, pandas as pd
import exp_practical_capacity as X
import serve as S
import train as T

ROOT, MDIR, CUT = sys.argv[1:4]
X.ROOT = ROOT


def main():
    import os, re
    from multiprocessing import Pool
    days = sorted(x for x in os.listdir(ROOT) if re.fullmatch(r"2026\d{4}", x) and x > CUT)
    with Pool(min(16, os.cpu_count() or 1)) as pool:
        rows = [r for part in pool.map(X.day, [(d, r) for d in days for r in X.BUSY]) for r in part]
    m = pd.DataFrame(rows, columns=["date", "route", "t", "plate", "bt", "sect", "n"])
    m["sec"] = pd.to_datetime(m.date + m.t, format="%Y%m%d%H%M%S")
    ev = X.events(m)
    ev["h"], ev["net"] = ev.sec.dt.hour + ev.sec.dt.minute / 60, ev.after - ev.before
    busy = np.zeros(len(ev), bool)
    for r, spec in X.BUSY.items():
        for stop, a, b in spec:
            busy |= (ev.route == r).values & (ev.stop == stop).values & ev.h.between(a, b).values
    ev = ev[busy].copy()
    model, meta = S.load(True, MDIR)
    th = {(p, s): t for p, s, t, _ in meta["thresholds"]}
    d = T.features(cats=meta["cats"])
    d = d[(d.date > CUT) & ~d.holiday & (d.weekday != "일") & (d.stops_away == 1)].assign(rule=lambda x: S.lite_rule(x))
    d["qsec"] = pd.to_datetime(d.date + d.time, format="%Y%m%d%H:%M:%S")
    # 사건마다 같은 노선·정류장·차량의 도착 전 10분 안 마지막 1정류장 전 조회
    d = d.sort_values("qsec"); ev = ev.sort_values("sec")
    j = pd.merge_asof(ev, d, left_on="sec", right_on="qsec", by=["route", "stop", "plate"], direction="backward",
                      tolerance=pd.Timedelta(minutes=10), suffixes=("", "_q")).dropna(subset=["qsec"])
    j = j.reset_index(drop=True)
    _, Pm = T.predict(model, j)
    cap = T.row_capacities(j)
    t = np.array([th.get(("수업 직전" if pk == 1 else "평소", S.seg_name(k))) or 9 for pk, k in zip(j.is_peak, j.stops_away)])
    out = {"cut": CUT, "days": days, "events": int(len(ev)), "matched": int(len(j)), "by_n": {}}
    stuck = (j.before >= cap - 5) & (j.net <= 1)
    for n in (0, 1, 3, 5):
        P = Pm[:, n]
        ok = j.net.values >= n + 1
        lv = np.where(P >= t, "여유", np.where(P <= S.HARD, "어려움", "빠듯"))
        out["by_n"][n] = {
            "탔음": int(ok.sum()), "못탐": int(stuck.sum()),
            "탔음_평균P": round(float(P[ok].mean()), 3) if ok.any() else None,
            "못탐_평균P": round(float(P[stuck].mean()), 3) if stuck.any() else None,
            "못탐인데_여유": round(float((lv[stuck] == "여유").mean()), 3) if stuck.any() else None,
            "못탐_어려움": round(float((lv[stuck] == "어려움").mean()), 3) if stuck.any() else None,
            "탔음인데_어려움": round(float((lv[ok] == "어려움").mean()), 3) if ok.any() else None,
            "탔음_여유": round(float((lv[ok] == "여유").mean()), 3) if ok.any() else None}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return out


if __name__ == "__main__":
    main()
