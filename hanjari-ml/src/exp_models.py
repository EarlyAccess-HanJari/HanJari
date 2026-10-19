"""모델 계열·앵커·새 피처 비교. 평일만, 날짜 분할 3폴드. 바로 앞(k=0)은 모든 팔에서 기존 규칙 모델 그대로."""
import sys, numpy as np, pandas as pd, xgboost as xgb, lightgbm as lgb, catboost as cb
sys.path.insert(0, "/data/VI001/vi004/workspace/PROJECTS/hanjari/hanjari-ai/src")
import train as T, eval_days as E

d = T.features()
d = d[d.date.astype(str).isin(["20260923", "20260928", "20260929", "20260930"])].copy()

# 새 피처: 같은 정류장에 이미 도착한 앞 버스들의 실제 도착재차(y)와 그 버스들의 규칙 오차 — 조회 시각보다 먼저 도착한 것만
d["res_"] = d.y - d.rule
g = d.groupby(["date", "route", "stop", "trip"]).agg(at=("arrive_time", "first"), yy=("y", "first"), rr=("res_", "mean")).reset_index().sort_values("at")
out = []
for (dt_, r, s), part in d.groupby(["date", "route", "stop"]):
    a = g[(g.date == dt_) & (g.route == r) & (g.stop == s)]
    idx = np.searchsorted(a["at"].values, part["time"].values, side="left")  # at < time 인 것만
    yy, rr, at = a.yy.values, a.rr.values, a["at"].values
    def f(i):
        if i == 0:
            return (np.nan, np.nan, np.nan)
        lo = max(0, i - 3)
        t0 = pd.to_timedelta(at[i - 1]).total_seconds()
        return (yy[i - 1], rr[lo:i].mean(), t0)
    v = np.array([f(i) for i in idx], dtype=float)
    tq = pd.to_timedelta(part["time"]).dt.total_seconds().values
    out.append(pd.DataFrame({"prev_y": v[:, 0], "prev_res3": v[:, 1], "prev_age": (tq - v[:, 2]) / 60}, index=part.index))
d = d.join(pd.concat(out))
d = d.drop(columns="res_")
assert (d.prev_age.dropna() > 0).all(), "누수: 조회 시각 이후 도착한 버스를 씀"

FEATS = sum(T.GROUPS.values(), [])
NEW = ["prev_y", "prev_res3", "prev_age"]
QS = T.QS
D5 = dict(T.XGB_KW, max_depth=5, n_estimators=600, learning_rate=0.03)


def fit_xgb(Xtr, t, w, Xte, kw):
    p = xgb.XGBRegressor(objective="reg:absoluteerror", **kw).fit(Xtr, t, sample_weight=w).predict(Xte)
    q = xgb.XGBRegressor(objective="reg:quantileerror", quantile_alpha=QS, **kw).fit(Xtr, t, sample_weight=w).predict(Xte)
    return p, q


def fit_lgb(Xtr, t, w, Xte):
    kw = dict(n_estimators=600, learning_rate=0.03, num_leaves=31, min_child_samples=20, subsample=0.8, subsample_freq=1, n_jobs=8, verbose=-1, random_state=0)
    p = lgb.LGBMRegressor(objective="l1", **kw).fit(Xtr, t, sample_weight=w).predict(Xte)
    q = np.stack([lgb.LGBMRegressor(objective="quantile", alpha=a, **kw).fit(Xtr, t, sample_weight=w).predict(Xte) for a in QS], 1)
    return p, q


def fit_cb(Xtr, t, w, Xte):
    kw = dict(iterations=800, learning_rate=0.05, depth=6, thread_count=8, verbose=0, random_seed=0)
    p = cb.CatBoostRegressor(loss_function="MAE", **kw).fit(Xtr, t, sample_weight=w).predict(Xte)
    q = cb.CatBoostRegressor(loss_function="MultiQuantile:alpha=" + ",".join(map(str, QS)), **kw).fit(Xtr, t, sample_weight=w).predict(Xte)
    return p, q


def finish(te, anchor, p, q, base_point, base_Pm):
    cap_te = np.array([T.cap(r, b) for r, b in zip(te.route, te.bus_type)])
    point = np.clip(anchor + p, 0, cap_te)
    Pm = T.quantile_p(np.clip(np.sort(q, 1) + anchor[:, None], 0, cap_te[:, None]), T.thresholds(te))
    k0 = te.stops_away.values == 0
    point[k0], Pm[k0] = base_point[k0], base_Pm[k0]
    return point, Pm


FOLDS = [(["20260923", "20260929", "20260930"], "20260928"),
         (["20260923", "20260928"], "20260929"),
         (["20260923", "20260928", "20260929"], "20260930")]
rows = []
for trd, ted in FOLDS:
    tr, te = d[d.date.astype(str).isin(trd)], d[d.date.astype(str) == ted]
    E.setcap(tr)
    T.XGB_KW = dict(D5)
    bp, bP = T.run(tr, te, FEATS)  # 깊이5 기준 (k=0 포함)
    peak = te.time.between("07:00", "11:00").values
    arms = {}
    per = te.r_now.values
    arms["persistence"] = (per, (per[:, None] <= T.thresholds(te)).astype(float))
    T.XGB_KW = dict(T.XGB_KW, max_depth=2, n_estimators=400, learning_rate=0.02)
    arms["XGB 깊이2 (현행)"] = T.run(tr, te, FEATS)
    arms["XGB 깊이5"] = (bp, bP)
    for name, feats in [("", FEATS), (" +앞버스실측", FEATS + NEW)]:
        Xtr, Xte = tr[feats].astype(float), te[feats].astype(float)
        t, w = tr.y.values - tr.rule.values, tr.w.values
        res = {}
        if name:
            res["XGB 깊이5"] = fit_xgb(Xtr, t, w, Xte, D5)
        res["LightGBM"] = fit_lgb(Xtr, t, w, Xte)
        res["CatBoost"] = fit_cb(Xtr, t, w, Xte)
        if not name:
            res["XGB 깊이5"] = fit_xgb(Xtr, t, w, Xte, D5)
        for k, (p, q) in res.items():
            if k == "XGB 깊이5" and not name:
                continue
            arms[k + name] = finish(te, te.rule.values, p, q, bp, bP)
        ens_p = np.mean([v[0] for v in res.values()], 0)
        ens_q = np.mean([np.sort(v[1], 1) for v in res.values()], 0)
        arms["앙상블(XGB+LGB+CB)" + name] = finish(te, te.rule.values, ens_p, ens_q, bp, bP)
    # 앵커 바꾸기: 규칙 대신 지금 재차 / 앵커 없음(0)
    Xtr, Xte = tr[FEATS].astype(float), te[FEATS].astype(float)
    for nm, a_tr, a_te in [("앵커=지금재차", tr.r_now.values, te.r_now.values), ("앵커 없음", 0 * tr.r_now.values, 0 * te.r_now.values)]:
        p, q = fit_xgb(Xtr, tr.y.values - a_tr, tr.w.values, Xte, D5)
        arms["XGB 깊이5 " + nm] = finish(te, a_te.astype(float), p, q, bp, bP)
    for k, (p, Pm) in arms.items():
        m = T.metrics(p, Pm, te)
        far = te.stops_away.values >= 3
        rows.append(dict(fold=ted, arm=k, MAE=m["mae"], Brier=m["brier"], 여유=m["hi_ok"], 여유비율=m["hi_share"],
                         피크MAE=np.average(np.abs(p - te.y.values)[peak], weights=te.w.values[peak]) if peak.any() else np.nan,
                         원거리MAE=np.average(np.abs(p - te.y.values)[far], weights=te.w.values[far])))
    print("done", ted, flush=True)

r = pd.DataFrame(rows)
r.to_csv("/tmp/claude-1001/-data-VI001-vi004-workspace/0458027c-0541-4423-8704-89c234a62b73/scratchpad/exp_models.csv", index=False)
with pd.option_context("display.width", 200, "display.float_format", "{:.4f}".format):
    print(r.pivot(index="arm", columns="fold", values="MAE"))
    print(r.groupby("arm", sort=False)[["MAE", "Brier", "여유", "여유비율", "피크MAE", "원거리MAE"]].mean().sort_values("MAE"))
