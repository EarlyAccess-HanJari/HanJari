"""달력·수업 피처 → data/processed/calendar.csv, class_starts.csv

calendar.csv   : 날짜별 요일·공휴일(특일정보)·학기/방학·시험기간·개교기념일 (한성대 학사일정 ICS)
class_starts.csv: 요일×시각(30분 단위)별 강좌 시작 수 — 대면수업 + BL(온라인 일부 + 강의실 수업) (한성대 공개 강의시간표)

교시 → 시각 (강좌 데이터에서 역추정. 1교시 09:00 은 지용 확인 09-23, M=+30분은 추정):
  k교시 = (8+k)시, 'M' = +30분.  1교시 09:00, 5M 13:30, 10교시 18:00(야간 시작).
  근거: 'a~b' 의 길이가 b−a+0.5시간이면 2회×1.5h(3학점)·1회×3h 블록이 전부 맞음.
"""
import csv, datetime as dt, glob, re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW, OUT = ROOT / "data/raw", ROOT / "data/processed"
DAYS = "월화수목금토일"


def period_time(p):
    h = 8 + int(p.rstrip("M"))
    return f"{h:02d}:{30 if p.endswith('M') else 0:02d}"


def ics_events():
    ev = {}
    for f in glob.glob(str(RAW / "hansung_calendar/*.ics")):
        for b in open(f, encoding="utf-8").read().split("BEGIN:VEVENT")[1:]:
            g = lambda k: (re.search(rf"^{k}[^:]*:(.*)$", b, re.M) or [None, ""])[1].strip()
            ev[g("UID")] = (g("DTSTART")[:8], g("DTEND")[:8], g("SUMMARY"))
    return sorted(ev.values())


def d(s):
    return dt.date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def calendar():
    ev = ics_events()
    hol = {r["date"]: r["name"] for r in csv.DictReader(open(OUT / "holidays.csv"))}
    # 학기 = 개강일 ~ 종강일
    # 표기가 해마다 다름: "개강", "개시일 및 개강일", "2023학년도 2학기 개시 및 개강", "1학기 종강" … 계절학기는 제외
    reg = lambda n: "계절" not in n and "상상더" not in n
    starts = sorted(d(s) for s, _, n in ev if reg(n) and n.endswith(("개강", "개강일")))
    ends = sorted(d(s) for s, _, n in ev if reg(n) and n.endswith("종강"))
    terms = [(a, min(e for e in ends if e >= a)) for a in starts if any(e >= a for e in ends)]
    exams = [(d(s), d(e), "중간" if "중간" in n else "기말") for s, e, n in ev if "고사" in n]
    off = {d(s) for s, _, n in ev if "개교기념일" in n}

    rows, day = [], dt.date(2023, 1, 1)
    while day <= dt.date(2026, 12, 31):
        k = day.strftime("%Y%m%d")
        exam = next((t for a, b, t in exams if a <= day <= b), "")
        rows.append(dict(date=k, weekday=DAYS[day.weekday()], holiday=hol.get(k, ""),
                         term="학기" if any(a <= day <= b for a, b in terms) else "방학",
                         exam=exam, school_off=int(day in off)))
        day += dt.timedelta(1)
    write("calendar.csv", rows)
    return terms


def class_starts():
    c = Counter()
    for f in glob.glob(str(RAW / "hansung_timetable_*.csv")):
        for r in csv.DictReader(open(f, encoding="utf-8-sig")):
            # 10-05: BL 도 강의실 수업이 있음 — 대면만 세면 토요일 80개 중 8개, 평일도 절반 가까이 빠졌다(src/exp_bl.py). 온라인100% 만 제외
            if r["mode"] not in ("대면수업", "BL"):
                continue
            for day, a, _ in re.findall(r"([월화수목금토일])(\d+M?)~(\d+M?)", r["classroom"]):
                c[(r["yearhakgi"], day, period_time(a))] += 1
    write("class_starts.csv", [dict(yearhakgi=y, weekday=w, start=t, n=n) for (y, w, t), n in sorted(c.items())])
    return c


def write(name, rows):
    with open(OUT / name, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    assert period_time("1") == "09:00" and period_time("5M") == "13:30" and period_time("10") == "18:00"
    terms = calendar()
    print("학기:", [(a.isoformat(), b.isoformat()) for a, b in terms])
    c = class_starts()
    tot = Counter()
    for (_, _, t), n in c.items():
        tot[t] += n
    print("강좌(대면+BL) 시작 시각별(주간 합):", sorted(tot.items()))
