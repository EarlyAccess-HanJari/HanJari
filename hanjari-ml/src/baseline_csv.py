"""기준 모델(단계 0): CSV로 정류장별·학기구분별·시간대별 회당 평균.

입력: data/processed/sb02_hourly.csv, sb02_trips.csv (src/extract_sb02.py 결과)
출력: data/processed/baseline_csv.csv + 콘솔 표 + 비정상 구간 목록

회당 값 = 월 합계 ÷ 추정 월 운행횟수.
추정 월 운행횟수 = (자료 있는 날 평균 운행) × 그 달 일수 — 운행횟수 결측일(49일) 보정.
도착 재차 = 정문 승차(순번 1·38 합) + 그 시간대 순번 2~(k−1) (승차−하차) 누적. 한 회차가 시간대 경계를 넘으면 틀어짐(음수 가능).
학기 구분(가정): 3~6·9~12월 학기, 1·2·7·8월 방학. 6·12월 말은 종강 후라 섞여 있음.
"""
import calendar, csv
from collections import defaultdict
from pathlib import Path

P = Path(__file__).resolve().parents[1] / "data/processed"
STOPS = {30: ("5번출구", "107900090"), 31: ("2번출구", "107900107"), 32: ("녹십자약국", "107900127")}
HOURS = range(6, 24)  # 성북02 운행 06:0x~23:5x


def term(ym):
    return "방학" if int(ym[4:]) in (1, 2, 7, 8) else "학기"


def main():
    hr = defaultdict(lambda: [0.0, 0.0])  # (ym, seq, h) -> [on, off]
    for r in csv.DictReader(open(P / "sb02_hourly.csv")):
        hr[(r["ym"], int(r["seq"]), int(r["hour"]))] = [float(r["on"]), float(r["off"])]
    yms = sorted({k[0] for k in hr})

    tr = defaultdict(int)       # (ym, stop_id, h) -> 운행 합
    days = defaultdict(set)     # (ym, stop_id) -> 자료 있는 날
    for r in csv.DictReader(open(P / "sb02_trips.csv")):
        if r["stop_id"] in {s for _, s in STOPS.values()}:
            ym = r["date"][:6]
            tr[(ym, r["stop_id"], int(r["hour"]))] += int(r["trips"])
            days[(ym, r["stop_id"])].add(r["date"])

    rows, bad = [], []
    for ym in yms:
        ndays = calendar.monthrange(int(ym[:4]), int(ym[4:]))[1]
        for seq, (name, sid) in STOPS.items():
            got = len(days[(ym, sid)])
            for h in HOURS:
                if not got or not tr[(ym, sid, h)]:
                    bad.append((ym, name, h, "운행횟수 없음"))
                    continue
                n = tr[(ym, sid, h)] / got * ndays
                # 순환노선: 정문이 순번 1·38 두 줄로 나뉘어 집계됨 → 정문 승차(1·38)는 출발 승차, 정문 하차는 종점 하차
                load = hr[(ym, 1, h)][0] + hr[(ym, 38, h)][0] + sum(
                    hr[(ym, j, h)][0] - hr[(ym, j, h)][1] for j in range(2, seq))
                on, off = hr[(ym, seq, h)]
                row = dict(ym=ym, term=term(ym), stop=name, hour=h, trips_est=round(n),
                           miss_days=ndays - got, load=load / n, on=on / n, off=off / n)
                rows.append(row)
                if row["load"] < 0 or row["load"] > 60:
                    bad.append((ym, name, h, f"도착재차 {row['load']:.1f}"))

    with open(P / "baseline_csv.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    print("학기구분 정류장 시 | 도착재차/회 승차/회 하차/회 (월평균의 평균, n=월수)")
    g = defaultdict(list)
    for r in rows:
        g[(r["term"], r["stop"], r["hour"])].append(r)
    for (t, s, h), L in sorted(g.items(), key=lambda x: (x[0][0], list(STOPS.values()).index(
            next(v for v in STOPS.values() if v[0] == x[0][1])), x[0][2])):
        m = lambda k: sum(r[k] for r in L) / len(L)
        print(f"{t} {s:6} {h:2}시 | {m('load'):5.1f} {m('on'):5.1f} {m('off'):5.1f}  n={len(L)}")
    print(f"\n비정상 구간 {len(bad)}건:")
    for b in bad:
        print(" ", *b)


if __name__ == "__main__":
    main()
