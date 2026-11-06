"""수집 감시 — 10분마다(systemd 타이머). '켜져 있는데 못 받는' 조용한 실패를 잡는다.

  - 노선 시간표 안인데 최신 스냅샷이 STALE 분보다 오래됨 → 알림. 수집기 생존 신호도 끊긴 경우에만 재시작
  - 최근 스냅샷 RECENT 개가 전부 API 오류 응답(키 만료·한도 초과) → 알림
  - 남은 디스크 MIN_FREE_GB 미만 → 알림
같은 문제는 한 번만 알리고(reports/watchdog.json), 운행 중 사라지면 '복구' 알림.
운행 종료는 장애 복구의 증거가 아니므로 해당 노선은 다음 운행에서 다시 확인한다.
"""
import datetime as dt, json, shutil, subprocess, urllib.request
import build_dataset as B
import collect as C
import notify as N
from api_response import response_items

STALE = 10          # 분. 한산한 시간 수집 간격이 2분 반이라 넉넉히
RECENT = 10
MIN_FREE_GB = 5
RESTART_GAP = 30    # 분
STATE = N.REPORTS / "watchdog.json"


def web_health():
    with urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5) as response:
        status = json.loads(response.read())
    if not isinstance(status, dict) or type(status.get('ready')) is not bool:
        raise ValueError('invalid web health response')
    return status


def load_state(now):
    try:
        state = json.loads(STATE.read_text())
        if not isinstance(state, dict) or not isinstance(state.get('open', []), list) \
                or any(not isinstance(p, str) for p in state.get('open', [])):
            raise ValueError('invalid watchdog state')
        if type(state.get('web_failures', 0)) is not int:
            raise ValueError('invalid web failure count')
        for key in ('restarted', 'web_restarted'):
            if key in state and (not isinstance(state[key], str) or dt.datetime.fromisoformat(state[key]).tzinfo is not None):
                raise ValueError('invalid restart time')
        return state
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, TypeError):
        backup = STATE.with_name(STATE.name + '.corrupt-' + now.strftime('%Y%m%d%H%M%S%f'))
        try:
            STATE.rename(backup)
            for old in STATE.parent.glob(STATE.name + '.corrupt-*'):
                if old != backup:
                    old.unlink()
        except OSError:
            pass
        N.send('감시 상태 손상: 파일 격리 후 계속 감시. 재시작 이력이 불명확하여 30분간 자동 재시작 보류', 'WARN')
        # Keep an unknown previous restart from causing a restart loop after recovery.
        return {'restarted': now.isoformat(), 'web_restarted': now.isoformat()}


def restart_due(state, key, now):
    last = state.get(key)
    return not last or (now - dt.datetime.fromisoformat(last)).total_seconds() > RESTART_GAP * 60


def collector_alive(now):
    """API 장애/한도 대기 중인 살아 있는 수집기는 재시작하지 않는다."""
    try:
        state = json.loads((B.LOG / "collector_state.json").read_text())
        heartbeat = dt.datetime.fromisoformat(state["heartbeat"]).astimezone(N.KST).replace(tzinfo=None)
        return 0 <= (now - heartbeat).total_seconds() <= 600
    except (OSError, ValueError, KeyError, TypeError):
        return False


def ok_header(f):
    try:
        response_items(json.loads(f.read_bytes()))
        return True
    except (OSError, ValueError):
        return False


def check(now):
    problems, stale = [], False
    sched = C.load_sched()
    # 자정 직후엔 새 날짜 폴더가 비어 있음(막차 00:42 까지 수집 중) → 어제 폴더까지 보고 가장 최근 파일로 판단 (10-02 헛알림 수정)
    folders = [B.LOG / (now - dt.timedelta(days=d)).strftime("%Y%m%d") for d in (1, 0)]
    for route in C.ROUTES:
        if not C.allowed(now, route, sched):
            continue
        day, m = C.service_day(now)
        first = sched.get(route, {}).get(C.day_type(day), C.FALLBACK)[0]
        if m < first - C.PAD + STALE:  # 수집 시작 직후는 아직 쌓이는 중
            continue
        fs = [f for fd in folders for f in sorted(fd.glob(f"{route}_arr_*.json"))]  # 날짜 순 → 마지막이 가장 최근
        age = (now - dt.datetime.strptime(fs[-1].parent.name + fs[-1].stem[-6:], "%Y%m%d%H%M%S")).total_seconds() / 60 if fs else None
        if age is None or age > STALE:
            problems.append(f"{route} 새 데이터 없음({'이틀간 0개' if age is None else f'{age:.0f}분째'})")
            stale = not collector_alive(now)
        elif fs and not any(ok_header(f) for f in fs[-RECENT:]):
            problems.append(f"{route} 최근 {RECENT}개 모두 API 오류 응답(키·한도 확인)")
    free = shutil.disk_usage(B.LOG.resolve()).free / 1e9
    if free < MIN_FREE_GB:
        problems.append(f"남은 디스크 {free:.1f}GB")
    return problems, stale


def main():
    now = dt.datetime.now(N.KST).replace(tzinfo=None)
    problems, stale = check(now)
    st = load_state(now)
    if stale:
        if restart_due(st, 'restarted', now):
            r = subprocess.run(["sudo", "-n", "systemctl", "restart", "hanjari-collect"], capture_output=True, text=True)
            problems.append("수집기 재시작 " + ("함" if r.returncode == 0 else f"실패({r.stderr.strip()[:80]})"))
            st["restarted"] = now.isoformat()
    web_problem, web_stale = None, False
    try:
        web = web_health()
        model = web.get('model') or {}
        if not web['ready']:
            status = model.get('status', 'unknown') if isinstance(model, dict) else 'unknown'
            web_problem = f'웹 모델 {status}(ready=false, 확인 후 ~/hanjari-ml/src/daily.py rollback 검토)'
            web_stale = status == 'stale'
    except (OSError, ValueError, TypeError):
        web_problem = '웹 연결/상태 확인 실패(확인 후 ~/hanjari-ml/src/daily.py rollback 검토)'
    st['web_failures'] = st.get('web_failures', 0) + 1 if web_problem else 0
    if web_problem:
        if st['web_failures'] == 1:
            print(now.strftime('%H:%M'), '웹 감시 1회 실패, 다음 점검에서 재확인:', web_problem)
        else:
            problems.append(web_problem)
            if web_stale and restart_due(st, 'web_restarted', now):
                st['web_restarted'] = now.isoformat()
                try:
                    r = subprocess.run(['sudo', '-n', 'systemctl', 'try-restart', 'hanjari-web'],
                                       capture_output=True, text=True, timeout=60)
                    note = '함' if r.returncode == 0 else f'실패({r.stderr.strip()[:80]})'
                except (OSError, subprocess.SubprocessError) as exc:
                    note = f'실패({type(exc).__name__})'
                problems.append('웹 재시작 ' + note)
    key = sorted(p.split("(")[0] for p in problems if not p.startswith(("수집기 재시작", '웹 재시작')))
    previous = st.get("open", [])
    sched = C.load_sched()
    inactive = [route for route in C.ROUTES if not C.allowed(now, route, sched)]
    pending = [problem for problem in previous if any(problem.startswith(route+" ") for route in inactive)]
    tracked = sorted(set(key + pending))
    if set(key) - set(previous):
        N.send("수집 감시: " + " / ".join(problems), "ERROR")
    elif not tracked and previous:
        N.send("수집 감시: 복구됨 (" + " / ".join(previous) + ")", "INFO")
    st["open"], st["checked"], st["outside_service_routes"] = tracked, now.isoformat(), inactive
    N.REPORTS.mkdir(exist_ok=True)
    C.write_snapshot(STATE, json.dumps(st, ensure_ascii=False).encode())
    print(now.strftime("%H:%M"), problems or ("운행시간 밖 노선은 다음 운행에서 재확인" if pending else
          "웹 재확인 대기" if st['web_failures'] == 1 else "문제 없음"))


if __name__ == "__main__":
    main()
