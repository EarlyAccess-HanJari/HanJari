"""오라클(수집 이력) 없이 API 한 번 호출 결과만으로 예측하는 '라이트' 모델 vs 전체 모델.
라이트 = 지금 스냅샷(도착정보+위치)과 고정 표(CSV 평균·q_hist·달력·수업)로 계산되는 피처만. 규칙도 오늘 실측(q_eb) 대신 CSV.
"""
import numpy as np, pandas as pd
import train as T, eval_days as E

HISTORY = ["since_prev", "hw_ratio", "q_bias3", "q_prev", "q_today", "q_eb", "q_live2", "q_today2", "q_rate", "gap_sum"]
FULL = sum(T.GROUPS.values(), [])
LITE = [f for f in FULL if f not in HISTORY]

d = T.features()
d = d[d.date.isin(["20260923", "20260928", "20260929", "20260930"])].copy()
sealed = (d.date == "20260930") & (d.time > "10:35")
FOLDS = [("9/28", d.date.isin(["20260923", "20260929", "20260930"]) & ~sealed, d.date == "20260928"),
         ("9/29", d.date.isin(["20260923", "20260928"]), d.date == "20260929"),
         ("9/30 오전", d.date.isin(["20260923", "20260928", "20260929"]), (d.date == "20260930") & ~sealed),
         ("9/30 오후(새 구간)", ~sealed, sealed)]
rows = []
for name, trm, tem in FOLDS:
    for arm, feats, rule in [("전체(오라클 이력)", FULL, d.rule), ("라이트(API 1회)", LITE, d.r_now + d.q_csv + d.q_pending.fillna(0))]:
        dd = d.assign(rule=rule)
        tr, te = dd[trm], dd[tem]
        E.setcap(tr)
        p, Pm = T.run(tr, te, feats)
        m = T.metrics(p, Pm, te)
        err = np.abs(p - te.y.values)
        far, pk = te.stops_away.values >= 3, te.is_peak.values == 1
        rows.append(dict(평가=name, 모델=arm, MAE=m["mae"], Brier=m["brier"], 여유=m["hi_ok"], 여유비율=m["hi_share"],
                         원거리=np.average(err[far], weights=te.w.values[far]), 수업직전=np.average(err[pk], weights=te.w.values[pk])))
    print("done", name, flush=True)
r = pd.DataFrame(rows)
with pd.option_context("display.width", 200, "display.float_format", "{:.3f}".format):
    print(r.to_string(index=False))
    print(r.groupby("모델")[["MAE", "Brier", "여유", "여유비율", "원거리", "수업직전"]].mean())
per = d.r_now  # 참고: 지금 재차 그대로
