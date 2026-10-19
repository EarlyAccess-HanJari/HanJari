"""수집 로그(data/api_logs) → 학습 데이터 data/processed/dataset.csv

한 행 = (조회 시각 t, 노선, 정류장 s)에서 본 첫째 버스. 거리 제한 없음(서비스는 늘 첫 버스 확률을 보여줌).
정답 y = 그 버스가 s 에 도착하기 직전 마지막 스냅샷의 reride_Num1
  - 도착 판정: 정류장 s 항목의 첫째 버스(plainNo1)가 다른 차로 바뀜. 바뀌기 직전 남은 정류장 수(staOrd−sectOrd1)가 0 이어야 인정.
  - 같은 차가 순환해 하루 여러 번 오므로 "연속으로 첫째 버스였던 구간" = 운행 1회.
  - 도착 1분 전쯤 재차가 떨어지는 경우가 많음(앞 정류장 하차가 늦게 반영) → 마지막 값을 씀.

줄 쌓임 피처 (조회 시각 t 이전에 끝난 사건만 사용 — 누설 없음):
  정류장 j 순증감 net_j(u) = 버스 u 의 (j+1 도착 재차 − j 도착 재차), 쓸 수 있는 시각 = u 의 j+1 도착.
  쌓이는 속도 = net_j(u) ÷ (u 와 그 앞 버스의 j 도착 간격).
  q_live = Σ_{남은 정류장 j} 속도 × (내 버스의 j 도착 추정 − u 의 j 도착).   u = t 이전 j 를 지난 가장 최근 다른 버스
  q_csv  = Σ_{남은 정류장 j} 과거 CSV 학기 평균 회당 (승차 − 하차), 조회 시각의 시간대.
  off_csv = s 정류장 회당 평균 하차(과거 CSV) — P(탑승) 계산의 D.
  q_prev = 직전 버스 u(t 이전에 s 도착)가 같은 구간(s−k → s)에서 겪은 재차 변화 × clip(내 배차간격/u 배차간격, 0.5, 2).
           정류장별 속도(q_live)는 도착 직전 재차 급락 때문에 잡음이 커서(−43~+99), 구간 합으로 상쇄시킨 버전.
  q_bias3 = 최근 3대(t 이전 s 도착)의 (같은 구간 실제 변화 − 그 시간대 CSV 기대 변화) 평균 = 오늘의 혼잡 보정.
  since_prev = 직전 다른 버스가 s 에 도착한 뒤 경과초, hw_ratio = (내 버스 도착 예정 − 직전 도착) ÷ 직전 배차간격.
  eta_gap = 둘째 버스 ETA − 첫째 ETA (뒤차가 붙어 있으면 앞차가 줄을 다 태움).
  route_load = 조회 시각 노선 위 모든 버스(차량번호 중복 제거)의 재차 평균 = 지금 노선 전체 혼잡도.
  q_today = Σ_{남은 정류장 j} (t 이전 60분 안에 j 를 지난 다른 버스들의 순증감 평균). 직전 1대(q_prev)보다 안정적.
  위치 API(pos, 같은 시각 스냅샷): 재차(reride)는 버스가 정류장을 **떠날 때** 갱신된다(9/23 확인: 5번출구 정차 2분 반 동안 6명, 출발 직후 2명).
    도착정보는 버스가 앞 정류장 p 에 서 있어도 "p+1 쪽으로 가는 중"으로 표시 → p 의 승하차가 아직 재차에 없음.
    pos_dwell = 지금 정차 중(stopFlag), pos_sect = 마지막 정류장 p, pos_frac = 구간 진행률(sectDist/fullSectDist),
    q_pending = 정차 중이면 p 의 CSV 평균 순승차(아직 반영 안 된 몫), 아니면 0.
  위치 기반 정류장 순승차(정밀): 버스가 구간 p(=p 출발 후 p+1 로 가는 중, stopFlag 0)에 있을 때의 재차 = p 출발 후 재차.
    net_p = (p 출발 후 재차) − (p−1 출발 후 재차), 사건 시각 = p 출발(구간 p 에서 처음 stopFlag 0).
    q_live2  = Σ_{아직 반영 안 된 정류장 j} 직전 다른 버스의 net_j × clip(경과/그 버스 배차간격, 0.5, 2)
    q_today2 = Σ_{같은 j} 최근 60분 다른 버스들의 net_j 평균 (없으면 CSV)
    반영 안 된 정류장 = 정차 중이면 p..s−1, 달리는 중이면 p+1..s−1 (p = 위치 API 마지막 정류장).
    q_rate  = Σ_j 쌓임속도_j × 공백_j  (구조 모델: 사람은 시간에 비례해 쌓이고 버스가 오면 비워진다)
              쌓임속도_j = 최근 90분 다른 버스들의 Σnet ÷ Σ배차간격(초), 없으면 CSV 회당 순승차 ÷ 600초
              공백_j = 내 버스의 j 도착 추정 − j 를 마지막으로 떠난 다른 버스의 출발 시각 (없으면 600초)
    gap_sum = Σ_j 공백_j (분)
  q_eb    = Σ_{남은 정류장 j} (n·오늘 최근 60분 평균 + K_EB·CSV) / (n + K_EB)  — 오늘 실측이 쌓일수록 CSV(학기 평일 평균)에서 벗어남.
            9/24 추석: CSV 는 +3.66 예상, 실제 +1.09 → CSV 고정 규칙이 persistence 보다 나빠짐. 휴일·방학·행사 대응.
  q_hist  = Σ_{남은 정류장 j} (조회일 이전 수집일들의 같은 정류장·같은 시간대 순증감 평균). 없으면 비움 → CSV 월평균을 실측으로 대체.
"""
import calendar, csv, datetime as dt, glob, json, os
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG, OUT = ROOT / "data/api_logs", ROOT / "data/processed"
STOPS = {"sb02": {30, 31, 32}, "jr03": {19, 20, 23}}
MAX_GAP = 5 * 60   # 스냅샷 간격이 이보다 벌어지면 운행을 끊고 버림(수집 공백)
K_EB = 3           # 오늘 실측 n 개가 CSV 사전값 몇 개 분량과 맞먹는지 (축소 강도)
MAX_HEADWAY = 40 * 60  # 이보다 긴 배차 간격은 쌓임 속도 계산에 안 씀
LINK = 15 * 60     # 같은 버스의 j → j+1 도착이 이 안에 있어야 순증감으로 인정


def files(route, kind, days=None):
    """days 를 주면 그 날짜 폴더만 (서비스: 최근 며칠만 읽어 빠르게).
    날짜 대신 **절대 경로 폴더**를 줘도 됨(LOG / 절대경로 = 그 경로) — 서비스가 LOG 전역을 안 바꾸고 임시 폴더를 읽는 길."""
    return sorted(f for d in (days or ["*"]) for f in glob.glob(str(LOG / f"{d}/{route}_{kind}_*.json")))


def snapshots(route, days=None):
    """시간순 (datetime, {staOrd: item})"""
    for f in files(route, "arr", days):
        day, hms = f.split(os.sep)[-2], os.path.basename(f).split("_")[-1][:6]
        try:
            items = json.load(open(f))["msgBody"]["itemList"] or []
        except ValueError:  # 복사 중 잘린 파일(수집기가 쓰는 도중에 가져옴) — 건너뜀
            continue
        yield dt.datetime.strptime(day + hms, "%Y%m%d%H%M%S"), {int(i["staOrd"]): i for i in items}


def num(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def segments(route, days=None, open_=False):
    """모든 정류장에 대해 (정류장, 차량, [(t, item)...], 도착 여부) — 도착이 확인된 운행만.
    open_: 마지막 스냅샷에 아직 첫째 버스로 오고 있는 운행도 (도착 여부 False) — 서비스 예측용"""
    cur, last_t = {}, None
    for t, items in snapshots(route, days):
        gap = last_t is not None and (t - last_t).total_seconds() > MAX_GAP
        for s, it in items.items():
            plate = it["plainNo1"].strip()
            if s in cur and (gap or plate != cur[s][0]):
                p, seen = cur.pop(s)
                end = seen[-1][1]
                if not gap and num(end["staOrd"]) - num(end["sectOrd1"]) == 0 and num(end["reride_Num1"]) is not None:
                    yield s, p, seen, True
            if plate:
                cur.setdefault(s, (plate, []))[1].append((t, it))
        last_t = t
    if open_:
        for s, (p, seen) in cur.items():
            if seen[-1][0] == last_t:
                yield s, p, seen, False


def csv_tables(route):
    """(seq, 시) → 회당 평균 (승차−하차), 하차. 학기(3~6·9~12월) 월평균의 평균."""
    trips, days = defaultdict(int), defaultdict(set)
    for r in csv.DictReader(open(OUT / f"{route}_trips.csv")):
        ym = r["date"][:6]
        trips[(ym, r["stop_id"], int(r["hour"]))] += int(r["trips"])
        days[(ym, r["stop_id"])].add(r["date"])
    acc = defaultdict(list)
    for r in csv.DictReader(open(OUT / f"{route}_hourly.csv")):
        ym, h = r["ym"], int(r["hour"])
        if int(ym[4:]) not in (3, 4, 5, 6, 9, 10, 11, 12):
            continue
        got = len(days[(ym, r["stop_id"])])
        n = trips[(ym, r["stop_id"], h)] / got * calendar.monthrange(int(ym[:4]), int(ym[4:]))[1] if got else 0
        if n > 0:
            acc[(int(r["seq"]), h)].append(((float(r["on"]) - float(r["off"])) / n, float(r["off"]) / n))
    return {k: tuple(sum(x) / len(v) for x in zip(*v)) for k, v in acc.items()}


HIST_DAY = {}
HIST_ALL = {}  # 노선 → {(정류장, 시): 읽은 모든 날의 순증감 평균}. 서비스는 이걸 저장해 두고 q_hist 로 씀(과거 로그를 매번 안 읽게)


def build(route, days=None, open_=False, hist_all=None, tab=None):
    """open_: 아직 도착 안 한 첫째 버스의 **마지막 스냅샷** 행만 돌려줌(y·arrive_time 없음). 피처 계산은 학습과 같은 코드.
    hist_all: {(정류장, 시): 평균} — 주면 q_hist 를 이 표로 계산(서비스: 오늘 로그만 읽으므로)."""
    arr = defaultdict(list)  # stop -> [(t_arr, plate, load)]
    target = []
    for s, plate, seen, done in segments(route, days, open_):
        if not done:
            if s in STOPS[route]:
                target.append((s, plate, seen[-1:], None, None))
            continue
        t_end, end = seen[-1]
        y = num(end["reride_Num1"])
        arr[s].append((t_end, plate, y))
        if s in STOPS[route] and not open_:
            target.append((s, plate, seen, t_end, y))
    for v in arr.values():
        v.sort()

    # 정류장별 순증감 사건: (쓸 수 있는 시각, j 도착 시각, 차량, net, 배차간격초)
    ev = defaultdict(list)
    for j, lst in arr.items():
        nxt = arr.get(j + 1, [])
        for i, (tj, v, lj) in enumerate(lst):
            m = next(((t2, l2) for t2, p2, l2 in nxt if p2 == v and tj < t2 <= tj + dt.timedelta(seconds=LINK)), None)
            hw = (tj - lst[i - 1][0]).total_seconds() if i else None
            if m and hw and 0 < hw <= MAX_HEADWAY:
                ev[j].append((m[0], tj, v, m[1] - lj, hw))

    # 조회 시각별 노선 전체 혼잡도
    route_load = {}
    for t, items in snapshots(route, days):
        loads = {}
        for it in items.values():
            for i in "12":
                p, r = it["plainNo" + i].strip(), num(it["reride_Num" + i])
                if p and r is not None:
                    loads[p] = r
        route_load[t] = round(sum(loads.values()) / len(loads), 2) if loads else None
    tab = csv_tables(route) if tab is None else tab  # 서비스(라이트)는 저장해 둔 표를 씀(원본 CSV 60MB 없이)
    # 위치 스냅샷: 조회 시각 → {차량: (마지막 정류장, 정차중, 구간 진행률)}
    pos = {}
    for f in files(route, "pos", days):
        day, hms = f.split(os.sep)[-2], os.path.basename(f).split("_")[-1][:6]
        vs = {}
        try:
            its = json.load(open(f))["msgBody"]["itemList"] or []
        except ValueError:
            continue
        for v in its:
            try:
                frac = float(v["sectDist"]) / float(v["fullSectDist"])
            except (ValueError, ZeroDivisionError):
                frac = None
            vs[v["plainNo"].strip()] = (num(v["sectOrd"]), num(v["stopFlag"]), frac)
        pos[dt.datetime.strptime(day + hms, "%Y%m%d%H%M%S")] = vs
    # 위치 기반 정밀 순승차 사건: pev[j] = [(출발시각, 차량, net, 배차간격초, 알 수 있게 된 시각)]
    #   net 은 구간 j 를 달리는 동안의 마지막 재차로 계산 → 알 수 있는 시각 = 그 구간을 마지막으로 본 시각(출발 시각 아님, 09-24 누설 수정)
    rr = {}  # (t, 차량) → 재차 (도착정보 어느 항목에서든)
    for t, items in snapshots(route, days):
        for it in items.values():
            for i in "12":
                pl, r = it["plainNo" + i].strip(), num(it["reride_Num" + i])
                if pl and r is not None:
                    rr[(t, pl)] = r
    segs = defaultdict(list)  # 차량 → [구간 p, 출발시각, 구간 안 달리는 중 마지막 재차, 마지막으로 본 시각, 그 재차를 본 시각]
    for t in sorted(pos):
        for pl, (p, f, _) in pos[t].items():
            r = rr.get((t, pl))
            if p is None:
                continue
            sg = segs[pl]
            if not sg or sg[-1][0] != p or (t - sg[-1][3]).total_seconds() > MAX_GAP:
                sg.append([p, None, None, t, None])
            sg[-1][3] = t
            if f == 0:
                if sg[-1][1] is None:
                    sg[-1][1] = t
                if r is not None:
                    sg[-1][2] = r
                    sg[-1][4] = t
    pev = defaultdict(list)
    for pl, sg in segs.items():
        for a, b in zip(sg, sg[1:]):
            if b[0] == a[0] + 1 and a[2] is not None and b[2] is not None and b[1] is not None:
                pev[b[0]].append((b[1], pl, b[2] - a[2], max(a[4], b[4])))
    for j, lst in pev.items():
        lst.sort()
        pev[j] = [(t, pl, n, (t - lst[i - 1][0]).total_seconds() if i else None, av) for i, (t, pl, n, av) in enumerate(lst)]
    # 이전 수집일 실측: (정류장, 시, 조회일) → 그 날짜 이전 모든 날의 순증감 평균
    by = defaultdict(list)
    for j, lst in ev.items():
        for e in lst:
            by[(j, e[1].hour)].append((e[1].date(), e[3]))
    ev_days = sorted({e[1].date() for lst in ev.values() for e in lst})
    hist = {}
    for (j, h), v in by.items():
        for day in ev_days:
            prev = [n for dd, n in v if dd < day]
            if prev:
                hist[(j, h, day)] = sum(prev) / len(prev)
    HIST_ALL[route] = {k: sum(n for _, n in v) / len(v) for k, v in by.items()}
    HIST_DAY[route] = defaultdict(lambda: [0.0, 0])  # (정류장, 시, 날짜) → [순증감 합, 개수] — 증분 빌드가 q_hist 를 이어 붙일 때
    for (j, h), v in by.items():
        for dd, n in v:
            c = HIST_DAY[route][(j, h, dd.strftime("%Y%m%d"))]
            c[0] += n
            c[1] += 1
    rows = []
    for s, plate, seen, t_end, y in target:
        for t, it in seen:
            eta, k = num(it["traTime1"]), num(it["staOrd"]) - num(it["sectOrd1"])
            if eta is None or k is None or k < 0:
                continue
            J = range(s - k, s)
            q_live, used = 0.0, 0
            for idx, j in enumerate(J):
                cand = [e for e in ev.get(j, []) if e[0] <= t and e[2] != plate]
                if not cand:
                    continue
                _, tj, _, net, hw = max(cand, key=lambda e: e[1])
                t_est = t + dt.timedelta(seconds=eta * (idx + 1) / (k + 1))
                q_live += net / hw * max((t_est - tj).total_seconds(), 0)
                used += 1
            # 직전 버스의 같은 구간 변화
            q_prev = None
            prev = [a for a in arr[s] if a[0] <= t and a[1] != plate]
            if k > 0 and prev:
                tu, u, lu = prev[-1]
                start = [a for a in arr.get(s - k, []) if a[1] == u and tu - dt.timedelta(seconds=MAX_HEADWAY) <= a[0] < tu]
                older = [a for a in arr[s] if a[0] < tu]
                if start and older:
                    hw_u = (tu - older[-1][0]).total_seconds()
                    hw_v = (t + dt.timedelta(seconds=eta) - tu).total_seconds()
                    if 0 < hw_u <= MAX_HEADWAY:
                        q_prev = round((lu - start[-1][2]) * min(max(hw_v / hw_u, 0.5), 2.0), 2)
            elif k == 0:
                q_prev = 0.0
            h = t.hour
            ps, pdw, pfr = pos.get(t, {}).get(plate, (None, None, None))
            q_live2 = q_today2 = q_rate = gap_sum = None
            if ps is not None and ps < s:
                J2 = range(ps if pdw == 1 else ps + 1, s)
                q_live2 = q_today2 = q_rate = gap_sum = 0.0
                for idx, j in enumerate(J2):
                    t_j = t + dt.timedelta(seconds=eta * (idx + 1) / (len(J2) + 1))
                    evs_all = [e for e in pev.get(j, []) if e[4] <= t and e[1] != plate]
                    win = [e for e in evs_all if e[0] >= t - dt.timedelta(minutes=90) and e[3] and 0 < e[3] <= MAX_HEADWAY]
                    rate = sum(e[2] for e in win) / sum(e[3] for e in win) if win else tab.get((j, t.hour), (0, 0))[0] / 600
                    gap = (t_j - evs_all[-1][0]).total_seconds() if evs_all and (t_j - evs_all[-1][0]).total_seconds() <= MAX_HEADWAY else 600
                    q_rate += rate * max(gap, 0)
                    gap_sum += max(gap, 0) / 60
                    evs = [e for e in pev.get(j, []) if e[4] <= t and e[1] != plate]
                    last = evs[-1] if evs else None
                    if last and last[3] and 0 < last[3] <= MAX_HEADWAY:
                        t_est = t + dt.timedelta(seconds=eta * (idx + 1) / (len(J2) + 1))
                        q_live2 += last[2] * min(max((t_est - last[0]).total_seconds() / last[3], 0.5), 2.0)
                    else:
                        q_live2 += tab.get((j, t.hour), (0, 0))[0]
                    rec = [e[2] for e in evs if e[0] >= t - dt.timedelta(minutes=60)]
                    q_today2 += sum(rec) / len(rec) if rec else tab.get((j, t.hour), (0, 0))[0]
                q_live2, q_today2, q_rate, gap_sum = round(q_live2, 2), round(q_today2, 2), round(q_rate, 2), round(gap_sum, 1)
            elif ps is not None:
                q_live2 = q_today2 = q_rate = gap_sum = 0.0
            q_pending = round(tab.get((ps, h), (0, 0))[0], 2) if pdw == 1 and ps is not None and ps < s else 0.0
            # 오늘 최근 60분 / 이전 수집일 같은 시간대의 정류장별 실측 순증감
            q_today = q_hist = q_eb = None
            if k > 0:
                tv, hv, ebv = [], [], []
                for j in J:
                    today = [e[3] for e in ev.get(j, []) if t - dt.timedelta(minutes=60) <= e[0] <= t and e[2] != plate]
                    past = hist.get((j, h, t.date())) if hist_all is None else hist_all.get((j, h))
                    prior = tab.get((j, h), (0, 0))[0]
                    tv.append(sum(today) / len(today) if today else prior)
                    ebv.append((sum(today) + K_EB * prior) / (len(today) + K_EB))
                    hv.append(past)
                q_today = round(sum(tv), 2)
                q_eb = round(sum(ebv), 2)
                q_hist = round(sum(hv), 2) if all(x is not None for x in hv) else None
            elif k == 0:
                q_today = q_hist = q_eb = 0.0
            # 오늘의 혼잡 보정: 최근 3대의 (실제 구간 변화 − CSV 기대)
            q_bias3 = None
            if k > 0 and prev:
                diffs = []
                for tu, u, lu in prev[-3:]:
                    st = [a for a in arr.get(s - k, []) if a[1] == u and tu - dt.timedelta(seconds=MAX_HEADWAY) <= a[0] < tu]
                    if st:
                        exp = sum(tab.get((j, tu.hour), (0, 0))[0] for j in J)
                        diffs.append((lu - st[-1][2]) - exp)
                if diffs:
                    q_bias3 = round(sum(diffs) / len(diffs), 2)
            elif k == 0:
                q_bias3 = 0.0
            since_prev = hw_ratio = None
            if prev:
                tu = prev[-1][0]
                since_prev = int((t - tu).total_seconds())
                older = [a for a in arr[s] if a[0] < tu]
                if older and 0 < (tu - older[-1][0]).total_seconds() <= MAX_HEADWAY:
                    hw_ratio = round((t - tu).total_seconds() + eta) / (tu - older[-1][0]).total_seconds()
                    hw_ratio = round(hw_ratio, 3)
            rows.append(dict(
                date=t.strftime("%Y%m%d"), time=t.strftime("%H:%M:%S"), route=route, stop=s, plate=plate,
                bus_type=it["busType1"], eta=eta, stops_away=k, r_now=num(it["reride_Num1"]),
                eta2=num(it["traTime2"]), r2=num(it["reride_Num2"]),
                q_live=round(q_live, 2), q_cover=round(used / len(J), 2) if len(J) else 1.0, q_prev=q_prev, q_today=q_today, q_eb=q_eb, q_hist=q_hist, q_bias3=q_bias3, since_prev=since_prev, hw_ratio=hw_ratio,
                eta_gap=(num(it["traTime2"]) - eta) if num(it["traTime2"]) else None, route_load=route_load.get(t),
                pos_sect=ps, pos_dwell=pdw, pos_frac=None if pfr is None else round(pfr, 3), q_pending=q_pending,
                q_live2=q_live2, q_today2=q_today2, q_rate=q_rate, gap_sum=gap_sum,
                q_csv=round(sum(tab.get((j, h), (0, 0))[0] for j in J), 2),
                off_csv=round(tab.get((s, h), (0, 0))[1], 2),
                arrive_time=t_end.strftime("%H:%M:%S") if t_end else None, y=y))
    return rows


def build_day(route, folders, i, acc):
    """날짜 폴더 i 의 행만. 자정을 넘는 운행·직전 버스 때문에 앞뒤 폴더까지 읽고 그 날 행만 남긴다.
    q_hist 는 전날까지 누적(acc)으로 — 전체 빌드와 같은 정의(조회일 이전 모든 날의 평균)."""
    day = folders[i]
    rows = build(route, folders[max(i - 1, 0):i + 2], hist_all={k: s / c for k, (s, c) in acc.items()})
    ev = [[j, h, *v] for (j, h, dd), v in HIST_DAY[route].items() if dd == day]
    return [r for r in rows if r["date"] == day], ev


def main(full=False, out=None):
    """기본은 증분: data/processed/days/ 에 날짜별 행·순증감을 저장해 두고, 파일 수가 바뀐 날(과 그 뒤)만 다시 계산.
    메모리는 한 번에 3일치만 → 로그가 몇 달 쌓여도 일정. full=True 면 예전처럼 전체를 한 번에."""
    if full:
        rows = [r for route in STOPS for r in build(route)]
    else:
        cache = OUT / "days"
        cache.mkdir(exist_ok=True)
        # 원본 폴더가 압축·삭제된 날(daily.py ⑥ 정리)도 캐시가 있으면 그대로 이어 붙임
        folders = sorted({p.name for p in LOG.glob("2026*") if p.is_dir()} | {f.name.split("_")[0] for f in cache.glob("2026*_*.json")})
        rows, redo = [], 0
        for route in STOPS:
            acc, dirty = defaultdict(lambda: [0.0, 0]), False
            def count(d):
                if (LOG / d).is_dir():
                    return len(glob.glob(str(LOG / d / f"{route}_*.json")))
                mf = cache / f"{d}_{route}.json"
                return json.loads(mf.read_text()).get("n") if mf.exists() else 0
            n = [count(d) for d in folders]
            for i, day in enumerate(folders):
                mf, rf = cache / f"{day}_{route}.json", cache / f"{day}_{route}.csv"
                files = n[max(i - 1, 0):i + 2]
                meta = json.loads(mf.read_text()) if mf.exists() else None
                dirty = dirty or meta is None or meta["files"] != files  # 한 날이 바뀌면 뒤 날들의 q_hist 도 바뀜
                if dirty and not (LOG / day).is_dir():
                    raise RuntimeError(f"{day} 원본이 압축돼 있어 다시 계산 불가 → tar xzf archive/{day}.tar.gz -C api_logs 후 재실행")
                if meta and "n" not in meta and (LOG / day).is_dir():  # 압축 전에 그날 파일 수를 캐시에 남겨 둠
                    meta["n"] = n[i]
                    mf.write_text(json.dumps(meta))
                if dirty:
                    got, ev = build_day(route, folders, i, acc)
                    with open(rf, "w", newline="") as f:
                        if got:
                            w = csv.DictWriter(f, fieldnames=list(got[0]))
                            w.writeheader()
                            w.writerows(got)
                    meta = dict(files=files, n=n[i], ev=ev)
                    mf.write_text(json.dumps(meta))
                    redo += 1
                else:
                    got = list(csv.DictReader(open(rf))) if rf.stat().st_size else []
                for j, h, s_, c in meta["ev"]:
                    acc[(j, h)][0] += s_
                    acc[(j, h)][1] += c
                rows += got
        print(f"다시 계산한 날·노선 {redo}개")
    with open(out or OUT / "dataset.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    n_trip = len({(r["date"], r["route"], r["stop"], r["plate"], r["arrive_time"]) for r in rows})
    print(f"rows {len(rows)}, 운행 {n_trip}")


if __name__ == "__main__":
    import sys
    main(full="--full" in sys.argv)
