"""학습을 작게 — 서버 한 대(1GB)에 수집·학습·백엔드를 같이 올리기 위한 설정 비교.
python exp_small.py <트리수> <학습률> <분위수 개수> <스레드>   → 한 줄: 평일 4폴드 MAE·Brier·'여유', 최종 학습 1회 시간·최대 메모리
"""
import json, resource, sys, time
import numpy as np
import serve as S
import train as T
import eval_days as E

n, lr, nq, jobs = int(sys.argv[1]), float(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
T.XGB_KW = dict(T.XGB_KW, n_estimators=n, learning_rate=lr, n_jobs=jobs)
T.QS = np.round(np.linspace(0.05, 0.95, nq), 3)
WD = ["20260923", "20260928", "20260929", "20260930", "20261001"]
d = T.features()
d = d[d.date.isin(WD)].assign(rule=lambda x: S.lite_rule(x))
ms = []
for day in WD[1:]:
    tr, te = d[d.date != day], d[d.date == day]
    E.setcap(tr)
    p, Pm = T.run(tr, te, S.LITE)
    ms.append(T.metrics(p, Pm, te))
t0 = time.time()
E.setcap(d)
m = T.fit(d, S.LITE)
sec = time.time() - t0
print(json.dumps(dict(trees=n, lr=lr, quantiles=nq, jobs=jobs,
                      mae=round(float(np.mean([x["mae"] for x in ms])), 3), brier=round(float(np.mean([x["brier"] for x in ms])), 4),
                      yeoyu=round(float(np.nanmean([x["hi_ok"] for x in ms])), 4),
                      fit_sec=round(sec), peak_mb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)), ensure_ascii=False))
