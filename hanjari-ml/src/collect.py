"""실시간 수집기 (성북02·종로03). 매일, 노선별 **실제 버스 시간표**(첫차 10분 전 ~ 막차 10분 후) 동안 도착정보·차량위치 원본을 그대로 저장.

시간표: 도착정보 응답의 firstTm/lastTm(그날 시간표)을 노선·요일유형(평일/토/일·공휴일)별로 data/api_logs/schedule.json 에 학습.
        아직 모르는 요일유형은 넉넉히 05:30~00:40 에 받으며 배운다. 01:30~05:00 은 어떤 경우에도 호출 안 함(새벽 차단).
        자정 넘은 막차(성북02 00:06, 종로03 00:32)는 전날 운행일로 셈.

data/api_logs/YYYYMMDD/{노선}_{arr,pos}_HHMMSS.json  (시각은 KST)
실행: nohup python3 src/collect.py >> data/api_logs/collect.log 2>&1 &
키: .env 의 SEOUL_BUS_API_KEY* 전부를 풀로 묶어 호출마다 돌아가며 사용. 간격 = 기본간격 × 노선수 ÷ 키수 (키당 한도 유지).
"""
import datetime as dt, hashlib, itertools, json, os, tempfile, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path
from api_response import response_items

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


def replay_usage(log, day, key_count):
    """과거 라운드로빈 수집기의 요청 묶음을 복원한다. 평균에 임의 여유분을 더하지 않는다.

    재시작/운행일 초기화 구간마다 각 키의 요청 수는 floor~ceil(묶음수/키수).
    한 요청에서 파일 저장 후 오류 로그도 남았으면 한 번만 센다.
    종료 직전 기록하지 못한 요청은 구간당 서비스별 최대 1회로 따로 보관한다.
    """
    groups, boundaries, counts = {}, {"000000", "240000"}, set()
    for path in (log / day).glob("*.json"):
        parts = path.stem.split("_")
        if len(parts) == 3 and parts[0] in ROUTES and parts[1] in URLS:
            groups.setdefault((parts[2], parts[0]), set()).add(parts[1])
    journal = log / "collect.log"
    if journal.exists():
        with journal.open() as f:
            for line in f:
                if not line.startswith(dt.datetime.strptime(day, "%Y%m%d").strftime("%Y-%m-%d")):
                    continue
                parts = line.split()
                stamp = parts[0][11:19].replace(":", "")
                if "start, keys" in line:
                    count = int(line.split("keys =", 1)[1].split()[0])
                    counts.add(count)
                    boundaries.add(stamp)
                if "오늘 이미 호출" in line:
                    boundaries.add(stamp)
                if len(parts) >= 4 and parts[1] in ROUTES and parts[2] in URLS:
                    groups.setdefault((stamp, parts[1]), set()).add(parts[2])
    if counts and counts != {key_count}:
        raise ValueError("키 구성이 바뀐 과거 기록은 균등 배분하여 복원할 수 없음")
    bounds, segments = {kind: dict(lower=0, upper=0, unlogged=0) for kind in URLS}, []
    cuts = sorted(boundaries)
    for a, b in zip(cuts, cuts[1:]):
        rows = [value for (stamp, _), value in groups.items() if a <= stamp < b]
        if not rows:
            continue
        segment = dict(start=a, end=b, groups=len(rows))
        for kind in URLS:
            present = sum(kind in row for row in rows)
            # 한쪽만 기록된 묶음도 같은 키가 선택됐으므로 누락 가능성을 상한에 포함한다.
            bounds[kind]["lower"] += max(0, len(rows) // key_count - (len(rows) - present))
            bounds[kind]["upper"] += -(-len(rows) // key_count)
            bounds[kind]["unlogged"] += 1
            segment[kind] = present
        segments.append(segment)
    return dict(kind="legacy_round_robin_bounds", day=day, key_count=key_count,
                recorded_total={kind: sum(kind in row for row in groups.values()) for kind in URLS},
                per_key_bounds=bounds, segments=segments)


class UsageBudget:
    """새 요청 예약 수와 과거 복원 범위·미기록 가능량을 분리한다."""
    def __init__(self, ks, now, reconcile=False, manual_calls=None):
        self.day = now.strftime("%Y%m%d")
        self.path = LOG / "usage" / (self.day + ".json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.ids = {k: hashlib.sha256(k.encode()).hexdigest()[:16] for k in ks}
        try:
            saved = json.loads(self.path.read_text())
        except FileNotFoundError:
            saved = None
        if reconcile or saved is None:
            if reconcile and saved and saved.get("version") == 2:
                raise ValueError("현재 예약 장부는 과거 로그로 재복원하지 않음")
            self.origin = replay_usage(LOG, self.day, len(ks))
            self.used = {ident: {kind: 0 for kind in URLS} for ident in self.ids.values()}
            self.prior = {ident: {kind: dict(bound) for kind, bound in self.origin["per_key_bounds"].items()} for ident in self.ids.values()}
            # 직접 수행한 진단 요청처럼 근거가 있는 별도 호출만 지정한다. 키는 파일에 저장하지 않는다.
            for key, services in (manual_calls or {}).items():
                for kind, n in services.items():
                    if kind not in URLS or type(n) is not int or n < 0:
                        raise ValueError("invalid manual call allowance")
                    self.prior[self.ids[key]][kind]["unlogged"] += n
            if reconcile and self.path.exists():
                backup = self.path.with_name(self.path.name + ".before-reconcile")
                if backup.exists():
                    raise ValueError("reconciliation backup already exists")
                backup.write_bytes(self.path.read_bytes())
            self.save()
        elif saved.get("version") == 2:
            self.used, self.prior, self.origin = saved["used"], saved["prior"], saved["origin"]
        else:
            # 이전 패딩 장부는 명시적 재검사 없이 낮추지 않는다.
            self.used = {ident: {kind: 0 for kind in URLS} for ident in saved}
            self.prior = {ident: {kind: dict(lower=0, upper=n, unlogged=0) for kind, n in services.items()} for ident, services in saved.items()}
            self.origin = dict(kind="legacy_unverified", day=self.day)
        if set(self.used) != set(self.ids.values()) or set(self.prior) != set(self.ids.values()):
            raise ValueError("키 구성이 호출 장부와 다름")
        for ident in self.used:
            for kind in URLS:
                bound = self.prior[ident][kind]
                nums = [self.used[ident][kind], bound["lower"], bound["upper"], bound["unlogged"]]
                if any(type(n) is not int or n < 0 for n in nums) or bound["lower"] > bound["upper"]:
                    raise ValueError("invalid usage ledger")

    def save(self):
        write_snapshot(self.path, json.dumps(dict(version=2, day=self.day, used=self.used, prior=self.prior, origin=self.origin)).encode())

    def remaining(self, key, service):
        ident = self.ids[key]
        before = self.prior[ident][service]
        return max(0, LIMIT - before["upper"] - before["unlogged"] - self.used[ident][service])

    def choose(self, preferred, service):
        if self.remaining(preferred, service):
            return preferred
        return next((key for key in self.ids if self.remaining(key, service)), preferred)

    def blocked_status(self):
        uncertain = any(b["upper"] != b["lower"] or b["unlogged"] for services in self.prior.values() for b in services.values())
        return "budget_estimated_limit" if uncertain else "budget_exhausted"

    def reserve(self, key, service):
        if not self.remaining(key, service):
            return False
        self.used[self.ids[key]][service] += 1
        self.save()  # 전송 직후 죽어도 예약한 호출은 이미 반영되어 있음
        return True


def attempt(route, kind, key, now, budget, state, sched):
    """한 번만 요청하고 실패 시 최대 5분까지 늦춘다. 상태에 키/URL/원문 오류를 넣지 않는다."""
    name = route + ":" + kind
    entry = state.setdefault("endpoints", {}).setdefault(name, {})
    if now.timestamp() < entry.get("retry_after", 0):
        return
    key = budget.choose(key, kind)
    if not budget.reserve(key, kind):
        entry.update(status=budget.blocked_status(), retry_after=0)
        return
    entry["last_attempt"] = now.isoformat()
    # 응답 본문/URL에는 키가 포함될 수 있다. 상태에는 단계·숫자 코드·본문 지문만 남긴다.
    diagnostic_fields = ("failure_stage", "error_type", "api_header_code", "response_kind",
                         "response_prefix_sha256", "response_sample_bytes")
    for field in diagnostic_fields:
        entry.pop(field, None)
    stage, body, code = "request", None, None
    try:
        body = fetch(URLS[kind], key, ROUTES[route])
        stage = "decode"
        data = json.loads(body)
        stage = "api_header"
        code = str(data["msgHeader"]["headerCd"])
        if code not in ("0", "4"):
            raise ValueError("API header error")
        stage = "api_body"
        items = response_items(data)
        stage = "snapshot_store"
        directory = LOG / now.strftime("%Y%m%d")
        directory.mkdir(parents=True, exist_ok=True)
        write_snapshot(directory / f"{route}_{kind}_{now:%H%M%S}.json", body)
        entry.update(status="ok", last_success=now.isoformat(), failures=0, retry_after=0, http_status=200)
        if kind == "arr" and code == "0":
            stage = "schedule"
            learn(sched, items, route)
            write_snapshot(SCHED, json.dumps(sched, ensure_ascii=False, indent=1).encode())
    except Exception as e:
        failures = entry.get("failures", 0) + 1
        local = stage in ("snapshot_store", "schedule")
        status = ("storage_error" if isinstance(e, OSError) else "processing_error") if local else "upstream_error"
        entry.update(status=status, failures=failures, failure_stage=stage,
                     retry_after=now.timestamp() + min(300, 30 * 2 ** min(failures, 4)),
                     http_status=getattr(e, "code", 200 if body is not None else None), error_type=type(e).__name__)
        if code is not None and code.isascii() and code.isdecimal() and len(code) <= 4:
            entry["api_header_code"] = code  # 제공사 코드와 HTTP 상태는 별개. 코드 의미를 추측하지 않는다.
        if isinstance(e, urllib.error.HTTPError):
            try:
                body = e.read(8192)
            except Exception:
                body = None
            finally:
                e.close()
        if body is not None:
            sample = body[:8192]
            beginning = sample.lstrip().lower()
            form = "html" if beginning.startswith((b"<!doctype html", b"<html")) else "xml" if beginning.startswith(b"<") else "json" if beginning.startswith((b"{", b"[")) else "other"
            entry.update(response_kind=form, response_prefix_sha256=hashlib.sha256(sample).hexdigest(), response_sample_bytes=len(sample))
        print(now.isoformat(), route, kind, type(e).__name__, entry["http_status"], stage,
              entry.get("api_header_code", ""), flush=True)


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
