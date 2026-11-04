"""저장된 학습 자료의 잠정 정원 초과값 집계. 오류 확정·정제·API 호출은 하지 않는다.

python src/audit_capacity.py --dataset /path/dataset.csv --output /path/audit.json
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import train as T


def summarize(d):
    rows = []
    for (route, bt), g in d.groupby(["route", "bus_type"]):
        cap = T.cap(route, bt)
        now, label = g.r_now > cap, g.y > cap
        rows.append(dict(route=route, bus_type=bt, provisional_capacity=cap, rows=len(g),
                         input_over_capacity=int(now.sum()), label_over_capacity=int(label.sum()),
                         either_over_capacity=int((now | label).sum()),
                         input_max=float(g.r_now.max()), label_max=float(g.y.max())))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    d = pd.read_csv(args.dataset, dtype={"date": str, "bus_type": str})
    cal = pd.read_csv(T.P / "calendar.csv", dtype=str).fillna("")
    d = d.merge(cal[["date", "weekday", "holiday"]], on="date", how="left", validate="many_to_one")
    # 학습 필터와 같은 월~토·공휴일 제외. 정원 초과가 곧 오류라는 뜻은 아님.
    school = d.weekday.notna() & (d.weekday != "일") & (d.holiday == "")
    report = dict(dataset_sha256=hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
                  date_min=d.date.min(), date_max=d.date.max(), days=int(d.date.nunique()),
                  rows=len(d), school_rows=int(school.sum()), capacity_policy=T.capacity_policy(),
                  all_rows=summarize(d), training_population=summarize(d[school]),
                  interpretation="API 입력과 API 정답의 잠정 기준 초과 후보. 반복 조회 포함; 실제 인원 오류나 실제 탑승률을 검증한 결과가 아님.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
