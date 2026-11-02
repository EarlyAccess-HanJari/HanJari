"""10~90% 범위 폭·'판단하기 일러요' 조건 실험(11-02). 주 단위 전진 검증(과거 주 학습 → 다음 주 평가).
팔: lite(서비스) / wk(+같은 요일·시각 과거 도착 인원) / wk_full(+수집 이력 피처).
규칙: 지금(폭>20) / 경계만(폭>20 이고 탑승 경계가 범위 안) / 애매만(폭>20 이고 P 가 어려움~여유 기준 사이).
실행: python src/exp_band.py [dataset.csv·calendar.csv·class_starts.csv 폴더]  (서버 data/processed 사본, 기본 레포 data/processed)
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
import eval_days as E
import serve as S
import train as T

if len(sys.argv) > 1:
    T.P, T.DATASET = Path(sys.argv[1]), Path(sys.argv[1]) / "dataset.csv"
FOLDS = [("20261012", "20261018"), ("20261019", "20261025"), ("20261026", "20261101")]
WK = ["wk_y", "wk_sd", "wk_n", "dk_y", "dk_sd"]
NS = [0, 3, 5, 10, 15, 20]


def hist(df):
    t = df.drop_duplicates("trip")[["date", "route", "stop", "weekday", "y", "arrive_time"]].copy()
    hh, mm, _ = t.arrive_time.str.split(":", expand=True).astype(int).T.values
    t["slot"] = (hh * 60 + mm) // 15
    x = pd.concat([t.assign(slot=t.slot + o) for o in (-1, 0, 1)]).assign(y2=lambda v: v.y ** 2, n=1)
    return x.rename(columns={"y": "s", "y2": "s2"})[["date", "route", "stop", "weekday", "slot", "n", "s", "s2"]]


def attach(df, h, keys, loo):
    """(keys, 15분 칸) 과거 평균·표준편차. loo: 그 행의 날짜 몫을 뺀다(학습 행의 자기 정답 누수 방지)."""
    tot = h.groupby(keys + ["slot"], observed=True)[["n", "s", "s2"]].sum().reset_index()
    m = df[keys + ["slot", "date"]].merge(tot, on=keys + ["slot"], how="left")
    if loo:
        day = h.groupby(keys + ["slot", "date"], observed=True)[["n", "s", "s2"]].sum().reset_index().rename(columns={"n": "dn", "s": "ds", "s2": "ds2"})
        m = m.merge(day, on=keys + ["slot", "date"], how="left").fillna({"dn": 0, "ds": 0, "ds2": 0})
        m["n"], m["s"], m["s2"] = m.n - m.dn, m.s - m.ds, m.s2 - m.ds2
    n = m.n.where(m.n > 0).values
    mean = m.s.values / n
    return mean, np.sqrt(np.maximum(m.s2.values / n - mean ** 2, 0)), m.n.fillna(0).values


def add(df, h, loo):
    df = df.assign(slot=((df.minute + df.eta.fillna(0) / 60) // 15).astype(int))
    a, b, c = attach(df, h, ["route", "stop", "weekday"], loo)
    e, f, _ = attach(df, h, ["route", "stop"], loo)
    return df.assign(wk_y=a, wk_sd=b, wk_n=c, dk_y=e, dk_sd=f)


d = T.features()
d = d[~d.holiday & (d.weekday != "일") & (d.date <= FOLDS[-1][1])].assign(rule=lambda x: S.lite_rule(x))
ARMS = {"lite": S.LITE, "wk": S.LITE + WK, "wk_full": S.FULL + WK}
out = []
for a, b in FOLDS:
    tr0, te0 = d[d.date < a], d[(d.date >= a) & (d.date <= b)]
    h = hist(tr0)
    tr, te = add(tr0, h, True), add(te0, h, False)
    E.setcap(tr)
    thr = T.thresholds(te)
    for arm, feats in ARMS.items():
        m = T.fit(tr, feats)
        point, Pm, Q = T.predict(m, te, quantiles=True)
        qs = np.asarray(m["qs"])
        r = te[["stop", "stops_away", "is_peak", "minute", "y", "w"]].copy()
        r["arm"], r["point"] = arm, point
        r["q10"], r["q90"] = zip(*[np.interp([0.1, 0.9], qs, q) for q in Q])
        for n in NS:
            r[f"P{n}"], r[f"T{n}"] = Pm[:, n], thr[:, n]
        out.append(r)
        print(a, arm, flush=True)
r = pd.concat(out)
r["width"], r["ae"] = r.q90 - r.q10, (r.point - r.y).abs()
r["hit"] = (r.y >= r.q10) & (r.y <= r.q90)
wm = lambda v, w: float(np.average(v, weights=w)) if len(v) else np.nan
print(r.groupby("arm", sort=False).apply(lambda g: pd.Series(dict(오차=wm(g.ae, g.w), 폭=wm(g.width, g.w), 폭20초과=(g.width > 20).mean(), 적중=wm(g.hit, g.w))), include_groups=False).round(3).to_string())

meta = json.loads((S.MODELS / "lite" / "meta.json").read_text())
th = {(p, s): t for p, s, t, _ in meta["thresholds"]}
x = r[r.arm == "lite"]
t = np.array([th[("수업 직전" if pk == 1 else "평소", S.seg_name(k))] or 9 for pk, k in zip(x.is_peak, x.stops_away)])
rows = []
for n in NS:
    P, L = x[f"P{n}"].values, x[f"T{n}"].values
    wide, board = (x.width > S.WIDE).values, x.y.values <= L
    for name, hold in (("지금", wide), ("경계만", wide & (x.q10.values <= L) & (L < x.q90.values)), ("애매만", wide & (P > S.HARD) & (P < t))):
        yeo = ~hold & (P >= t)
        rows.append(dict(N=n, 규칙=name, 보류=hold.mean(), 보류8시=hold[(x.minute.values // 60) == 8].mean(), 여유표시=yeo.mean(),
                         여유탑승=wm(board[yeo], x.w.values[yeo]), 새여유탑승=wm(board[yeo & wide], x.w.values[yeo & wide])))
print(pd.DataFrame(rows).round(3).to_string(index=False))
