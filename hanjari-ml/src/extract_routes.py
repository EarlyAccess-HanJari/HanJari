"""원본(data/raw)에서 대상 노선(성북02·종로03) 행만 뽑아 data/processed 에 저장.

- {노선}_hourly.csv : 월 × 정류장순번 × 시 승차/하차 (OA-12913). 같은 순번이 두 줄이면(월중 정류장명 변경) 합산.
- {노선}_trips.csv  : 날짜 × 정류장 × 시 운행횟수 (OA-21220). 주간 파일이 겹치면 날짜 기준 중복 제거.
"""
import csv, glob, io, re, zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW, OUT = ROOT / "data/raw", ROOT / "data/processed"
ROUTES = {"sb02": ("성북02", "107900003"), "jr03": ("종로03", "100900010")}  # 이름: (노선번호, 노선ID)
TRIPS_COLS = ["기준_날짜", "노선_ID", "정류장_ID", "버스운행횟수",
              *[f"버스운행횟수_{h:02d}시" for h in range(24)], "정류장_순서"]


def hourly(name):
    route_no = ROUTES[name][0]
    agg = defaultdict(lambda: [0.0, 0.0])
    meta = {}
    for f in sorted(glob.glob(str(RAW / "seoul_hourly/*.csv"))):
        for r in csv.DictReader(open(f, encoding="cp949")):
            if r["노선번호"] != route_no:
                continue
            seq = int(re.search(r"\((\d+)\)$", r["역명"]).group(1))
            meta[(r["사용년월"], seq)] = (r["역명"], r["버스정류장ARS번호"], r["표준버스정류장ID"])
            for h in range(24):
                a = agg[(r["사용년월"], seq, h)]
                a[0] += float(r[f"{'00' if h == 0 else h}시승차총승객수"] or 0)
                a[1] += float(r[f"{'00' if h == 0 else h}시하차총승객수"] or 0)
    with open(OUT / f"{name}_hourly.csv", "w", newline="") as fo:
        w = csv.writer(fo)
        w.writerow(["ym", "seq", "stop_name", "ars", "stop_id", "hour", "on", "off"])
        for (ym, seq, h), (on, off) in sorted(agg.items()):
            w.writerow([ym, seq, *meta[(ym, seq)], h, on, off])
    return len(agg)


def trips(name):
    route_id = ROUTES[name][1]
    rows = {}
    for f in sorted(glob.glob(str(RAW / "seoul_trips/*.zip"))):
        z = zipfile.ZipFile(f)
        for i in z.infolist():
            rd = csv.reader(io.TextIOWrapper(z.open(i), encoding="cp949", errors="replace"))
            head = next(rd)
            if "노선_ID" not in head:  # 2023.01.02-01.08 파일은 원본 헤더가 '????' 로 깨짐, 순서는 동일
                head = TRIPS_COLS
            for r in (dict(zip(head, x)) for x in rd):
                if r["노선_ID"] != route_id:
                    continue
                for h in range(24):
                    n = r[f"버스운행횟수_{h:02d}시"]
                    rows[(r["기준_날짜"], r["정류장_순서"], r["정류장_ID"], h)] = int(n or 0)
    with open(OUT / f"{name}_trips.csv", "w", newline="") as fo:
        w = csv.writer(fo)
        w.writerow(["date", "seq", "stop_id", "hour", "trips"])
        for k, n in sorted(rows.items()):
            w.writerow([*k, n])
    return len(rows)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ROUTES:
        print(name, "hourly rows", hourly(name), "trips rows", trips(name))
