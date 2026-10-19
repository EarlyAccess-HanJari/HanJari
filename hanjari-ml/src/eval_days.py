"""날짜 기준 평가(서비스와 같은 '처음 보는 시간' 예측).

분할 A: 마지막 날 이전 전체 → 마지막 날 전체
분할 B: 마지막 날 12시 이전까지 전부 → 마지막 날 12시 이후
표: persistence / 규칙 / XGB(피처 묶음 누적) 의 MAE·Brier·'여유'→탑승, 거리별 MAE.
실행: env -u PYTHONPATH /data/VI001/vi004/workspace/miniconda3/envs/dacon/bin/python src/eval_days.py
"""
import numpy as np
import pandas as pd
import train as T


def setcap(tr):
    T.CAP_OBS.clear()
    T.CAP_OBS.update(pd.concat([tr.y, tr.r_now]).groupby(pd.concat([tr.route + "|" + tr.bus_type] * 2)).max()
                     .rename(lambda k: tuple(k.split("|"))).to_dict())


def evaluate(tr, te, title):
    setcap(tr)
    thr = T.thresholds(te)
    rows, preds = [], {}
    rows.append(("persistence", T.metrics(te.r_now.values, (te.r_now.values[:, None] <= thr).astype(float), te)))
    preds["persistence"] = te.r_now.values
    rows.append(("규칙+잔차", T.metrics(te.rule.values, T.empirical_p(tr.y.values - tr.rule.values, te.rule.values, thr), te)))
    preds["규칙"] = te.rule.values
    feats = []
    for g, cols in T.GROUPS.items():
        feats = feats + cols
        p, Pm = T.run(tr, te, feats)
        rows.append((f"XGB {g}", T.metrics(p, Pm, te)))
        preds[f"XGB {g}"] = p
    r = pd.DataFrame([dict(model=m, **v) for m, v in rows]).set_index("model")
    r.columns = ["MAE", "Brier", "'여유'비율", "'여유'→탑승", "'어려움'→탑승"]
    seg = pd.cut(te.stops_away, [-1, 0, 2, 99], labels=["바로앞", "1~2", "3+"]).values
    for k, p in preds.items():
        for sname in ["바로앞", "1~2", "3+"]:
            m = seg == sname
            r.loc[k, sname] = np.average(np.abs(p[m] - te.y.values[m]), weights=te.w.values[m]) if m.any() else np.nan
    print(f"\n=== {title} | 학습 {tr.trip.nunique()}운행 / 평가 {te.trip.nunique()}운행 ===")
    with pd.option_context("display.width", 200, "display.float_format", "{:.3f}".format):
        print(r.to_string())
    return r


def main():
    d = T.features()
    days = sorted(d.date.unique())
    last = d[d.date == days[-1]]
    a = evaluate(d[d.date < days[-1]], last, f"A. ~{days[-2]} → {days[-1]} 전체")
    pm = last.time >= "12:00"
    if pm.sum() < 100:  # 마지막 날 오후가 아직 없으면 B 는 건너뜀
        print(f"\n(B 생략: {days[-1]} 12시 이후 {pm.sum()}행)")
        return a, None
    b = evaluate(pd.concat([d[d.date < days[-1]], last[~pm]]), last[pm], f"B. ~{days[-1]} 오전 → {days[-1]} 오후")
    return a, b


if __name__ == "__main__":
    main()
