"""MAE 2명 이하로 갈 수 있나 — 바닥 오차(포아송) + 강화 후보 (라이트 모델 기준).

바닥: 남은 정류장 j 의 승차·하차가 서로 독립 포아송이라면 도착 재차의 분산 = Σ_j (승차_j + 하차_j)(CSV 시간대 평균).
      정규 근사로 MAE 바닥 ≈ 0.80 × √분산. 실제론 몰림(과분산) 때문에 더 높다 → 이 값은 **낙관적 하한**.
후보: (a) 평일만 학습 (b) 같은 시각 실측: 이전 평일들에서 같은 정류장에 ±5분 안에 도착한 버스의 실제 재차 평균·최대·개수
평가: 평일 날짜 분할 4폴드(9/28·9/29·9/30·10/1 오전) — 각 날짜 이전·이후 다른 평일로 학습, 같은 시각 실측은 그 날짜 이전 평일만.
"""
import numpy as np, pandas as pd
import build_dataset as B
import serve as S
import train as T
import eval_days as E

WEEKDAYS = ["20260923", "20260928", "20260929", "20260930", "20261001"]
d = T.features()
d = d.assign(rule=S.lite_rule(d))
d["arr_min"] = d.minute + d.eta / 60

# (b) 같은 시각 실측 — 조회 행의 예상 도착 시각 ±5분, 같은 노선·정류장, 그 날짜 이전 평일
trips = d.groupby("trip").agg(date=("date", "first"), route=("route", "first"), stop=("stop", "first"),
                              y=("y", "first"), at=("arrive_time", "first")).reset_index()
trips["at_min"] = trips["at"].str[:2].astype(int) * 60 + trips["at"].str[3:5].astype(int)
trips = trips[trips.date.isin(WEEKDAYS)]
feat = np.full((len(d), 3), np.nan)
for (r, s), idx in d.groupby(["route", "stop"]).groups.items():
    tp = trips[(trips.route == r) & (trips.stop == s)]
    rows = d.loc[idx]
    for i, (dt_, am) in zip(idx, zip(rows.date.values, rows.arr_min.values)):
        m = tp[(tp.date < dt_) & (np.abs(tp.at_min - am) <= 5)]
        if len(m):
            feat[d.index.get_loc(i)] = (m.y.mean(), m.y.max(), len(m))
d[["slot_y", "slot_max", "slot_n"]] = feat
d["slot_inc"] = d.slot_y - d.r_now      # 같은 시각엔 지금보다 몇 명 더 차 있었나
SLOT = ["slot_y", "slot_max", "slot_n", "slot_inc"]

# 바닥 오차
tabs = {r: B.csv_tables(r) for r in B.STOPS}
var = []
for r, s, k, mi in zip(d.route, d.stop.astype(int), d.stops_away, d.minute):
    h = int(mi // 60)
    v = sum((lambda net, off: max(net + off, 0) + off)(*tabs[r].get((j, h), (0, 0))) for j in range(s - k, s))
    var.append(v)
d["floor"] = 0.80 * np.sqrt(np.array(var))

wd = d[d.date.isin(WEEKDAYS)]
FOLDS = [(day, wd[wd.date != day], wd[wd.date == day]) for day in WEEKDAYS[1:]]
ARMS = {"라이트(지금)": (S.LITE, False), "(a) 평일만": (S.LITE, True),
        "(b) +같은 시각 실측": (S.LITE + SLOT, False), "(c) 평일만+같은 시각": (S.LITE + SLOT, True)}
seg = lambda k: pd.cut(k, [-1, 0, 2, 5, 99], labels=["바로 앞", "1~2", "3~5", "6+"])
rows = []
for day, tr_wd, te in FOLDS:
    tr_all = d[d.date != day]
    for arm, (feats, weekday_only) in ARMS.items():
        tr = tr_wd if weekday_only else tr_all
        E.setcap(tr)
        p, Pm = T.run(tr, te, feats)
        m = T.metrics(p, Pm, te)
        err, w = np.abs(p - te.y.values), te.w.values
        row = dict(평가=day, 팔=arm, MAE=m["mae"], Brier=m["brier"], 여유=m["hi_ok"])
        for name, msk in te.groupby(seg(te.stops_away.values), observed=False).indices.items():
            row[name] = np.average(err[msk], weights=w[msk])
        pk = te.is_peak.values == 1
        row["수업직전"] = np.average(err[pk], weights=w[pk]) if pk.any() else np.nan
        rows.append(row)
    print("done", day, flush=True)
r = pd.DataFrame(rows)
with pd.option_context("display.width", 220, "display.float_format", "{:.3f}".format):
    print(r.pivot(index="팔", columns="평가", values="MAE"))
    print(r.groupby("팔", sort=False)[["MAE", "Brier", "여유", "바로 앞", "1~2", "3~5", "6+", "수업직전"]].mean())
    fl = wd.groupby(seg(wd.stops_away.values), observed=False).apply(lambda g: np.average(g.floor, weights=g.w))
    print("\n포아송 바닥(낙관적 하한) 거리별:", fl.round(2).to_dict(), "| 전체", round(np.average(wd.floor, weights=wd.w), 2))
    sh = wd.groupby(seg(wd.stops_away.values), observed=False).w.sum() / wd.w.sum()
    print("거리별 행 비중(운행 가중):", sh.round(3).to_dict())
