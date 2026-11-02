"""실시간 수집기 (성북02·종로03). 매일, 노선별 **실제 버스 시간표**(첫차 10분 전 ~ 막차 10분 후) 동안 도착정보·차량위치 원본을 그대로 저장.

시간표: 도착정보 응답의 firstTm/lastTm(그날 시간표)을 노선·요일유형(평일/토/일·공휴일)별로 data/api_logs/schedule.json 에 학습.
        아직 모르는 요일유형은 넉넉히 05:30~00:40 에 받으며 배운다. 01:30~05:00 은 어떤 경우에도 호출 안 함(새벽 차단).
        자정 넘은 막차(성북02 00:06, 종로03 00:32)는 전날 운행일로 셈.

data/api_logs/YYYYMMDD/{노선}_{arr,pos}_HHMMSS.json  (시각은 KST)
실행: nohup python3 src/collect.py >> data/api_logs/collect.log 2>&1 &
키: .env 의 SEOUL_BUS_API_KEY* 전부를 풀로 묶어 호출마다 돌아가며 사용. 간격 = 기본간격 × 노선수 ÷ 키수 (키당 한도 유지).
"""
import datetime as dt, hashlib, itertools, json, os, tempfile, time, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "data/api_logs"
ROUTES = {"sb02": "107900003", "jr03": "100900010"}  # 이름: busRouteId
URLS = {
    "arr": "http://ws.bus.go.kr/api/rest/arrive/getArrInfoByRouteAll",
    "pos": "http://ws.bus.go.kr/api/rest/buspos/getBusPosByRtid",
}
SCHED = LOG / "schedule.json"
PAD = 10                   # 첫차 전·막차 후 여유(분)
FALLBACK = (5 * 60 + 30, 24 * 60 + 40)  # 시간표 모를 때 05:30 ~ 다음날 00:40 (운행일 기준 분)
NIGHT = (dt.time(1, 30), dt.time(5, 0))  # 설정·시간표가 어떻든 이 시간엔 절대 호출 안 함
DAY_START = 5 * 60         # 05:00 이전 시각은 전날 운행일로 셈
HOLIDAYS = ROOT / "data/processed/holidays.csv"
# 시간대별 기본 간격(키 1개·노선 1개 기준, 초). 실제 간격 = 기본 × 노선수 ÷ 키수. 키 4개·노선 2개면 27초 / 40초 / 150초.
#   07~19시: 등교·18:00 야간수업 직전까지 / 19~22시: 19:30·21:00 야간 강좌 / 그 외(첫차~07시, 22시~막차): 한산
TIERS = [(dt.time(7, 0), dt.time(19, 0), 54), (dt.time(19, 0), dt.time(22, 0), 80)]
OFF = 300  # 위 구간 밖(키 4개면 150초). 시간표 창이 가장 넓을 때(05:30~00:40)도 키당 990건, 학습된 평일 980건 (시뮬레이션 09-28)
LIMIT = 990  # 키당·서비스당 하루 호출 상한(한도 1000). 넘기 전에 멈춤 — 계산이 틀려도 한도 초과 방지
KST = dt.timezone(dt.timedelta(hours=9))  # 컨테이너 시계는 UTC


def interval(t, share=1.0):
    return next((iv for a, b, iv in TIERS if a <= t < b), OFF) * share


def service_day(now):
    """(운행일, 운행일 기준 분). 05:00 이전은 전날 운행일의 24시 이후로 셈."""
    m = now.hour * 60 + now.minute
    if m < DAY_START:
        return now.date() - dt.timedelta(days=1), m + 24 * 60
    return now.date(), m


def day_type(day):
    try:
        with open(HOLIDAYS) as f:
            if day.strftime("%Y%m%d") in {l.split(",")[0] for l in f}:
                return "sun"  # 공휴일은 일요일 시간표
    except OSError:
        pass
    return {5: "sat", 6: "sun"}.get(day.weekday(), "wkd")


def load_sched():
    try:
        return json.loads(SCHED.read_text())
    except (OSError, ValueError):
        return {}


def learn(sched, items, route):
    """도착정보 응답의 firstTm/lastTm → (가장 이른 첫차, 가장 늦은 막차) 분, 그 시간표가 속한 날(첫차 날짜) 기준.
    자정 이후엔 API 가 **다음 날** 시간표를 주므로 조회 시각이 아니라 firstTm 의 날짜로 요일유형을 정한다(09-28 버그 수정)."""
    fts = sorted(i["firstTm"][:12] for i in items if i.get("firstTm", "").strip())
    lts = [i["lastTm"][:12] for i in items if i.get("lastTm", "").strip()]
    if not fts or not lts:
        return
    day = dt.datetime.strptime(fts[0][:8], "%Y%m%d").date()
    def minutes(ts):
        d = dt.datetime.strptime(ts, "%Y%m%d%H%M")
        return (d.date() - day).days * 24 * 60 + d.hour * 60 + d.minute
    new = [minutes(fts[0]), max(minutes(t) for t in lts)]
    old = sched.setdefault(route, {}).get(day_type(day), new)
    # 넓히기만 한다: 막차가 지난 뒤(자정 직후) 응답은 막차를 더 이르게 보고함(09-28 종로03 00:32→00:08) → 덮어쓰면 막차를 놓침
    sched[route][day_type(day)] = [min(old[0], new[0]), max(old[1], new[1])]


def allowed(now, route=None, sched=None):
    """새벽 차단 + (노선을 주면) 그 노선의 시간표 창 안인지."""
    if NIGHT[0] <= now.time() < NIGHT[1]:
        return False
    if route is None:
        return True
    day, m = service_day(now)
    first, last = (sched or {}).get(route, {}).get(day_type(day), FALLBACK)
    return first - PAD <= m <= last + PAD


def already_used(day):
    """운행일 day 에 이미 한 호출 수: day 폴더의 05시 이후 + 다음 날 폴더의 05시 전 도착정보 파일(노선별 1호출 = 1파일)."""
    nxt = day + dt.timedelta(days=1)
    n = sum(1 for f in (LOG / day.strftime("%Y%m%d")).glob("*_arr_*.json") if f.stem[-6:] >= "050000")
    return n + sum(1 for f in (LOG / nxt.strftime("%Y%m%d")).glob("*_arr_*.json") if f.stem[-6:] < "050000")


def keys():
    ks = [l.split("=", 1)[1].strip() for l in open(ROOT / ".env") if l.startswith("SEOUL_BUS_API_KEY")]
    return list(dict.fromkeys(k for k in ks if k))  # 같은 키 중복 등록 시 한도 초과 방지


def fetch(url, k, route_id):
    q = urllib.parse.urlencode({"serviceKey": k, "busRouteId": route_id, "resultType": "json"})
    with urllib.request.urlopen(f"{url}?{q}", timeout=15) as r:
        return r.read()


class UsageBudget:
    """실패도 호출 전에 기록한다. 재시작해도 키별·서비스별 당일 사용량을 되돌리지 않는다."""
    def __init__(self, ks, now):
        self.day = now.strftime("%Y%m%d")  # 공급자 일일 한도는 KST 달력 날짜로 분리
        self.path = LOG / "usage" / (self.day + ".json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.ids = {k: hashlib.sha256(k.encode()).hexdigest()[:16] for k in ks}
        try:
            self.used = json.loads(self.path.read_text())
            if not isinstance(self.used, dict) or any(type(n) is not int or n < 0 for v in self.used.values() for n in v.values()):
                raise ValueError("invalid usage ledger")
        except FileNotFoundError:
            # 이전 버전에서 넘어오는 날: 저장 성공 + 오류 로그를 보수적으로 배분한다.
            totals = {kind: len(list((LOG / self.day).glob(f"*_{kind}_*.json"))) for kind in URLS}
            restarts = 0
            if (LOG / "collect.log").exists():
                with (LOG / "collect.log").open() as f:
                    for line in f:
                        if not line.startswith(now.strftime("%Y-%m-%d")):
                            continue
                        if "start, keys" in line:
                            restarts += 1
                        parts = line.split()
                        if len(parts) >= 4 and parts[1] in ROUTES and parts[2] in URLS:
                            totals[parts[2]] += 1
            margin = restarts + 16 if any(totals.values()) else 0
            self.used = {ident: {kind: -(-n // len(ks)) + margin for kind, n in totals.items()} for ident in self.ids.values()}
            self.save()
        # 손상된 장부는 0으로 초기화하지 않는다. 수집기 실패로 감시 대상이 된다.

    def save(self):
        write_snapshot(self.path, json.dumps(self.used).encode())

    def reserve(self, key, service):
        values = self.used.setdefault(self.ids[key], {})
        if values.get(service, 0) >= LIMIT:
            return False
        values[service] = values.get(service, 0) + 1
        self.save()  # 전송 직후 죽어도 이 호출은 이미 반영되어 있음
        return True


def attempt(route, kind, key, now, budget, state, sched):
    """한 번만 요청하고 실패 시 최대 5분까지 늦춘다. 상태에 키/URL/원문 오류를 넣지 않는다."""
    name = route + ":" + kind
    entry = state.setdefault("endpoints", {}).setdefault(name, {})
    if now.timestamp() < entry.get("retry_after", 0):
        return
    if not budget.reserve(key, kind):
        entry.update(status="budget_exhausted", retry_after=0)
        return
    entry["last_attempt"] = now.isoformat()
    try:
        body = fetch(URLS[kind], key, ROUTES[route])
        data = json.loads(body)
        code = str(data["msgHeader"]["headerCd"])
        if code not in ("0", "4"):
            raise ValueError("API header error")
        directory = LOG / now.strftime("%Y%m%d")
        directory.mkdir(parents=True, exist_ok=True)
        write_snapshot(directory / f"{route}_{kind}_{now:%H%M%S}.json", body)
        entry.update(status="ok", last_success=now.isoformat(), failures=0, retry_after=0, http_status=200)
        if kind == "arr" and code == "0":
            learn(sched, data["msgBody"]["itemList"] or [], route)
            write_snapshot(SCHED, json.dumps(sched, ensure_ascii=False, indent=1).encode())
    except Exception as e:
        failures = entry.get("failures", 0) + 1
        entry.update(status="upstream_error", failures=failures,
                     retry_after=now.timestamp() + min(300, 30 * 2 ** min(failures, 4)),
                     http_status=getattr(e, "code", None), error_type=type(e).__name__)
        print(now.isoformat(), route, kind, type(e).__name__, getattr(e, "code", ""), flush=True)


def main():
    ks = keys()
    if not ks:
        raise RuntimeError("버스 API 키가 없음")
    pool = itertools.cycle(ks)
    share = len(ROUTES) / len(ks)  # 키 하나가 한 틱에 부담하는 평균 호출 수 (서비스별)
    print(dt.datetime.now(KST).isoformat(), "start, keys =", len(ks), "share =", round(share, 3), flush=True)
    sched = load_sched()
    budget = None
    try:
        state = json.loads((LOG / "collector_state.json").read_text())
    except (OSError, ValueError):
        state = {"endpoints": {}}
    while True:
        now = dt.datetime.now(KST)
        if budget is None or budget.day != now.strftime("%Y%m%d"):
            budget = UsageBudget(ks, now)
            print(now.isoformat(), "호출 장부 날짜", budget.day, flush=True)
        active = [r for r in ROUTES if allowed(now, r, sched)]
        if active:
            for route in active:
                k = next(pool)
                for kind in URLS:
                    attempt(route, kind, k, now, budget, state, sched)
            state["heartbeat"] = dt.datetime.now(KST).isoformat()
            write_snapshot(LOG / "collector_state.json", json.dumps(state).encode())
            iv = interval(now.time(), share)
            time.sleep(iv - (time.time() % iv))
        else:
            LOG.mkdir(parents=True, exist_ok=True)
            state["heartbeat"] = now.isoformat()
            write_snapshot(LOG / "collector_state.json", json.dumps(state).encode())
            time.sleep(60)


def write_snapshot(path, body):
    """쓰는 도중의 JSON이 최신 파일로 읽히지 않도록 같은 폴더에서 원자적으로 교체한다."""
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as f:
            tmp = Path(f.name)
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
