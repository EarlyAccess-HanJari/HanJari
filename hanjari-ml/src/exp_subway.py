"""지하철 시간표 피처 실험. 버스가 지나갈 중간 정류장 중 지하철역 앞인 곳에 열차가 언제·몇 번 서는지.
시간표: data/raw/subway/서울교통공사_도시철도열차운행시각표_20260914.csv (평일 DAY, 양방향·모든 호선)
평일만, 날짜 3폴드 + 봉인 구간(9/30 10:35~). XGB 깊이5 기준, 피처만 추가.
"""
import numpy as np, pandas as pd
import train as T, eval_days as E

ROOT = T.ROOT if hasattr(T, "ROOT") else __import__("pathlib").Path(__file__).resolve().parents[1]
# 노선 순번 → 그 정류장 앞 지하철역 코드
STATION_STOPS = {"sb02": {30: ["0419"], 31: ["0419"]},
                 "jr03": {19: ["0421", "0155"], 20: ["0159", "2637"], 23: ["2638"]}}

tt = pd.read_csv(ROOT / "data/raw/subway/서울교통공사_도시철도열차운행시각표_20260914.csv", encoding="cp949", dtype=str)
tt = tt[(tt["주중주말"] == "DAY") & tt["역사코드"].isin({c for m in STATION_STOPS.values() for v in m.values() for c in v})]
tt["sec"] = pd.to_timedelta(tt["열차도착시간"].fillna(tt["열차출발시간"])).dt.total_seconds()
TRAINS = {c: np.sort(g.sec.values) for c, g in tt.groupby("역사코드")}


def sub_feats(d):
    t = pd.to_timedelta(d.time).dt.total_seconds().values
    arr = t + d.eta.values.astype(float)
    n10 = np.full(len(d), np.nan); ahead = n10.copy(); last = n10.copy()
    for i, (r, s, k) in enumerate(zip(d.route.values, d.stop.astype(int).values, d.stops_away.astype(int).values)):
        codes = [c for j, cs in STATION_STOPS[r].items() if s - k <= j < s for c in cs]
        if not codes:
            continue
        x = np.concatenate([TRAINS[c] for c in codes])
        n10[i] = ((x >= t[i] - 600) & (x <= arr[i])).sum()     # 최근 10분 ~ 버스 도착까지 선 열차 수
        ahead[i] = ((x > t[i]) & (x <= arr[i])).sum()           # 지금부터 도착까지 (시간표라 미래도 알 수 있음)
        before = x[x <= arr[i]]
        last[i] = (arr[i] - before.max()) / 60 if len(before) else np.nan  # 버스 도착 순간 기준 마지막 열차 후 몇 분
    return pd.DataFrame({"sub_n10": n10, "sub_ahead": ahead, "sub_last": last}, index=d.index)


d = T.features()
d = d[d.date.astype(str).isin(["20260923", "20260928", "20260929", "20260930"])].copy()
d = d.join(sub_feats(d))
NEW = ["sub_n10", "sub_ahead", "sub_last"]
# 지용 09-30: 수업이 없으면 지하철에서 내린 사람이 마을버스를 탈 이유가 없다 → 수업 직전에만 켜기 / 수업 수와 곱하기
for c in NEW:
    d[c + "_pk"] = d[c].where(d.is_peak == 1)
d["sub_n10_x_cls"] = d.sub_n10 * d.class_board_win
d["sub_ahead_x_cls"] = d.sub_ahead * d.class_board_win
PK = [c + "_pk" for c in NEW]
XC = ["sub_n10_x_cls", "sub_ahead_x_cls"]
FEATS = sum(T.GROUPS.values(), [])
print("지하철 피처가 있는 행", round(d.sub_n10.notna().mean(), 3))

sealed = (d.date.astype(str) == "20260930") & (d.time > "10:35")
FOLDS = [("9/28", d.date.astype(str).isin(["20260923", "20260929", "20260930"]) & ~sealed, d.date.astype(str) == "20260928"),
         ("9/29", d.date.astype(str).isin(["20260923", "20260928"]), d.date.astype(str) == "20260929"),
         ("9/30 오전", d.date.astype(str).isin(["20260923", "20260928", "20260929"]), (d.date.astype(str) == "20260930") & ~sealed),
         ("봉인 9/30 오후", ~sealed, sealed)]
rows = []
for name, trm, tem in FOLDS:
    tr, te = d[trm], d[tem]
    E.setcap(tr)
    has = te.sub_n10.notna().values
    pk = has & (te.is_peak.values == 1)
    for arm, feats in [("기존", FEATS), ("+지하철", FEATS + NEW), ("+지하철(수업직전만)", FEATS + PK), ("+지하철×수업수", FEATS + XC)]:
        p, Pm = T.run(tr, te, feats)
        m = T.metrics(p, Pm, te)
        err = np.abs(p - te.y.values)
        rows.append(dict(평가=name, 팔=arm, MAE=m["mae"], Brier=m["brier"], 여유=m["hi_ok"],
                         역경유MAE=np.average(err[has], weights=te.w.values[has]), 역경유행=has.sum(),
                         피크역경유MAE=np.average(err[pk], weights=te.w.values[pk]) if pk.any() else np.nan, 피크역경유행=pk.sum()))
    print("done", name, flush=True)
r = pd.DataFrame(rows)
with pd.option_context("display.width", 200, "display.float_format", "{:.4f}".format):
    print(r.to_string(index=False))
    print(r[r.평가 != "봉인 9/30 오후"].groupby("팔")[["MAE", "Brier", "여유", "역경유MAE", "피크역경유MAE"]].mean())
