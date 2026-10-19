"""수업 수에 BL(블렌디드) 강좌를 넣을까 — 지금은 '대면수업'만 셈(BL 737개·토요일 72개 빠짐).
BL 도 강의실·요일·교시가 있는 오프라인 수업이 있다(온라인 몇 시간 + 대면).
팔: A 대면만·피크 20(지금) / B 대면+BL·피크 20 / C 대면+BL·피크 40(수업 수가 ~2배라 문턱도 2배)
평가: 수업 있는 날(일요일·공휴일 제외) 날짜 분할 — 9/28~10/2 각 하루를 빼고 나머지로 학습. 라이트 모델.
"""
import csv, re, shutil, tempfile
from collections import Counter
from pathlib import Path
import numpy as np, pandas as pd
import build_calendar as BC
import eval_days as E
import serve as S
import train as T

DAYS = ["20260928", "20260929", "20260930", "20261001", "20261002"]


def class_starts(modes, out):
    c = Counter()
    for f in BC.RAW.glob("hansung_timetable_*.csv"):
        for r in csv.DictReader(open(f, encoding="utf-8-sig")):
            if r["mode"] not in modes:
                continue
            for day, a, _ in re.findall(r"([월화수목금토일])(\d+M?)~(\d+M?)", r["classroom"]):
                c[(r["yearhakgi"], day, BC.period_time(a))] += 1
    with open(out / "class_starts.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["yearhakgi", "weekday", "start", "n"])
        w.writerows([y, d, t, n] for (y, d, t), n in sorted(c.items()))


rows = []
for arm, modes, peak in [("A 대면만·피크20(지금)", {"대면수업"}, 20), ("B 대면+BL·피크20", {"대면수업", "BL"}, 20),
                         ("C 대면+BL·피크40", {"대면수업", "BL"}, 40)]:
    tmp = Path(tempfile.mkdtemp())
    shutil.copy(T.P / "calendar.csv", tmp)
    class_starts(modes, tmp)
    P0, pk0 = T.P, T.PEAK_CLASSES
    T.P, T.PEAK_CLASSES = tmp, peak
    try:
        d = T.features()
    finally:
        T.P, T.PEAK_CLASSES = P0, pk0
    d = d[~d.holiday & (d.weekday != "일")].assign(rule=lambda x: S.lite_rule(x))
    for day in DAYS:
        tr, te = d[d.date != day], d[d.date == day]
        E.setcap(tr)
        p, Pm = T.run(tr, te, S.LITE)
        m = T.metrics(p, Pm, te)
        err, w = np.abs(p - te.y.values), te.w.values
        win = te.time.between("07:30", "11:00").values  # 등교 피크(팔과 무관한 고정 구간)
        rows.append(dict(팔=arm, 평가=day, MAE=m["mae"], Brier=m["brier"], 여유=m["hi_ok"],
                         등교피크=np.average(err[win], weights=w[win]), 피크칸비율=te.is_peak.mean()))
    print("done", arm, flush=True)
r = pd.DataFrame(rows)
with pd.option_context("display.width", 200, "display.float_format", "{:.3f}".format):
    print(r.pivot(index="팔", columns="평가", values="MAE"))
    print(r.groupby("팔", sort=False)[["MAE", "Brier", "여유", "등교피크", "피크칸비율"]].mean())
